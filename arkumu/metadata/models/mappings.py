from django.db import models
from arkumu.metadata.models.cidoc import UUIDModel


class Mapping(UUIDModel):
    """Generic mapping storage for datasets and columns"""
    
    # Scope: 'dataset' or 'multi_dataset' 
    scope = models.CharField(max_length=20, default='multi_dataset')
    
    # Organization context
    organization_id = models.CharField(max_length=255, db_index=True)
    
    # All mapping data stored as JSON
    mapping_data = models.JSONField(default=dict)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_id', 'scope']),
        ]
    
    def __str__(self):
        return f"{self.scope} mapping for {self.organization_id}" 