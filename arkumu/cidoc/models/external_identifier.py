from django.db import models
from .entities import CIDOCEntity

class ExternalIdentifier(models.Model):
    """
    Model for storing external identifiers that link CIDOC entities to external systems.
    
    This model allows tracking of identifiers from various source systems (like CSV imports,
    archives, etc.) and maintains the relationship between external IDs and CIDOC entities.
    
    Attributes:
        entity (ForeignKey): The CIDOC entity this identifier belongs to
        identifier (str): The actual identifier value
        identifier_type (str): Type of identifier (e.g., "UUID", "URI", "local_id")
        source_system (str): System that provided this identifier
        import_date (datetime): When this identifier was imported
    """
    
    entity = models.ForeignKey(CIDOCEntity, on_delete=models.CASCADE, related_name='external_ids')
    identifier = models.CharField(max_length=255, db_index=True)
    identifier_type = models.CharField(max_length=50)  # e.g., "UUID", "URI", "local_id"
    source_system = models.CharField(max_length=100)   # e.g., "CSV_IMPORT_2024_03", "ARCHIVE_X"
    import_date = models.DateTimeField(auto_now_add=True)
