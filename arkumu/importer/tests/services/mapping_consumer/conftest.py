"""
Pytest configuration for mapping consumer tests.
Provides fixtures specific to mapping consumer testing.
"""

import pytest
from datetime import datetime
from arkumu.metadata.models.mappings import Mapping


@pytest.fixture
def sample_mapping_configuration():
    """Sample mapping configuration for testing"""
    return {
        'version': '1.1',
        'workspace_columns': {
            'people': {
                'name': {
                    'arkumu_type': 'Person.name',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': True,
                    'is_multi_value': False,
                    'confidence': 0.95
                },
                'age': {
                    'arkumu_type': 'Person.age',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#integer',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'confidence': 0.90
                },
                'tags': {
                    'arkumu_type': 'Person.tags',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': True,
                    'multi_value_separator': ',',
                    'confidence': 0.80
                },
                'location_id': {
                    'arkumu_type': 'Person.location',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'confidence': 0.85
                }
            },
            'locations': {
                'id': {
                    'arkumu_type': 'Location.id',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': True,
                    'is_multi_value': False,
                    'confidence': 0.95
                },
                'city': {
                    'arkumu_type': 'Location.city',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'confidence': 0.90
                }
            }
        },
        'selected_datasets': ['people', 'locations'],
        'fk_relationships': {
            'fk_1': {
                'source_column': 'location_id',
                'source_dataset': 'people',
                'target_column': 'id',
                'target_dataset': 'locations',
                'relationship_type': 'resides_in',
                'direction': 'outgoing',
                'is_multi_value': False,
                'multi_value_separator': ',',
                'confidence': 0.80
            }
        },
        'relationship_contexts': {},
        'external_ontologies': {},
        'import_strategy': {
            'update_strategy': 'SKIP_EXISTING',
            'link_topology': 'row',
            'bulk_size': 1000,
            'multi_value_threshold': 0.2,
            'enable_progress_tracking': True,
            'batch_processing': True,
            'processing_strategy': 'entity_centric'
        }
    }


@pytest.fixture
def complex_mapping_configuration():
    """Complex mapping configuration with all features"""
    return {
        'version': '1.1',
        'workspace_columns': {
            'people': {
                'id': {
                    'arkumu_type': 'Person.id',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': True,
                    'is_multi_value': False,
                    'confidence': 0.95
                },
                'name': {
                    'arkumu_type': 'Person.name',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'confidence': 0.90
                },
                'keywords': {
                    'arkumu_type': 'Person.keywords',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': True,
                    'multi_value_separator': '|',
                    'confidence': 0.75
                },
                'orcid_id': {
                    'arkumu_type': 'Person.orcid',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'is_external_ontology': True,
                    'external_ontology': {
                        'ontology_type': 'orcid',
                        'uri_template': 'https://orcid.org/{identifier}'
                    },
                    'confidence': 0.85
                },
                'org_ids': {
                    'arkumu_type': 'Person.organizations',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': True,
                    'multi_value_separator': ';',
                    'confidence': 0.70
                }
            },
            'organizations': {
                'id': {
                    'arkumu_type': 'Organization.id',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': True,
                    'is_multi_value': False,
                    'confidence': 0.95
                },
                'name': {
                    'arkumu_type': 'Organization.name',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'confidence': 0.90
                }
            },
            'projects': {
                'id': {
                    'arkumu_type': 'Project.id',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': True,
                    'is_multi_value': False,
                    'confidence': 0.95
                },
                'title': {
                    'arkumu_type': 'Project.title',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'confidence': 0.85
                },
                'person_id': {
                    'arkumu_type': 'Project.lead',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'confidence': 0.80
                },
                'org_id': {
                    'arkumu_type': 'Project.organization',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': False,
                    'is_multi_value': False,
                    'confidence': 0.80
                }
            }
        },
        'selected_datasets': ['people', 'organizations', 'projects'],
        'fk_relationships': {
            'fk_person_org': {
                'source_column': 'org_ids',
                'source_dataset': 'people',
                'target_column': 'id',
                'target_dataset': 'organizations',
                'relationship_type': 'affiliated_with',
                'direction': 'outgoing',
                'is_multi_value': True,
                'multi_value_separator': ';',
                'confidence': 0.70
            },
            'fk_project_person': {
                'source_column': 'person_id',
                'source_dataset': 'projects',
                'target_column': 'id',
                'target_dataset': 'people',
                'relationship_type': 'led_by',
                'direction': 'outgoing',
                'is_multi_value': False,
                'confidence': 0.80
            },
            'fk_project_org': {
                'source_column': 'org_id',
                'source_dataset': 'projects',
                'target_column': 'id',
                'target_dataset': 'organizations',
                'relationship_type': 'funded_by',
                'direction': 'outgoing',
                'is_multi_value': False,
                'confidence': 0.80
            }
        },
        'relationship_contexts': {
            'ctx_person_org': {
                'primary_fk': 'fk_person_org',
                'secondary_fk': 'fk_person_org',
                'context_columns': ['start_date', 'end_date', 'role'],
                'context_type': 'employment',
                'dataset_name': 'people'
            }
        },
        'external_ontologies': {
            'orcid_people': {
                'column_name': 'orcid_id',
                'dataset_name': 'people',
                'ontology_type': 'orcid',
                'uri_template': 'https://orcid.org/{identifier}',
                'identifier_column': 'orcid_id',
                'validation_enabled': True
            }
        },
        'import_strategy': {
            'update_strategy': 'UPDATE_VALUES',
            'link_topology': 'mesh',
            'bulk_size': 2000,
            'multi_value_threshold': 0.3,
            'enable_progress_tracking': True,
            'batch_processing': True,
            'processing_strategy': 'multi_phase'
        }
    }


