import pytest
import os
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from pathlib import Path
from rdflib import Namespace, Graph
from arkumu.metadata.models.cidoc import CIDOCClass, CIDOCProperty
from arkumu.metadata.rdf_import import import_cidoc_from_rdf



@pytest.fixture
def cidoc_ns():
    """Return the CIDOC namespace"""
    return Namespace("http://www.cidoc-crm.org/cidoc-crm/")

@pytest.fixture(scope='session')
def rdf_file_path():
    """Return the path to the CIDOC RDF file"""
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    rdf_file = os.path.join(base_dir, 'arkumu', 'metadata', 'schema', 'CIDOC_CRM_v7.1.1.rdf')
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

