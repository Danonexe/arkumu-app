from django.db import models
from django.utils.translation import gettext_lazy as _
from arkumu.metadata.models.cidoc import UUIDModel


class ResourceType(models.TextChoices):
        IRI = 'IRI', _('IRI Identified Resource')
        CLASS = 'CLASS', _('Class')
        PROPERTY = 'PROPERTY', _('Property')
        LITERAL = 'LITERAL', _('Literal')
        # Potentially BLANK_NODE = 'BLANK', _('Blank Node') if you plan to mint them


class Resource(UUIDModel):

    uri = models.URLField(
        max_length=512,
        unique=True,  # Unique for non-literals
        null=True,    # Literals don't have URIs
        blank=True,
        help_text="Uniform Resource Identifier for this resource"
    )
    resource_type = models.CharField(
        max_length=10,
        choices=ResourceType.choices,
        default=ResourceType.IRI,
        help_text="Type of the resource (IRI, Class, Property, or Literal)"
    )
    source = models.CharField(max_length=255, blank=True, help_text="Source or origin of this resource (e.g., the institution like 'FUK')")


    # Explicit column tracking fields for better querying
    name = models.TextField(
        max_length=255, 
        null=True, 
        blank=True,
        help_text="Name of the column, property, or context this resource represents"
    )
    
    value = models.TextField(
        null=True, 
        blank=True,
        help_text="Value of this resource (literal value or descriptive value for IRIs)"
    )
    
    is_placeholder = models.BooleanField(
        default=False,
        help_text="Indicates if this is a placeholder resource created during cross-reference that hasn't been fully imported yet"
    )

    datatype = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Datatype URI for literal values (e.g., xsd:string, xsd:integer)"
    )
    language = models.CharField(
        max_length=10, blank=True, null=True,
        help_text="Language tag for language-tagged string literals (e.g., 'en', 'fr')"
    )

    class Meta:
        # Ensure consistency between resource_type and required fields
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(resource_type='LITERAL') & models.Q(value__isnull=False)) |
                    (~models.Q(resource_type='LITERAL') & models.Q(uri__isnull=False))
                ),
                name='resource_type_consistency'
            ),
            # Add uniqueness constraint for literal values
            models.UniqueConstraint(
                fields=['value', 'language', 'datatype', 'source', 'name'],
                condition=models.Q(resource_type='LITERAL'),
                name='unique_literal_value'
            )
        ]
        
        # Add indexes for common queries
        indexes = [
            models.Index(fields=['name'], name='name_idx'),
            models.Index(fields=['value'], name='value_idx'),
            models.Index(fields=['source', 'name'], name='source_name_idx'),
        ]

    def __str__(self):
        if self.resource_type == ResourceType.LITERAL:
            result = f'"{self.value}"'
            if self.datatype:
                result += f"^^{self.datatype}"
            if self.language:
                result += f"@{self.language}"
            return result
        return self.uri or f"_{self.id}" # Fallback for blank node or uninitialized
