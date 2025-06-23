from django.db import models
from django.conf import settings
from arkumu.metadata.models.cidoc import UUIDModel


class Mapping(UUIDModel):
    """Flexible mapping configurations for CSV data transformation"""
    
    # Basic mapping info
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Optional description of what this mapping does")
    
    # Organization context
    organization_id = models.CharField(max_length=255, db_index=True)
    
    # Source information (for traceability)
    source_datasets = models.JSONField(default=list, help_text="List of datasets this mapping applies to")
    
    # Flexible mapping configuration - GUI interprets structure
    mapping_config = models.JSONField(default=dict, help_text="Flexible mapping configuration interpreted by GUI")
    
    # Provenance and validation
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name='created_mappings', null=True, blank=True)
    validation_status = models.CharField(max_length=20, default='draft', 
                                       choices=[('draft', 'Draft'), ('validated', 'Validated'), ('active', 'Active')])
    
    # Execution tracking
    last_executed = models.DateTimeField(null=True, blank=True)
    execution_stats = models.JSONField(default=dict, help_text="Statistics from last execution")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_id', 'validation_status']),
            models.Index(fields=['created_by', 'validation_status']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.organization_id}"
    
    def get_dataset_count(self):
        """Get number of datasets in this mapping"""
        return len(self.source_datasets)
    
    def get_column_count(self):
        """Get total number of columns in workspace (selected columns only)"""
        workspace_columns = self.mapping_config.get('workspace_columns', {})
        return len(workspace_columns)
    
    def get_relationship_count(self):
        """Get number of FK relationships configured"""
        return len(self.mapping_config.get('fk_relationships', {}))
    
    def is_ready_for_execution(self):
        """Check if mapping has sufficient configuration to execute"""
        return (self.validation_status in ['validated', 'active'] and 
                self.mapping_config and 
                self.source_datasets) 