from django.core.exceptions import ValidationError  
from django.db import models
from django.core.cache import cache
from arkumu.cidoc.models.cidoc import UUIDModel, CIDOCClass, CIDOCProperty

class Ontology(UUIDModel):
    """Represents an ontology that can be used for mapping"""
    uri = models.URLField(max_length=512, unique=True, db_index=True)
    prefix = models.CharField(max_length=50, unique=True, db_index=True, 
                             help_text="Short prefix for the ontology (e.g., 'cidoc', 'foaf')")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_cidoc = models.BooleanField(default=False, db_index=True, 
                                  help_text="Whether this is the CIDOC-CRM ontology")
    
    class Meta:
        verbose_name_plural = "Ontologies"
    
    def __str__(self):
        return f"{self.prefix}: {self.name}"
    
    def save(self, *args, **kwargs):
        # Ensure only one ontology is marked as CIDOC-CRM
        if self.is_cidoc and not self.pk:  # If new CIDOC ontology
            Ontology.objects.filter(is_cidoc=True).update(is_cidoc=False)
            # Clear cache when CIDOC ontology changes
            cache.delete('cidoc_ontology_id')
        super().save(*args, **kwargs)
        # Update cache if this is the CIDOC ontology
        if self.is_cidoc:
            cache.set('cidoc_ontology_id', self.id, timeout=None)  # Permanent cache

    @classmethod
    def get_cidoc_ontology(cls):
        """Efficiently get the CIDOC ontology instance with caching"""
        # Try to get from cache first
        ontology_id = cache.get('cidoc_ontology_id')
        if ontology_id:
            try:
                return cls.objects.get(id=ontology_id)
            except cls.DoesNotExist:
                # If cached ID is invalid, clear it
                cache.delete('cidoc_ontology_id')
        
        # If not in cache or cache is invalid, fetch and cache
        ontology = cls.objects.filter(is_cidoc=True).first()
        if ontology:
            cache.set('cidoc_ontology_id', ontology.id, timeout=None)
        return ontology

class OntologyClass(UUIDModel):
    """Represents a class from any ontology"""
    uri = models.URLField(max_length=512, unique=True, db_index=True)
    ontology = models.ForeignKey(Ontology, on_delete=models.CASCADE, related_name="classes")
    class_id = models.CharField(max_length=100, db_index=True, 
                              help_text="Original ID in the ontology (e.g., 'Person', 'E21')")
    label = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # CIDOC-specific fields
    cidoc_class = models.OneToOneField(CIDOCClass, on_delete=models.SET_NULL, null=True, blank=True,
                                   help_text="Link to CIDOC class if this is a CIDOC-CRM class")
    
    class Meta:
        verbose_name_plural = "Ontology Classes"
        unique_together = [['ontology', 'class_id']]
        indexes = [
            models.Index(fields=['ontology', 'class_id']),
        ]
    
    def __str__(self):
        return f"{self.ontology.prefix}:{self.class_id}"
    
    def save(self, *args, **kwargs):
        # Auto-link to CIDOC class if this is in the CIDOC ontology
        if self.ontology.is_cidoc and not self.cidoc_class and self.class_id:
            # Only attempt to find and link if we have a class_id
            try:
                self.cidoc_class = CIDOCClass.objects.get(class_id=self.class_id)
            except CIDOCClass.DoesNotExist:
                pass
        super().save(*args, **kwargs)
        # Clear any cached data that might include this class
        cache_key = f'ontology_class:{self.ontology.prefix}:{self.class_id}'
        cache.delete(cache_key)
    
    @classmethod
    def get_or_create_from_cidoc(cls, cidoc_class, cidoc_ontology=None):
        """
        Efficiently creates an OntologyClass linked to a CIDOC class.
        Useful for bulk operations to avoid redundant queries.
        """
        if not cidoc_ontology:
            cidoc_ontology = Ontology.get_cidoc_ontology()
            if not cidoc_ontology:
                return None
                
        # Try to get existing first
        try:
            return cls.objects.get(ontology=cidoc_ontology, class_id=cidoc_class.class_id)
        except cls.DoesNotExist:
            # Create new if not exists
            return cls.objects.create(
                ontology=cidoc_ontology,
                class_id=cidoc_class.class_id,
                label=cidoc_class.label,
                description=cidoc_class.description,
                uri=f"{cidoc_ontology.uri}{cidoc_class.class_id}",
                cidoc_class=cidoc_class
            )

