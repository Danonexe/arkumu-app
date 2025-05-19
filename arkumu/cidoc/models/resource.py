from django.db import models
from django.utils.translation import gettext_lazy as _
from arkumu.cidoc.models.cidoc import UUIDModel


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

    source_field = models.TextField(
        blank=True,
        null=True,
        help_text="Original value from the source data field"
    )

    # Fields for literals (relevant only if resource_type is LITERAL)
    literal_value = models.TextField(blank=True, null=True, help_text="Value when this resource represents a literal")
    literal_datatype = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Datatype URI for literal values (e.g., xsd:string, xsd:integer)"
    )
    literal_language = models.CharField(
        max_length=10, blank=True, null=True,
        help_text="Language tag for language-tagged string literals (e.g., 'en', 'fr')"
    )

    # The old fields is_literal, value, datatype, language would be removed/renamed.

    class Meta:
        # You might need a constraint to ensure uri is not null if type is not LITERAL
        # And that literal_value is not null if type is LITERAL
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(resource_type='LITERAL') & models.Q(literal_value__isnull=False)) |
                    (~models.Q(resource_type='LITERAL') & models.Q(uri__isnull=False))
                ),
                name='resource_type_consistency'
            )
        ]

    def __str__(self):
        if self.resource_type == ResourceType.LITERAL:
            result = f'"{self.literal_value}"'
            if self.literal_datatype:
                result += f"^^{self.literal_datatype}"
            if self.literal_language:
                result += f"@{self.literal_language}"
            return result
        return self.uri or f"_{self.id}" # Fallback for blank node or uninitialized
