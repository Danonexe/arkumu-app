from django.db import models
from arkumu.metadata.models.cidoc import UUIDModel


class MappingType(models.TextChoices):
    """Types of data mappings supported."""
    ENTITY = 'entity', 'Entity Mapping'          # Intra-dataset: row cells → entity properties
    LOOKUP = 'lookup', 'Lookup Mapping'          # Inter-dataset: FK values → entity references  
    VOCABULARY = 'vocabulary', 'Vocabulary Mapping'  # Multi-value → controlled terms
    JUNCTION = 'junction', 'Junction Mapping'    # Junction table → relationships


class Mapping(UUIDModel):
    """Mapping definitions for transforming CSV data to RDF triples"""
    
    # Basic mapping info
    name = models.CharField(max_length=255)
    mapping_type = models.CharField(max_length=20, choices=MappingType.choices)
    
    # Scope: 'dataset' or 'multi_dataset' 
    scope = models.CharField(max_length=20, default='multi_dataset')
    
    # Organization context
    organization_id = models.CharField(max_length=255, db_index=True)
    
    # Source information (for traceability)
    source_dataset = models.CharField(max_length=255, help_text="Primary dataset this mapping applies to")
    source_file = models.CharField(max_length=500, blank=True, help_text="Original file path/name")
    
    # Mapping configuration - structured by type
    mapping_config = models.JSONField(default=dict, help_text="Type-specific mapping configuration")
    
    # Provenance and validation
    created_by = models.CharField(max_length=255, blank=True)
    validation_status = models.CharField(max_length=20, default='draft', 
                                       choices=[('draft', 'Draft'), ('validated', 'Validated'), ('active', 'Active')])
    
    # Execution tracking
    last_executed = models.DateTimeField(null=True, blank=True)
    execution_stats = models.JSONField(default=dict, help_text="Statistics from last execution")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_id', 'mapping_type']),
            models.Index(fields=['source_dataset', 'validation_status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_mapping_type_display()}) - {self.organization_id}"
    
    def get_subject_column(self):
        """Get the column that becomes the RDF subject (for Entity mappings)"""
        if self.mapping_type == MappingType.ENTITY:
            return self.mapping_config.get('subject_column')
        return None
    
    def get_predicate_mappings(self):
        """Get column -> predicate mappings (for Entity mappings)"""
        if self.mapping_type == MappingType.ENTITY:
            return self.mapping_config.get('predicate_mappings', {})
        return {}
    
    def get_lookup_config(self):
        """Get lookup configuration (for Lookup mappings)"""
        if self.mapping_type == MappingType.LOOKUP:
            return self.mapping_config.get('lookup_config', {})
        return {}
    
    def is_ready_for_execution(self):
        """Check if mapping is ready to execute"""
        return (self.validation_status == 'active' and 
                self.mapping_config and 
                self.mapping_type in MappingType.values) 