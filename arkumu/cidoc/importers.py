import pandas as pd
import json
import uuid
import os.path
import logging
from django.db import transaction
from django.db.utils import IntegrityError
from .models import CIDOCClass, CIDOCProperty, CIDOCEntity, CIDOCData, SourceTracking


class CIDOCImporter:
    """
    Generic importer for CIDOC-CRM data.
    Takes a mapping definition (JSON) and a data source (CSV) and imports the data
    according to the mapping rules.
    """
    
    def __init__(self, mapping_file, csv_file, 
                 institution=None, field=None, batch_name=None,
                 delimiter=';', skip_existing=True):
        """
        Initialize the importer.
        
        Args:
            mapping_file: Path to the mapping JSON file
            csv_file: Path to the CSV data file
            institution: Name of the institution providing the data
            field: Field or collection within the institution
            batch_name: Identifier for this import batch
            delimiter: CSV delimiter character (default: ';')
            skip_existing: Whether to skip rows that already exist (based on external IDs)
        """
        self.mapping_file = mapping_file
        self.csv_file = csv_file
        self.delimiter = delimiter
        self.skip_existing = skip_existing
        self.logger = logging.getLogger(__name__)
        
        # Extract default institution and field from file paths if not provided
        if institution is None:
            # Try to extract from the directory structure, assuming something like
            # arkumu-metadata/institution/field/file.csv
            path_parts = os.path.normpath(csv_file).split(os.path.sep)
            if len(path_parts) >= 3 and path_parts[-3] == 'arkumu-metadata':
                institution = path_parts[-2]
        
        if field is None and len(path_parts) >= 3:
            field = path_parts[-3]
        
        # Generate a batch name if not provided
        if batch_name is None:
            csv_basename = os.path.splitext(os.path.basename(csv_file))[0]
            batch_name = f"{csv_basename}_{uuid.uuid4().hex[:8]}"
        
        # Create or get the source tracking record
        self.source, _ = SourceTracking.objects.get_or_create(
            institution=institution or "Unknown",
            field=field or "Unknown",
            import_batch=batch_name
        )
        
        # Dictionary to cache entities we've created or retrieved
        self.entity_cache = {}
        
        # Load the mapping
        with open(mapping_file, 'r') as f:
            self.mapping_config = json.load(f)
            self.mappings = self.mapping_config.get('mappings', [])
        
        # Group mappings by subject class for easier processing
        self.mappings_by_subject = {}
        for mapping in self.mappings:
            subject_class = mapping.get('subject_class')
            if subject_class not in self.mappings_by_subject:
                self.mappings_by_subject[subject_class] = []
            self.mappings_by_subject[subject_class].append(mapping)
    
    def load_dataframe(self, nrows=None):
        """Load the CSV file into a pandas DataFrame."""
        return pd.read_csv(self.csv_file, sep=self.delimiter, nrows=nrows)
    
    def get_or_create_entity(self, entity_class_id, external_id, label=None):
        """
        Get or create an entity in the registry, with caching.
        
        Args:
            entity_class_id: CIDOC class ID (e.g., "E12_Production")
            external_id: External identifier for the entity
            label: Human-readable label for the entity
            
        Returns:
            A CIDOCEntity instance
        """
        # Create a cache key
        cache_key = f"{entity_class_id}:{external_id}"
        
        # Check if we've already handled this entity
        if cache_key in self.entity_cache:
            return self.entity_cache[cache_key]
        
        # Get the class
        try:
            entity_class = CIDOCClass.objects.get(class_id=entity_class_id)
        except CIDOCClass.DoesNotExist:
            self.logger.error(f"Class {entity_class_id} not found! Creating placeholder.")
            entity_class = CIDOCClass.objects.create(
                class_id=entity_class_id,
                class_name=entity_class_id,
                class_description=f"Auto-created during import"
            )
        
        # Try to find an existing entity
        entity = None
        if external_id:
            entity = CIDOCEntity.objects.filter(
                entity_class=entity_class,
                external_id=external_id
            ).first()
        
        # Create if not found
        if entity is None:
            entity = CIDOCEntity.objects.create(
                entity_class=entity_class,
                external_id=external_id or "",
                label=label or external_id or "",
                source=self.source
            )
        
        # Cache and return
        self.entity_cache[cache_key] = entity
        return entity
    
    def create_cidoc_statement(self, subject_entity, property_id, target_entity=None, value_data=None):
        """
        Create a CIDOC data statement.
        
        Args:
            subject_entity: The subject CIDOCEntity
            property_id: The CIDOC property ID (e.g., "P2_has_type")
            target_entity: Target entity for relationships (or None for literals)
            value_data: Value data for literal properties (or None for relationships)
            
        Returns:
            The created CIDOCData instance or None if there was an error
        """
        try:
            # Get the property
            property_obj = CIDOCProperty.objects.get(property_id=property_id)
            
            # Check if this statement already exists
            existing = CIDOCData.objects.filter(
                entity=subject_entity,
                property=property_obj,
                target_entity=target_entity
            )
            
            if existing.exists():
                if value_data and not existing.filter(value_data__value=value_data.get('value')).exists():
                    # If there's a statement with the same entity/property/target but different value,
                    # create a new one
                    pass
                else:
                    # Otherwise skip
                    return None
            
            # Create the statement
            return CIDOCData.objects.create(
                entity=subject_entity,
                property=property_obj,
                value_data=value_data,
                target_entity=target_entity,
                source=self.source
            )
        
        except CIDOCProperty.DoesNotExist:
            self.logger.error(f"Property {property_id} not found! Skipping statement.")
            return None
        except IntegrityError as e:
            self.logger.error(f"Integrity error creating statement: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error creating statement: {e}")
            return None
    
    def process_row(self, row):
        """
        Process a single row from the CSV according to the mapping.
        
        Args:
            row: A pandas Series representing a row from the CSV
            
        Returns:
            Dictionary of created entities by subject class
        """
        row_entities = {}
        
        # First, create all the primary entities for each subject class
        for subject_class, mappings in self.mappings_by_subject.items():
            # Find a suitable identifier for this entity
            identifier_mapping = next(
                (m for m in mappings if m.get('predicate', '').startswith('P1_')), 
                None
            )
            
            external_id = None
            if identifier_mapping:
                id_column = identifier_mapping.get('source_column')
                if id_column in row and pd.notna(row[id_column]):
                    external_id = str(row[id_column])
            
            # If no identifier found, use a generic one based on the row index
            if not external_id and 'Projekt_ID' in row:
                external_id = f"{subject_class}_{row['Projekt_ID']}"
            elif not external_id:
                external_id = f"{subject_class}_{uuid.uuid4().hex[:8]}"
            
            # Create or get the entity
            entity = self.get_or_create_entity(
                subject_class, 
                external_id,
                label=f"{subject_class} {external_id}"
            )
            row_entities[subject_class] = entity
        
        # Create any missing relationships between primary entities
        # For example, connect Document to Production or other relationships
        for subject_class, entity in row_entities.items():
            if subject_class == "E31_Document" and "E12_Production" in row_entities:
                # Connect Document to Production
                self.create_cidoc_statement(
                    entity,
                    "P70_documents",
                    target_entity=row_entities["E12_Production"]
                )
        
        # Now process each mapping to create properties and relationships
        for mapping in self.mappings:
            source_column = mapping.get('source_column')
            subject_class = mapping.get('subject_class')
            predicate = mapping.get('predicate')
            object_class = mapping.get('object_class')
            
            # Skip if missing required fields
            if not all([source_column, subject_class, predicate, object_class]):
                self.logger.warning(f"Skipping incomplete mapping: {mapping}")
                continue
            
            # Skip if column is empty in this row
            if source_column not in row or pd.isna(row[source_column]) or row[source_column] == "":
                continue
            
            # Get the subject entity
            subject_entity = row_entities.get(subject_class)
            if not subject_entity:
                self.logger.warning(f"Missing subject entity for {subject_class}")
                continue
            
            # Handle different object types
            if object_class in ["E62_String", "rdfs:Literal"]:
                # This is a literal property
                self.create_cidoc_statement(
                    subject_entity,
                    predicate,
                    value_data={"value": str(row[source_column])}
                )
            else:
                # This is a relationship to another entity
                # Create a unique external ID for the related entity
                related_external_id = f"{subject_class}_{predicate}_{source_column}_{row[source_column]}"
                
                # Create or get the related entity
                related_entity = self.get_or_create_entity(
                    object_class,
                    related_external_id,
                    label=str(row[source_column])
                )
                
                # Create the relationship
                self.create_cidoc_statement(
                    subject_entity,
                    predicate,
                    target_entity=related_entity
                )
                
                # If this is an identifier, add its value
                if object_class == "E42_Identifier":
                    self.create_cidoc_statement(
                        related_entity,
                        "P190_has_symbolic_content",
                        value_data={"value": str(row[source_column])}
                    )
        
        return row_entities
    
    def import_data(self, limit=None):
        """
        Import data from the CSV file according to the mapping.
        
        Args:
            limit: Maximum number of rows to import (None for all)
            
        Returns:
            Dictionary with statistics about the import
        """
        df = self.load_dataframe(nrows=limit)
        
        stats = {
            'total_rows': len(df),
            'processed_rows': 0,
            'skipped_rows': 0,
            'errors': 0,
            'entities_created': 0,
            'statements_created': 0
        }
        
        # Process each row
        for index, row in df.iterrows():
            try:
                with transaction.atomic():
                    self.process_row(row)
                    stats['processed_rows'] += 1
            except Exception as e:
                stats['errors'] += 1
                self.logger.error(f"Error processing row {index}: {e}")
        
        # Update entity and statement counts
        stats['entities_created'] = len(self.entity_cache)
        stats['statements_created'] = CIDOCData.objects.filter(source=self.source).count()
        
        return stats


# Simple usage example:
def import_csv_with_mapping(mapping_file, csv_file, institution=None, field=None, batch_name=None, limit=None):
    """
    Import a CSV file using a mapping file.
    
    Args:
        mapping_file: Path to the mapping JSON file
        csv_file: Path to the CSV data file
        institution: Name of the institution providing the data
        field: Field or collection within the institution
        batch_name: Identifier for this import batch
        limit: Maximum number of rows to import (None for all)
        
    Returns:
        Dictionary with statistics about the import
    """
    importer = CIDOCImporter(
        mapping_file=mapping_file,
        csv_file=csv_file,
        institution=institution,
        field=field,
        batch_name=batch_name
    )
    
    return importer.import_data(limit=limit) 