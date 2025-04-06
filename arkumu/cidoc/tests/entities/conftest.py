import pytest
import os
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from pathlib import Path
from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
from arkumu.cidoc.models.entities import CIDOCEntity, CIDOCEntityProperty, CIDOCRelationship
from arkumu.cidoc.rdf_import import import_cidoc_from_rdf
import arkumu.cidoc.models.graph_service

@pytest.fixture(autouse=True)
def disable_graph_db(monkeypatch):
    """
    Disable graph database operations for entity tests.
    
    We use a flag-based approach to disable graph operations, which allows us to:
    1. Test entity models with real data without graph dependencies
    2. Keep database validation intact, but skip graph creation
    3. Maintain separation between entity model tests and graph integration tests
    
    This is a cleaner approach than patching individual methods, as the application
    code already supports this flag-based approach.
    """
    monkeypatch.setattr(arkumu.cidoc.models.graph_service, 'ENABLE_GRAPH_DB', False)
    yield

@pytest.fixture(scope='session')
def rdf_file_path():
    """Return the path to the CIDOC RDF file"""
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    rdf_file = os.path.join(base_dir, 'cidoc', 'schema', 'CIDOC_CRM_v7.1.1.rdf')
    assert os.path.exists(rdf_file), f"RDF file not found at {rdf_file}"
    return rdf_file

@pytest.fixture(scope='session')
def loaded_cidoc_data(django_db_setup, django_db_blocker, rdf_file_path):
    """
    Load CIDOC data from RDF into actual database models.
    This fixture has session scope to ensure schema is loaded only once per test session.
    """
    with django_db_blocker.unblock():
        # First check if data is already loaded
        if CIDOCClass.objects.count() > 0 and CIDOCProperty.objects.count() > 0:
            classes_count = CIDOCClass.objects.count()
            properties_count = CIDOCProperty.objects.count()
            print(f"\nUsing existing CIDOC schema: {classes_count} classes and {properties_count} properties")
            return (classes_count, properties_count)
            
        # If not loaded, import from RDF
        with transaction.atomic():
            classes_count, properties_count = import_cidoc_from_rdf(rdf_file_path)
            print(f"\nLoaded {classes_count} classes and {properties_count} properties for testing")
            
            # Ensure critical classes exist - create them if not found
            required_classes = ['E1', 'E5', 'E21', 'E53', 'E70']
            for class_id in required_classes:
                CIDOCClass.objects.get_or_create(
                    class_id=class_id,
                    defaults={
                        'label': f'{class_id} Test Class',
                        'description': f'Test class for {class_id}'
                    }
                )
                
            # Ensure critical properties exist - create them if not found  
            required_properties = ['P1', 'P2', 'P3', 'P7', 'P12']
            for prop_id in required_properties:
                # Get or create the property
                prop, created = CIDOCProperty.objects.get_or_create(
                    property_id=prop_id,
                    defaults={
                        'label': f'{prop_id} Test Property',
                        'description': f'Test property for {prop_id}'
                    }
                )
                
                # If inverse property exists (P7i, P12i, etc.), ensure it's linked
                inverse_id = f"{prop_id}i"
                inverse_prop, inverse_created = CIDOCProperty.objects.get_or_create(
                    property_id=inverse_id,
                    defaults={
                        'label': f'{inverse_id} Test Property',
                        'description': f'Test inverse property for {prop_id}'
                    }
                )
                
                # Link inverse properties
                if prop_id != 'P1' and prop_id != 'P3':  # Skip P1 and P3 as they might not have inverses
                    prop.inverse_property = inverse_prop
                    inverse_prop.inverse_property = prop
                    prop.save()
                    inverse_prop.save()
                    print(f"Linked inverse: {prop_id} -> {inverse_id}")
                    print(f"Linked inverse: {inverse_id} -> {prop_id}")
            
            # Set up domain and range for P7 (took place at) - Event -> Place
            try:
                p7 = CIDOCProperty.objects.get(property_id='P7')
                p7i = CIDOCProperty.objects.get(property_id='P7i')
                e5 = CIDOCClass.objects.get(class_id='E5')
                e53 = CIDOCClass.objects.get(class_id='E53')
                
                p7.domain_class = e5  # Event
                p7.range_class = e53  # Place
                p7.save()
                
                p7i.domain_class = e53  # Place
                p7i.range_class = e5  # Event
                p7i.save()
                print(f"Set up domain/range for P7 (Event -> Place)")
            except (CIDOCProperty.DoesNotExist, CIDOCClass.DoesNotExist):
                print(f"Warning: Could not set up domain/range for P7")
                
            # Set up domain and range for P1 (is identified by) - Any entity -> E41 Appellation
            try:
                p1 = CIDOCProperty.objects.get(property_id='P1')
                e1 = CIDOCClass.objects.get(class_id='E1')
                e41, _ = CIDOCClass.objects.get_or_create(
                    class_id='E41',
                    defaults={
                        'label': 'E41 Appellation',
                        'description': 'Appellation class'
                    }
                )
                
                p1.domain_class = e1  # Any entity
                p1.save()
                print(f"Set up domain for P1 (Any entity)")
            except (CIDOCProperty.DoesNotExist, CIDOCClass.DoesNotExist):
                print(f"Warning: Could not set up domain for P1")
                
            # Set up P3 as a note property (for testing relationship properties)
            try:
                p3 = CIDOCProperty.objects.get(property_id='P3')
                e1 = CIDOCClass.objects.get(class_id='E1')
                
                # P3 has literal note values
                p3.domain_class = e1
                p3.save()
                print(f"Set up P3 as note property")
            except (CIDOCProperty.DoesNotExist, CIDOCClass.DoesNotExist):
                print(f"Warning: Could not set up P3")
            
            # Create a symmetric property for testing
            sym_prop, created = CIDOCProperty.objects.get_or_create(
                property_id='P_TEST_SYMMETRIC',
                defaults={
                    'label': 'Test Symmetric Property',
                    'description': 'Property for symmetric relationship testing',
                    'is_symmetric': True
                }
            )
            
            if created or not sym_prop.domain_class:
                e1 = CIDOCClass.objects.get(class_id='E1')
                sym_prop.domain_class = e1
                sym_prop.range_class = e1
                sym_prop.is_symmetric = True
                sym_prop.save()
                print(f"Created symmetric property P_TEST_SYMMETRIC")
                
        return (CIDOCClass.objects.count(), CIDOCProperty.objects.count())

