# models.py
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db.models import Prefetch
from arkumu.cidoc.models.cidoc import UUIDModel, CIDOCClass, CIDOCProperty
from arkumu.cidoc.models.ontology import Ontology, OntologyClass, OntologyProperty, Resource



class Resource(UUIDModel):
    uri = models.URLField(max_length=512, unique=True, 
                      help_text="Uniform Resource Identifier for this resource")
    source = models.CharField(max_length=255, blank=True, help_text="Source or origin of this resource")
    value = models.TextField(blank=True, null=True, help_text="Value when this resource represents a literal")
    is_literal = models.BooleanField(default=False, help_text="Whether this resource represents a literal value")
    datatype = models.CharField(max_length=255, blank=True, null=True, 
                help_text="Datatype URI for literal values (e.g., xsd:string, xsd:integer)")
    language = models.CharField(max_length=10, blank=True, null=True,
                help_text="Language tag for language-tagged string literals (e.g., 'en', 'fr')")
    
    # Ontology mappings (including CIDOC-CRM via the ontology system)
    ontology_classes = models.ManyToManyField(OntologyClass, blank=True, related_name="resources",
                                             help_text="Classes from various ontologies this resource is mapped to")

    def __str__(self):
        if self.is_literal:
            result = f'"{self.value}"'
            if self.datatype:
                result += f"^^{self.datatype}"
            if self.language:
                result += f"@{self.language}"
            return result
        return self.uri
    
    def get_cidoc_class(self):
        """Returns the CIDOC class if this resource is mapped to one"""
        cidoc_ontology = Ontology.objects.filter(is_cidoc=True).first()
        if not cidoc_ontology:
            return None
            
        cidoc_classes = self.ontology_classes.filter(ontology=cidoc_ontology)
        if cidoc_classes.exists():
            return cidoc_classes.first().cidoc_class
        return None
    
    def get_ontology_classes(self, ontology_prefix=None):
        """
        Returns ontology class mappings, optionally filtered by ontology prefix
        """
        if ontology_prefix:
            return self.ontology_classes.filter(ontology__prefix=ontology_prefix)
        return self.ontology_classes.all()
    
    def add_cidoc_class(self, cidoc_class_id):
        """Helper method to add a CIDOC class mapping"""
        cidoc_ontology = Ontology.objects.filter(is_cidoc=True).first()
        if not cidoc_ontology:
            return False
            
        try:
            cidoc_class = CIDOCClass.objects.get(class_id=cidoc_class_id)
            ontology_class, created = OntologyClass.objects.get_or_create(
                ontology=cidoc_ontology,
                class_id=cidoc_class_id,
                defaults={
                    'label': cidoc_class.label,
                    'description': cidoc_class.description,
                    'uri': f"{cidoc_ontology.uri}{cidoc_class_id}",
                    'cidoc_class': cidoc_class
                }
            )
            self.ontology_classes.add(ontology_class)
            return True
        except CIDOCClass.DoesNotExist:
            return False


