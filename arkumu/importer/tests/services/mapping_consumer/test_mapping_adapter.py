"""
Tests for mapping adapter service.

Tests the MappingAdapter class which loads and adapts mapping configurations
from arkumu.metadata for execution.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from arkumu.metadata.models.mappings import Mapping
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter, MappingInfo
from arkumu.importer.services.mapping_consumer.config_translator import ExecutionConfig
from arkumu.importer.services.mapping_consumer.validation import ValidationResult


@pytest.fixture
def sample_mapping_config():
    """Sample mapping configuration"""
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
                }
            },
            'locations': {
                'city': {
                    'arkumu_type': 'Location.city',
                    'datatype': 'http://www.w3.org/2001/XMLSchema#string',
                    'is_anchor': True,
                    'is_multi_value': False,
                    'confidence': 0.85
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
                'confidence': 0.80
            }
        },
        'external_ontologies': {
            'orcid_1': {
                'column_name': 'orcid_id',
                'dataset_name': 'people',
                'ontology_type': 'orcid',
                'uri_template': 'https://orcid.org/{identifier}',
                'validation_enabled': True
            }
        },
        'import_strategy': {
            'update_strategy': 'SKIP_EXISTING',
            'link_topology': 'row',
            'bulk_size': 1000,
            'processing_strategy': 'entity_centric'
        }
    }


class TestMappingAdapter:
    """Test suite for MappingAdapter class"""

    @pytest.fixture
    def mapping_adapter(self):
        """Create a MappingAdapter instance"""
        return MappingAdapter()

    @pytest.fixture
    def test_mapping(self, test_user, test_organization, sample_mapping_config):
        """Create a test mapping"""
        return Mapping.objects.create(
            name='Test Mapping',
            description='Test mapping for unit tests',
            organization_id=test_organization.code,
            created_by=test_user,
            mapping_config=sample_mapping_config,
            validation_status='validated'
        )

    def test_init(self, mapping_adapter):
        """Test MappingAdapter initialization"""
        assert mapping_adapter.config_translator is not None
        assert mapping_adapter.validation_service is not None

    def test_load_mapping_config_success(self, mapping_adapter, test_mapping):
        """Test successful loading of mapping configuration"""
        config = mapping_adapter.load_mapping_config(test_mapping.id)
        
        assert config is not None
        assert isinstance(config, dict)
        assert config['version'] == '1.1'
        assert 'workspace_columns' in config
        assert 'selected_datasets' in config
        assert 'fk_relationships' in config
        
        # Check metadata was added
        assert '_metadata' in config
        metadata = config['_metadata']
        assert metadata['mapping_id'] == test_mapping.id
        assert metadata['mapping_name'] == test_mapping.name
        assert metadata['organization'] == test_mapping.organization_id
        assert metadata['created_by'] == test_mapping.created_by.username

    def test_load_mapping_config_not_found(self, mapping_adapter):
        """Test loading non-existent mapping"""
        with pytest.raises(ObjectDoesNotExist):
            mapping_adapter.load_mapping_config(99999)

    def test_load_mapping_config_invalid_format(self, mapping_adapter):
        """Test loading mapping with invalid configuration format"""
        from django.contrib.auth import get_user_model
        from arkumu.users.models import Organization
        
        # Create test objects directly to avoid fixture conflicts
        org, _ = Organization.objects.get_or_create(
            code='TEST_INVALID',
            defaults={'name': 'Test Org Invalid', 'domain': 'invalid.test'}
        )
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username='test_invalid_user',
            defaults={'email': 'invalid@test.com', 'organization': org}
        )
        
        invalid_mapping = Mapping.objects.create(
            name='Invalid Mapping',
            description='Invalid mapping configuration',
            organization_id=org.code,
            created_by=user,
            mapping_config="invalid_string",  # Should be dict
            validation_status='draft'
        )
        
        with pytest.raises(ValueError, match="invalid configuration format"):
            mapping_adapter.load_mapping_config(invalid_mapping.id)

    def test_get_mapping_info_success(self, mapping_adapter, test_mapping):
        """Test successful retrieval of mapping info"""
        info = mapping_adapter.get_mapping_info(test_mapping.id)
        
        assert isinstance(info, MappingInfo)
        assert info.id == test_mapping.id
        assert info.name == test_mapping.name
        assert info.organization == test_mapping.organization_id
        assert info.version == '1.1'
        assert info.datasets == ['people', 'locations']
        assert info.total_columns == 3  # name, age, city
        assert info.fk_relationships == 1
        assert info.external_ontologies == 1

    def test_get_mapping_info_not_found(self, mapping_adapter):
        """Test getting info for non-existent mapping"""
        with pytest.raises(ObjectDoesNotExist):
            mapping_adapter.get_mapping_info(99999)

    def test_list_mappings_for_organization(self, mapping_adapter):
        """Test listing mappings for organization"""
        from django.contrib.auth import get_user_model
        from arkumu.users.models import Organization
        
        # Create test objects directly
        org, _ = Organization.objects.get_or_create(
            code='TEST_LIST',
            defaults={'name': 'Test Org List', 'domain': 'list.test'}
        )
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username='test_list_user',
            defaults={'email': 'list@test.com', 'organization': org}
        )
        
        # Create multiple mappings
        mapping1 = Mapping.objects.create(
            name='Mapping 1',
            organization_id=org.code,
            created_by=user,
            mapping_config={'workspace_columns': {}, 'selected_datasets': []}
        )
        mapping2 = Mapping.objects.create(
            name='Mapping 2',
            organization_id=org.code,
            created_by=user,
            mapping_config={'workspace_columns': {}, 'selected_datasets': []}
        )
        
        # Create mapping for different organization
        other_org = 'OTHER_ORG'
        Mapping.objects.create(
            name='Other Mapping',
            organization_id=other_org,
            created_by=user,
            mapping_config={'workspace_columns': {}, 'selected_datasets': []}
        )
        
        mappings = mapping_adapter.list_mappings_for_organization(org.code)
        
        assert len(mappings) == 2
        mapping_names = [m.name for m in mappings]
        assert 'Mapping 1' in mapping_names
        assert 'Mapping 2' in mapping_names
        assert 'Other Mapping' not in mapping_names

    def test_list_mappings_for_organization_empty(self, mapping_adapter):
        """Test listing mappings for organization with no mappings"""
        mappings = mapping_adapter.list_mappings_for_organization('NONEXISTENT_ORG')
        assert mappings == []

    def test_list_mappings_for_organization_with_invalid_mapping(self, mapping_adapter):
        """Test listing mappings when some have invalid configurations"""
        from django.contrib.auth import get_user_model
        from arkumu.users.models import Organization
        
        # Create test objects directly
        org, _ = Organization.objects.get_or_create(
            code='TEST_MIXED',
            defaults={'name': 'Test Org Mixed', 'domain': 'mixed.test'}
        )
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username='test_mixed_user',
            defaults={'email': 'mixed@test.com', 'organization': org}
        )
        
        # Create valid mapping
        Mapping.objects.create(
            name='Valid Mapping',
            organization_id=org.code,
            created_by=user,
            mapping_config={'workspace_columns': {}, 'selected_datasets': []}
        )
        
        # Create invalid mapping
        Mapping.objects.create(
            name='Invalid Mapping',
            organization_id=org.code,
            created_by=user,
            mapping_config="invalid_string"
        )
        
        mappings = mapping_adapter.list_mappings_for_organization(org.code)
        
        # Should only return valid mappings
        assert len(mappings) == 1
        assert mappings[0].name == 'Valid Mapping'

    def test_validate_mapping_success(self, mapping_adapter, test_mapping):
        """Test successful mapping validation"""
        with patch.object(mapping_adapter.validation_service, 'validate_mapping_config') as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                summary="Mapping is valid"
            )
            
            result = mapping_adapter.validate_mapping(test_mapping.id)
            
            assert result.is_valid is True
            assert len(result.errors) == 0
            assert len(result.warnings) == 0
            assert result.summary == "Mapping is valid"
            mock_validate.assert_called_once()

    def test_validate_mapping_with_errors(self, mapping_adapter, test_mapping):
        """Test mapping validation with errors"""
        with patch.object(mapping_adapter.validation_service, 'validate_mapping_config') as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=False,
                errors=["Missing required field: workspace_columns"],
                warnings=["No anchor columns found"],
                summary="Mapping has validation errors"
            )
            
            result = mapping_adapter.validate_mapping(test_mapping.id)
            
            assert result.is_valid is False
            assert len(result.errors) == 1
            assert len(result.warnings) == 1
            assert "Missing required field" in result.errors[0]

    def test_validate_mapping_load_failure(self, mapping_adapter):
        """Test mapping validation when loading fails"""
        result = mapping_adapter.validate_mapping(99999)
        
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "Failed to load mapping" in result.errors[0]
        assert result.summary == "Mapping could not be loaded for validation"

    def test_translate_to_execution_config_success(self, mapping_adapter, test_mapping):
        """Test successful translation to execution config"""
        with patch.object(mapping_adapter.validation_service, 'validate_mapping_config') as mock_validate:
            mock_validate.return_value = ValidationResult(is_valid=True)
            
            with patch.object(mapping_adapter.config_translator, 'translate_mapping_config') as mock_translate:
                mock_execution_config = ExecutionConfig(
                    mapping_id=test_mapping.id,
                    mapping_name=test_mapping.name,
                    organization=test_mapping.organization_id
                )
                mock_translate.return_value = mock_execution_config
                
                result = mapping_adapter.translate_to_execution_config(test_mapping.id)
                
                assert result == mock_execution_config
                mock_validate.assert_called_once()
                mock_translate.assert_called_once()

    def test_translate_to_execution_config_validation_failure(self, mapping_adapter, test_mapping):
        """Test translation when validation fails"""
        with patch.object(mapping_adapter.validation_service, 'validate_mapping_config') as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=False,
                errors=["Validation error"],
                warnings=[],
                summary="Invalid mapping"
            )
            
            with pytest.raises(ValueError, match="Mapping .* validation failed"):
                mapping_adapter.translate_to_execution_config(test_mapping.id)

    def test_translate_to_execution_config_load_failure(self, mapping_adapter):
        """Test translation when loading fails"""
        with pytest.raises(ObjectDoesNotExist):
            mapping_adapter.translate_to_execution_config(99999)

    def test_get_mapping_summary_success(self, mapping_adapter, test_mapping):
        """Test successful mapping summary generation"""
        with patch.object(mapping_adapter, 'get_mapping_info') as mock_info:
            mock_info.return_value = MappingInfo(
                id=test_mapping.id,
                name=test_mapping.name,
                organization=test_mapping.organization_id,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                version='1.1',
                datasets=['people', 'locations'],
                total_columns=3,
                fk_relationships=1,
                external_ontologies=1
            )
            
            with patch.object(mapping_adapter, 'validate_mapping') as mock_validate:
                mock_validate.return_value = ValidationResult(
                    is_valid=True,
                    errors=[],
                    warnings=['Minor warning'],
                    summary="Mapping is valid"
                )
                
                summary = mapping_adapter.get_mapping_summary(test_mapping.id)
                
                assert 'mapping_info' in summary
                assert 'validation' in summary
                assert 'execution_ready' in summary
                assert 'complexity_score' in summary
                
                assert summary['validation']['is_valid'] is True
                assert summary['validation']['error_count'] == 0
                assert summary['validation']['warning_count'] == 1
                assert summary['execution_ready'] is True
                assert summary['complexity_score'] in ['low', 'medium', 'high']

    def test_get_mapping_summary_failure(self, mapping_adapter):
        """Test mapping summary generation when it fails"""
        summary = mapping_adapter.get_mapping_summary(99999)
        
        assert 'error' in summary
        assert summary['execution_ready'] is False

    def test_calculate_complexity_score_low(self, mapping_adapter):
        """Test complexity score calculation - low complexity"""
        info = MappingInfo(
            id=1,
            name='Test',
            organization='TEST',
            created_at=datetime.now(),
            updated_at=datetime.now(),
            version='1.1',
            datasets=['dataset1'],  # 1 dataset
            total_columns=5,  # 5 columns
            fk_relationships=0,  # No FK relationships
            external_ontologies=0  # No external ontologies
        )
        
        score = mapping_adapter._calculate_complexity_score(info)
        assert score == 'low'

    def test_calculate_complexity_score_medium(self, mapping_adapter):
        """Test complexity score calculation - medium complexity"""
        info = MappingInfo(
            id=1,
            name='Test',
            organization='TEST',
            created_at=datetime.now(),
            updated_at=datetime.now(),
            version='1.1',
            datasets=['dataset1', 'dataset2'],  # 2 datasets
            total_columns=15,  # 15 columns
            fk_relationships=2,  # 2 FK relationships
            external_ontologies=0  # No external ontologies
        )
        
        score = mapping_adapter._calculate_complexity_score(info)
        assert score == 'medium'

    def test_calculate_complexity_score_high(self, mapping_adapter):
        """Test complexity score calculation - high complexity"""
        info = MappingInfo(
            id=1,
            name='Test',
            organization='TEST',
            created_at=datetime.now(),
            updated_at=datetime.now(),
            version='1.1',
            datasets=['dataset1', 'dataset2', 'dataset3', 'dataset4'],  # 4 datasets
            total_columns=25,  # 25 columns
            fk_relationships=8,  # 8 FK relationships
            external_ontologies=2  # 2 external ontologies
        )
        
        score = mapping_adapter._calculate_complexity_score(info)
        assert score == 'high'


class TestMappingInfo:
    """Test suite for MappingInfo dataclass"""

    def test_mapping_info_creation(self):
        """Test MappingInfo creation"""
        now = datetime.now()
        info = MappingInfo(
            id=1,
            name='Test Mapping',
            organization='TEST_ORG',
            created_at=now,
            updated_at=now,
            version='1.1',
            datasets=['dataset1', 'dataset2'],
            total_columns=10,
            fk_relationships=2,
            external_ontologies=1
        )
        
        assert info.id == 1
        assert info.name == 'Test Mapping'
        assert info.organization == 'TEST_ORG'
        assert info.created_at == now
        assert info.updated_at == now
        assert info.version == '1.1'
        assert info.datasets == ['dataset1', 'dataset2']
        assert info.total_columns == 10
        assert info.fk_relationships == 2
        assert info.external_ontologies == 1


class TestMappingAdapterIntegration:
    """Integration tests for MappingAdapter"""

    def test_full_workflow(self, sample_mapping_config):
        """Test full workflow from mapping creation to execution config"""
        from django.contrib.auth import get_user_model
        from arkumu.users.models import Organization
        
        # Create test objects directly
        org, _ = Organization.objects.get_or_create(
            code='TEST_WORKFLOW',
            defaults={'name': 'Test Org Workflow', 'domain': 'workflow.test'}
        )
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username='test_workflow_user',
            defaults={'email': 'workflow@test.com', 'organization': org}
        )
        
        # Create mapping
        mapping = Mapping.objects.create(
            name='Integration Test Mapping',
            description='Full workflow test',
            organization_id=org.code,
            created_by=user,
            mapping_config=sample_mapping_config,
            validation_status='validated'
        )
        
        # Initialize adapter
        adapter = MappingAdapter()
        
        # Load configuration
        config = adapter.load_mapping_config(mapping.id)
        assert config is not None
        assert config['version'] == '1.1'
        
        # Get mapping info
        info = adapter.get_mapping_info(mapping.id)
        assert info.name == 'Integration Test Mapping'
        assert len(info.datasets) == 2
        
        # Validate mapping - expect validation errors due to missing columns referenced in FK
        validation_result = adapter.validate_mapping(mapping.id)
        # The sample config has FK relationships and external ontologies that reference
        # non-existent columns, so validation should fail
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
        
        # Try to translate to execution config - should fail due to validation errors
        with pytest.raises(ValueError, match="validation failed"):
            adapter.translate_to_execution_config(mapping.id)
        
        # Get summary
        summary = adapter.get_mapping_summary(mapping.id)
        assert summary['execution_ready'] is False  # Should be false due to validation errors
        assert 'complexity_score' in summary