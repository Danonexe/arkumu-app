from django.db import transaction
from unittest import mock
from ..models.entities import CIDOCRelationship

def create_test_relationship_pair(source, target, relation_type, inverse_type, user):
    """
    Create a bidirectional relationship pair without validation constraints.
    
    This utility bypasses the inverse relationship validation temporarily to allow 
    creating both sides of a relationship in tests.
    
    Args:
        source: Source entity for the main relationship
        target: Target entity for the main relationship
        relation_type: Main relationship type (e.g., 'P7')
        inverse_type: Inverse relationship type (e.g., 'P7i')
        user: User creating the relationships
        
    Returns:
        tuple: (main_relationship, inverse_relationship)
    """
    # Create both relationships at once without validation
    with transaction.atomic():
        # Temporarily patch the validator
        with mock.patch('arkumu.cidoc.validators.validate_inverse_relationship'):
            rel1 = CIDOCRelationship.objects.create(
                source=source, 
                target=target, 
                relation_type=relation_type,
                created_by=user, 
                updated_by=user
            )
            rel2 = CIDOCRelationship.objects.create(
                source=target, 
                target=source, 
                relation_type=inverse_type,
                created_by=user, 
                updated_by=user
            )
    return rel1, rel2 