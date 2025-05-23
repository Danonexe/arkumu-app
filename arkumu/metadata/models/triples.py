# models.py
from django.db import models
from django.core.exceptions import ValidationError
from arkumu.metadata.models.cidoc import UUIDModel
from arkumu.metadata.models.resource import Resource, ResourceType


class Triple(UUIDModel):
    subject = models.ForeignKey(Resource, related_name='subject_triples', on_delete=models.CASCADE)
    predicate = models.ForeignKey(Resource, related_name='predicate_triples', on_delete=models.CASCADE)
    object = models.ForeignKey(Resource, related_name='object_triples', on_delete=models.CASCADE)
    
    class Meta:
        indexes = [
            models.Index(fields=['subject', 'predicate']),
            models.Index(fields=['object']),
        ]
        # Add uniqueness constraint to prevent duplicate triples
        constraints = [
            models.UniqueConstraint(
                fields=['subject', 'predicate', 'object'],
                name='unique_triple'
            )
        ]
    
    def clean(self):
        """Validate the triple based on resource types."""
        # Subject cannot be a literal
        if self.subject.resource_type == ResourceType.LITERAL:
            raise ValidationError("Subject cannot be a literal resource")
        
        # Predicate must be a property
        if self.predicate.resource_type != ResourceType.PROPERTY:
            raise ValidationError("Predicate must be a property resource")
            
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.subject} —{self.predicate}→ {self.object}"