class Triple(UUIDModel):
    subject = models.ForeignKey(Resource, related_name='subject_triples', on_delete=models.CASCADE)
    predicate = models.ForeignKey(Resource, related_name='predicate_triples', on_delete=models.CASCADE)
    object = models.ForeignKey(Resource, related_name='object_triples', on_delete=models.CASCADE)
    
    # Ontology mappings (including CIDOC-CRM via the ontology system)
    ontology_properties = models.ManyToManyField(OntologyProperty, blank=True, related_name="triples",
                                               help_text="Properties from various ontologies this triple is mapped to")

    class Meta:
        indexes = [
            models.Index(fields=['subject', 'predicate']),
            models.Index(fields=['object']),
        ]

    def __str__(self):
        return f"{self.subject} {self.predicate} {self.object}"
    
    def get_cidoc_property(self):
        """Returns the CIDOC property if this triple is mapped to one"""
        # Use cached CIDOC ontology for performance
        cidoc_ontology = Ontology.get_cidoc_ontology()
        if not cidoc_ontology:
            return None
            
        # Use select_related to avoid extra queries
        cidoc_properties = self.ontology_properties.filter(
            ontology=cidoc_ontology
        ).select_related('cidoc_property')
        
        if cidoc_properties.exists():
            return cidoc_properties.first().cidoc_property
        return None
    
    def get_ontology_properties(self, ontology_prefix=None):
        """
        Returns ontology property mappings, optionally filtered by ontology prefix
        """
        # Use select_related to optimize performance
        queryset = self.ontology_properties.select_related('ontology')
        
        if ontology_prefix:
            return queryset.filter(ontology__prefix=ontology_prefix)
        return queryset.all()
    
    def add_cidoc_property(self, cidoc_property_id):
        """Helper method to add a CIDOC property mapping"""
        # Use cached CIDOC ontology for performance
        cidoc_ontology = Ontology.get_cidoc_ontology()
        if not cidoc_ontology:
            return False
            
        try:
            # Get the CIDOC property
            cidoc_property = CIDOCProperty.objects.get(property_id=cidoc_property_id)
            
            # Use the efficient helper method
            ontology_property = OntologyProperty.get_or_create_from_cidoc(
                cidoc_property, 
                cidoc_ontology
            )
            
            # Add to the triple's properties
            self.ontology_properties.add(ontology_property)
            return True
        except CIDOCProperty.DoesNotExist:
            return False
    
    def clean(self):
        """
        Validate ontology constraints including CIDOC-CRM domain/range if applicable
        """
        super().clean()
        
        # Load and cache subject & object classes to avoid N+1 queries
        subject_classes = list(self.subject.ontology_classes.all())
        subject_class_ids = {cls.id for cls in subject_classes}
        
        # Only check object classes if it's not a literal
        object_class_ids = set()
        if not self.object.is_literal:
            object_classes = list(self.object.ontology_classes.all())
            object_class_ids = {cls.id for cls in object_classes}
        
        # Get property mappings with related domain and range classes
        property_mappings = self.ontology_properties.select_related(
            'domain_class', 'range_class'
        ).all()
        
        for property_mapping in property_mappings:
            # Skip properties without domain/range constraints
            if not (property_mapping.domain_class or property_mapping.range_class):
                continue
                
            # Check domain constraints
            if property_mapping.domain_class and property_mapping.domain_class.id not in subject_class_ids:
                raise ValidationError(
                    f"Subject does not match domain for property {property_mapping}. "
                    f"Expected {property_mapping.domain_class}."
                )
            
            # Check range constraints (only if not a literal)
            if property_mapping.range_class and not self.object.is_literal:
                if property_mapping.range_class.id not in object_class_ids:
                    raise ValidationError(
                        f"Object does not match range for property {property_mapping}. "
                        f"Expected {property_mapping.range_class}."
                    )
    
    @classmethod
    def get_resource_triples(cls, resource_uri, as_subject=True, as_object=True, include_literals=True):
        """
        Efficiently get all triples where a resource appears as subject and/or object
        """
        try:
            resource = Resource.objects.get(uri=resource_uri)
        except Resource.DoesNotExist:
            return []
            
        queries = []
        if as_subject:
            subject_triples = cls.objects.filter(subject=resource)
            queries.append(subject_triples)
        
        if as_object:
            # If we don't want literals, filter them out
            object_filter = {'object': resource}
            if not include_literals:
                object_filter['object__is_literal'] = False
                
            object_triples = cls.objects.filter(**object_filter)
            queries.append(object_triples)
        
        # Combine queries if both subject and object are requested
        if as_subject and as_object:
            from django.db.models import Q
            return cls.objects.filter(
                Q(subject=resource) | 
                Q(object=resource, **({} if include_literals else {'object__is_literal': False}))
            ).select_related('subject', 'predicate', 'object')
        elif queries:
            # Return the single query with optimizations
            return queries[0].select_related('subject', 'predicate', 'object')
        else:
            return cls.objects.none()
    
    @classmethod
    def bulk_add_cidoc_property(cls, triple_ids, cidoc_property_id):
        """
        Efficiently add a CIDOC property to multiple triples at once.
        """
        # Get the CIDOC ontology
        cidoc_ontology = Ontology.get_cidoc_ontology()
        if not cidoc_ontology:
            return False
            
        try:
            # Get the CIDOCProperty
            cidoc_property = CIDOCProperty.objects.get(property_id=cidoc_property_id)
            
            # Get or create the OntologyProperty
            ontology_property = OntologyProperty.get_or_create_from_cidoc(
                cidoc_property, 
                cidoc_ontology
            )
            
            # Get the triples
            triples = cls.objects.filter(id__in=triple_ids)
            
            # Add the property to all triples
            for triple in triples:
                triple.ontology_properties.add(ontology_property)
                
            return True
        except CIDOCProperty.DoesNotExist:
            return False
    
    @classmethod
    def validate_batch(cls, triples):
        """
        Validate a batch of triples efficiently by loading related data once.
        Returns a list of (triple, error_message) tuples for invalid triples.
        """
        if not triples:
            return []
            
        # Collect all subjects and objects
        subject_ids = {t.subject_id for t in triples}
        object_ids = {t.object_id for t in triples}
        resource_ids = subject_ids | object_ids
        
        # Load all resources with their classes in one query
        resources = Resource.objects.filter(
            id__in=resource_ids
        ).prefetch_related('ontology_classes')
        
        # Build lookup dictionaries
        resources_by_id = {r.id: r for r in resources}
        resource_classes = {}
        for resource in resources:
            resource_classes[resource.id] = set(
                cls.id for cls in resource.ontology_classes.all()
            )
        
        # Collect all ontology properties
        property_mappings = {}
        for triple in triples:
            for prop in triple.ontology_properties.select_related('domain_class', 'range_class').all():
                if prop.domain_class or prop.range_class:
                    if triple.id not in property_mappings:
                        property_mappings[triple.id] = []
                    property_mappings[triple.id].append(prop)
        
        # Validate each triple
        errors = []
        for triple in triples:
            # Skip if no property mappings with constraints
            if triple.id not in property_mappings:
                continue
                
            triple_errors = []
            subject_classes = resource_classes.get(triple.subject_id, set())
            object_resource = resources_by_id.get(triple.object_id)
            object_classes = resource_classes.get(triple.object_id, set())
            
            for prop in property_mappings[triple.id]:
                # Check domain
                if prop.domain_class and prop.domain_class.id not in subject_classes:
                    triple_errors.append(
                        f"Subject does not match domain for property {prop}. Expected {prop.domain_class}."
                    )
                
                # Check range (if not literal)
                if prop.range_class and not object_resource.is_literal:
                    if prop.range_class.id not in object_classes:
                        triple_errors.append(
                            f"Object does not match range for property {prop}. Expected {prop.range_class}."
                        )
            
            if triple_errors:
                errors.append((triple, triple_errors))
                
        return errors