@pytest.fixture
def test_user(db):
    """Create a test user."""
    User = get_user_model()
    return User.objects.create_user(
        username='testuser', 
        email='test@example.com',
        password='password123'
    )

@pytest.fixture
def test_superuser(db):
    """Create a test superuser."""
    User = get_user_model()
    return User.objects.create_superuser(
        username='admin', 
        email='admin@example.com',
        password='admin123'
    )

@pytest.fixture
def test_group(db):
    """Create a test group."""
    return Group.objects.get_or_create(name='TestGroup')[0]

@pytest.fixture
def cidoc_classes(loaded_cidoc_data):
    """Return a dictionary of commonly used CIDOC classes for testing."""
    classes = {}
    
    # Get commonly used classes or create them if missing
    required_classes = ['E1', 'E5', 'E21', 'E53', 'E70']
    for class_id in required_classes:
        cls, created = CIDOCClass.objects.get_or_create(
            class_id=class_id,
            defaults={
                'label': f'{class_id} Test Class',
                'description': f'Test class for {class_id}'
            }
        )
        classes[class_id] = cls
        if created:
            print(f"Created class: {class_id}")
            
    return classes

@pytest.fixture
def cidoc_properties(loaded_cidoc_data, cidoc_classes):
    """Return a dictionary of commonly used CIDOC properties for testing."""
    properties = {}
    
    # Get commonly used properties or create them if missing
    required_properties = ['P1', 'P2', 'P3', 'P7', 'P12', 'P_TEST_SYMMETRIC']
    for prop_id in required_properties:
        prop, created = CIDOCProperty.objects.get_or_create(
            property_id=prop_id,
            defaults={
                'label': f'{prop_id} Test Property',
                'description': f'Test property for {prop_id}'
            }
        )
        properties[prop_id] = prop
        if created:
            print(f"Created property: {prop_id}")
            
            # For P7, set domain and range if they don't exist
            if prop_id == 'P7' and not prop.domain_class:
                prop.domain_class = cidoc_classes['E5']  # Event
                prop.range_class = cidoc_classes['E53']  # Place
                prop.save()
            
            # For P_TEST_SYMMETRIC, set domain and range to E1
            if prop_id == 'P_TEST_SYMMETRIC' and not prop.domain_class:
                prop.domain_class = cidoc_classes['E1']
                prop.range_class = cidoc_classes['E1']
                prop.is_symmetric = True
                prop.save()
    
    return properties

@pytest.fixture
def real_entity(db, cidoc_classes, test_user):
    """Create a real entity for testing."""
    return CIDOCEntity.objects.create(
        crm_class=cidoc_classes['E1'].class_id,
        created_by=test_user,
        updated_by=test_user
    )

@pytest.fixture
def real_entities(db, cidoc_classes, test_user):
    """Create multiple real entities for relationship testing."""
    return [
        CIDOCEntity.objects.create(
            crm_class=cidoc_classes['E21'].class_id,
            created_by=test_user,
            updated_by=test_user
        ),
        CIDOCEntity.objects.create(
            crm_class=cidoc_classes['E53'].class_id,
            created_by=test_user,
            updated_by=test_user
        ),
        CIDOCEntity.objects.create(
            crm_class=cidoc_classes['E5'].class_id,
            created_by=test_user,
            updated_by=test_user
        )
    ]

@pytest.fixture
def real_property(cidoc_properties):
    """Get a real property for testing."""
    return cidoc_properties['P1']

@pytest.fixture
def real_relationship_property(cidoc_properties):
    """Get a property suitable for relationships."""
    return cidoc_properties['P7']  # Changed from P12 to P7 as we set up its domain/range

@pytest.fixture
def real_entity_with_property(db, real_entity, real_property, test_user):
    """Create an entity with a property."""
    CIDOCEntityProperty.objects.create(
        entity=real_entity,
        cidoc_property=real_property,
        value_data='Test Entity',
        created_by=test_user,
        updated_by=test_user
    )
    return real_entity

@pytest.fixture
def real_relationship(db, real_entities, real_relationship_property, test_user):
    """Create a real relationship for testing."""
    # Use the event (index 2) and place (index 1) with P7 (took place at)
    return CIDOCRelationship.objects.create(
        source=real_entities[2],  # Event
        target=real_entities[1],  # Place
        relation_type=real_relationship_property.property_id,
        created_by=test_user,
        updated_by=test_user
    ) 