@pytest.fixture
def test_mapping_with_config(test_user, test_organization, sample_mapping_configuration):
    """Create a test mapping with proper configuration"""
    return Mapping.objects.create(
        name='Test Mapping Consumer',
        description='Test mapping for mapping consumer tests',
        organization_id=test_organization.code,
        created_by=test_user,
        mapping_config=sample_mapping_configuration,
        validation_status='validated'
    )


@pytest.fixture
def complex_test_mapping(test_user, test_organization, complex_mapping_configuration):
    """Create a complex test mapping"""
    return Mapping.objects.create(
        name='Complex Test Mapping',
        description='Complex test mapping with all features',
        organization_id=test_organization.code,
        created_by=test_user,
        mapping_config=complex_mapping_configuration,
        validation_status='validated'
    )


@pytest.fixture
def invalid_mapping_configuration():
    """Invalid mapping configuration for error testing"""
    return {
        'version': '1.1',
        'workspace_columns': {},  # Empty workspace columns (invalid)
        'selected_datasets': ['nonexistent_dataset'],  # References non-existent dataset
        'fk_relationships': {
            'invalid_fk': {
                'source_column': 'nonexistent_col',
                'source_dataset': 'nonexistent_dataset',
                'target_column': 'id',
                'target_dataset': 'another_nonexistent_dataset',
                'relationship_type': 'relates_to'
            }
        },
        'external_ontologies': {
            'invalid_ont': {
                'column_name': 'nonexistent_col',
                'dataset_name': 'nonexistent_dataset',
                'ontology_type': 'invalid_type',
                'uri_template': 'invalid_template_without_placeholder'
            }
        },
        'import_strategy': {
            'update_strategy': 'INVALID_STRATEGY',
            'bulk_size': 'invalid_size',
            'multi_value_threshold': 2.0  # Out of range
        }
    }


@pytest.fixture
def circular_dependency_configuration():
    """Configuration with circular FK dependencies"""
    return {
        'version': '1.1',
        'workspace_columns': {
            'dataset_a': {
                'id': {'arkumu_type': 'A.id', 'is_anchor': True},
                'b_ref': {'arkumu_type': 'A.b_ref'}
            },
            'dataset_b': {
                'id': {'arkumu_type': 'B.id', 'is_anchor': True},
                'c_ref': {'arkumu_type': 'B.c_ref'}
            },
            'dataset_c': {
                'id': {'arkumu_type': 'C.id', 'is_anchor': True},
                'a_ref': {'arkumu_type': 'C.a_ref'}
            }
        },
        'selected_datasets': ['dataset_a', 'dataset_b', 'dataset_c'],
        'fk_relationships': {
            'fk_a_to_b': {
                'source_column': 'b_ref',
                'source_dataset': 'dataset_a',
                'target_column': 'id',
                'target_dataset': 'dataset_b',
                'relationship_type': 'relates_to'
            },
            'fk_b_to_c': {
                'source_column': 'c_ref',
                'source_dataset': 'dataset_b',
                'target_column': 'id',
                'target_dataset': 'dataset_c',
                'relationship_type': 'relates_to'
            },
            'fk_c_to_a': {
                'source_column': 'a_ref',
                'source_dataset': 'dataset_c',
                'target_column': 'id',
                'target_dataset': 'dataset_a',
                'relationship_type': 'relates_to'
            }
        },
        'relationship_contexts': {},
        'external_ontologies': {},
        'import_strategy': {}
    }


@pytest.fixture
def minimal_valid_configuration():
    """Minimal valid configuration for testing"""
    return {
        'version': '1.0',
        'workspace_columns': {
            'simple_dataset': {
                'name': {
                    'arkumu_type': 'Entity.name',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': True
                }
            }
        },
        'selected_datasets': ['simple_dataset'],
        'fk_relationships': {},
        'relationship_contexts': {},
        'external_ontologies': {},
        'import_strategy': {}
    }