class OntologyProperty(UUIDModel):
    """Represents a property from any ontology"""
    uri = models.URLField(max_length=512, unique=True, db_index=True)
    ontology = models.ForeignKey(Ontology, on_delete=models.CASCADE, related_name="properties")
    property_id = models.CharField(max_length=100, db_index=True, 
                                help_text="Original ID in the ontology (e.g., 'knows', 'P1')")
    label = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Domain and range
    domain_class = models.ForeignKey(OntologyClass, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="domain_properties", help_text="Domain class for this property")
    range_class = models.ForeignKey(OntologyClass, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="range_properties", help_text="Range class for this property")
    
    # Property characteristics
    is_functional = models.BooleanField(default=False, help_text="Property can have at most one value")
    is_symmetric = models.BooleanField(default=False, help_text="If A relates to B, then B relates to A")
    is_transitive = models.BooleanField(default=False, help_text="If A relates to B and B to C, then A relates to C")
    
    # CIDOC-specific fields
    cidoc_property = models.OneToOneField(CIDOCProperty, on_delete=models.SET_NULL, null=True, blank=True,
                                      help_text="Link to CIDOC property if this is a CIDOC-CRM property")
    
    class Meta:
        verbose_name_plural = "Ontology Properties"
        unique_together = [['ontology', 'property_id']]
        indexes = [
            models.Index(fields=['ontology', 'property_id']),
        ]
    
    def __str__(self):
        return f"{self.ontology.prefix}:{self.property_id}"
    
    def save(self, *args, **kwargs):
        # Auto-link to CIDOC property if this is in the CIDOC ontology
        perform_domain_range_linking = False
        
        if self.ontology.is_cidoc and not self.cidoc_property and self.property_id:
            try:
                # Get the CIDOCProperty in a separate query
                self.cidoc_property = CIDOCProperty.objects.select_related(
                    'domain_class', 'range_class'
                ).get(property_id=self.property_id)
                perform_domain_range_linking = True
            except CIDOCProperty.DoesNotExist:
                pass
                
        # First save to ensure we have an ID
        super().save(*args, **kwargs)
        
        # Now perform domain/range linking if needed
        if perform_domain_range_linking:
            self._link_domain_range()
            # Save again if domain or range was updated
            super().save(update_fields=['domain_class', 'range_class'])
        
        # Clear any cached data
        cache_key = f'ontology_property:{self.ontology.prefix}:{self.property_id}'
        cache.delete(cache_key)
    
    def _link_domain_range(self):
        """Helper method to link domain and range classes based on CIDOC property"""
        if not self.cidoc_property:
            return
            
        # Auto-populate domain if available and not already set
        if self.cidoc_property.domain_class and not self.domain_class:
            try:
                self.domain_class = OntologyClass.objects.get(
                    ontology=self.ontology, 
                    cidoc_class=self.cidoc_property.domain_class
                )
            except OntologyClass.DoesNotExist:
                # Create the domain class if it doesn't exist
                if self.cidoc_property.domain_class:
                    self.domain_class = OntologyClass.get_or_create_from_cidoc(
                        self.cidoc_property.domain_class, 
                        self.ontology
                    )
                
        # Auto-populate range if available and not already set
        if self.cidoc_property.range_class and not self.range_class:
            try:
                self.range_class = OntologyClass.objects.get(
                    ontology=self.ontology, 
                    cidoc_class=self.cidoc_property.range_class
                )
            except OntologyClass.DoesNotExist:
                # Create the range class if it doesn't exist
                if self.cidoc_property.range_class:
                    self.range_class = OntologyClass.get_or_create_from_cidoc(
                        self.cidoc_property.range_class, 
                        self.ontology
                    )
    
    @classmethod
    def get_or_create_from_cidoc(cls, cidoc_property, cidoc_ontology=None):
        """
        Efficiently creates an OntologyProperty linked to a CIDOC property.
        Useful for bulk operations to avoid redundant queries.
        """
        if not cidoc_ontology:
            cidoc_ontology = Ontology.get_cidoc_ontology()
            if not cidoc_ontology:
                return None
                
        # Try to get existing first
        try:
            return cls.objects.get(ontology=cidoc_ontology, property_id=cidoc_property.property_id)
        except cls.DoesNotExist:
            # Create new instance
            instance = cls.objects.create(
                ontology=cidoc_ontology,
                property_id=cidoc_property.property_id,
                label=cidoc_property.label,
                description=cidoc_property.description,
                uri=f"{cidoc_ontology.uri}{cidoc_property.property_id}",
                cidoc_property=cidoc_property,
                is_functional=cidoc_property.is_functional,
                is_symmetric=cidoc_property.is_symmetric,
                is_transitive=cidoc_property.is_transitive
            )
            
            # Link domain and range
            instance._link_domain_range()
            if instance.domain_class or instance.range_class:
                instance.save(update_fields=['domain_class', 'range_class'])
                
            return instance
