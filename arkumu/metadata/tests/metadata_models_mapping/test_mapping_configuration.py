import unittest
import json
import uuid
from unittest.mock import Mock, patch
from datetime import datetime

from arkumu.metadata.services.metadata_models_mapping.mapping_configuration import (
    MappingConfigurationService,
    PatternRule,
    MappingRule,
    RelationshipTemplate,
    EntityResolutionRule,
    TransformationConfiguration,
    PatternType,
    MappingType
)


class TestPatternRule(unittest.TestCase):
    """Test PatternRule dataclass"""
    
    def test_pattern_rule_creation(self):
        """Test basic pattern rule creation"""
        rule = PatternRule(
            id="test-id",
            name="Test Rule",
            pattern_type=PatternType.PREFIX,
            pattern_value="test_",
            target_fields=["name", "uri"],
            description="Test description"
        )
        
        self.assertEqual(rule.id, "test-id")
        self.assertEqual(rule.name, "Test Rule")
        self.assertEqual(rule.pattern_type, PatternType.PREFIX)
        self.assertEqual(rule.pattern_value, "test_")
        self.assertEqual(rule.target_fields, ["name", "uri"])
        self.assertEqual(rule.description, "Test description")
        self.assertTrue(rule.active)
    
    def test_pattern_rule_defaults(self):
        """Test pattern rule with default values"""
        rule = PatternRule(
            id="test-id",
            name="Test Rule",
            pattern_type=PatternType.EXACT,
            pattern_value="exact_match",
            target_fields=["value"]
        )
        
        self.assertEqual(rule.description, "")
        self.assertTrue(rule.active)


class TestMappingRule(unittest.TestCase):
    """Test MappingRule dataclass"""
    
    def setUp(self):
        self.pattern_rule = PatternRule(
            id="pattern-id",
            name="Pattern Rule",
            pattern_type=PatternType.CONTAINS,
            pattern_value="address",
            target_fields=["name"]
        )
    
    def test_mapping_rule_creation(self):
        """Test basic mapping rule creation"""
        rule = MappingRule(
            id="mapping-id",
            name="Address Mapping",
            mapping_type=MappingType.TYPE_ASSIGNMENT,
            pattern_rule=self.pattern_rule,
            target_semantic_type="Address",
            target_predicate="hasAddress",
            conditions={"column_type": "varchar"},
            metadata={"confidence": 0.9},
            priority=50
        )
        
        self.assertEqual(rule.id, "mapping-id")
        self.assertEqual(rule.name, "Address Mapping")
        self.assertEqual(rule.mapping_type, MappingType.TYPE_ASSIGNMENT)
        self.assertEqual(rule.pattern_rule, self.pattern_rule)
        self.assertEqual(rule.target_semantic_type, "Address")
        self.assertEqual(rule.target_predicate, "hasAddress")
        self.assertEqual(rule.conditions, {"column_type": "varchar"})
        self.assertEqual(rule.metadata, {"confidence": 0.9})
        self.assertEqual(rule.priority, 50)
        self.assertTrue(rule.active)
    
    def test_mapping_rule_defaults(self):
        """Test mapping rule with default values"""
        rule = MappingRule(
            id="mapping-id",
            name="Simple Mapping",
            mapping_type=MappingType.PROPERTY_MAPPING,
            pattern_rule=self.pattern_rule,
            target_semantic_type="Property"
        )
        
        self.assertIsNone(rule.target_predicate)
        self.assertIsNone(rule.conditions)
        self.assertIsNone(rule.metadata)
        self.assertEqual(rule.priority, 100)
        self.assertTrue(rule.active)


class TestRelationshipTemplate(unittest.TestCase):
    """Test RelationshipTemplate dataclass"""
    
    def test_relationship_template_creation(self):
        """Test basic relationship template creation"""
        template = RelationshipTemplate(
            id="rel-template-id",
            name="Manager Relationship",
            source_column="employee_id",
            target_column="manager_id",
            relationship_predicate="reportsTo",
            source_entity_type="Employee",
            target_entity_type="Manager",
            relationship_metadata_columns=["start_date", "role"],
            bidirectional=True,
            description="Employee reports to manager relationship"
        )
        
        self.assertEqual(template.id, "rel-template-id")
        self.assertEqual(template.name, "Manager Relationship")
        self.assertEqual(template.source_column, "employee_id")
        self.assertEqual(template.target_column, "manager_id")
        self.assertEqual(template.relationship_predicate, "reportsTo")
        self.assertEqual(template.source_entity_type, "Employee")
        self.assertEqual(template.target_entity_type, "Manager")
        self.assertEqual(template.relationship_metadata_columns, ["start_date", "role"])
        self.assertTrue(template.bidirectional)
        self.assertEqual(template.description, "Employee reports to manager relationship")
    
    def test_relationship_template_defaults(self):
        """Test relationship template with default values"""
        template = RelationshipTemplate(
            id="rel-id",
            name="Simple Relationship",
            source_column="source_id",
            target_column="target_id",
            relationship_predicate="relatedTo",
            source_entity_type="SourceType",
            target_entity_type="TargetType"
        )
        
        self.assertIsNone(template.relationship_metadata_columns)
        self.assertFalse(template.bidirectional)
        self.assertEqual(template.description, "")
    
    def test_relationship_template_validation(self):
        """Test relationship template field validation"""
        # Test required fields are present
        template = RelationshipTemplate(
            id="test-id",
            name="Test Relationship",
            source_column="src",
            target_column="tgt",
            relationship_predicate="connects",
            source_entity_type="Source",
            target_entity_type="Target"
        )
        
        # Verify all required fields have values
        self.assertIsNotNone(template.id)
        self.assertIsNotNone(template.name)
        self.assertIsNotNone(template.source_column)
        self.assertIsNotNone(template.target_column)
        self.assertIsNotNone(template.relationship_predicate)
        self.assertIsNotNone(template.source_entity_type)
        self.assertIsNotNone(template.target_entity_type)


class TestEntityResolutionRule(unittest.TestCase):
    """Test EntityResolutionRule dataclass"""
    
    def test_entity_resolution_rule_creation(self):
        """Test basic entity resolution rule creation"""
        rule = EntityResolutionRule(
            id="resolution-rule-id",
            name="Customer Resolution",
            source_table="orders",
            source_column="customer_name",
            target_table="customers",
            target_column="name",
            resolution_strategy="fuzzy_match",
            fallback_strategy="create_placeholder",
            confidence_threshold=0.85
        )
        
        self.assertEqual(rule.id, "resolution-rule-id")
        self.assertEqual(rule.name, "Customer Resolution")
        self.assertEqual(rule.source_table, "orders")
        self.assertEqual(rule.source_column, "customer_name")
        self.assertEqual(rule.target_table, "customers")
        self.assertEqual(rule.target_column, "name")
        self.assertEqual(rule.resolution_strategy, "fuzzy_match")
        self.assertEqual(rule.fallback_strategy, "create_placeholder")
        self.assertEqual(rule.confidence_threshold, 0.85)
    
    def test_entity_resolution_rule_defaults(self):
        """Test entity resolution rule with default values"""
        rule = EntityResolutionRule(
            id="rule-id",
            name="Default Resolution",
            source_table="table1",
            source_column="col1",
            target_table="table2",
            target_column="col2",
            resolution_strategy="exact_match"  # Required parameter
        )
        
        self.assertEqual(rule.resolution_strategy, "exact_match")
        self.assertEqual(rule.fallback_strategy, "create_placeholder")
        self.assertEqual(rule.confidence_threshold, 0.8)
    
    def test_entity_resolution_strategies(self):
        """Test different resolution strategies"""
        strategies = ["exact_match", "fuzzy_match", "pattern_match"]
        fallback_strategies = ["skip", "create_placeholder", "error"]
        
        for strategy in strategies:
            rule = EntityResolutionRule(
                id=f"rule-{strategy}",
                name=f"Rule {strategy}",
                source_table="source",
                source_column="src_col",
                target_table="target",
                target_column="tgt_col",
                resolution_strategy=strategy
            )
            self.assertEqual(rule.resolution_strategy, strategy)
        
        for fallback in fallback_strategies:
            rule = EntityResolutionRule(
                id=f"rule-{fallback}",
                name=f"Rule {fallback}",
                source_table="source",
                source_column="src_col",
                target_table="target",
                target_column="tgt_col",
                resolution_strategy="exact_match",  # Required parameter
                fallback_strategy=fallback
            )
            self.assertEqual(rule.fallback_strategy, fallback)
    
    def test_confidence_threshold_validation(self):
        """Test confidence threshold bounds"""
        # Test valid threshold
        rule = EntityResolutionRule(
            id="valid-rule",
            name="Valid Rule",
            source_table="source",
            source_column="src_col",
            target_table="target",
            target_column="tgt_col",
            resolution_strategy="fuzzy_match",
            confidence_threshold=0.5
        )
        self.assertEqual(rule.confidence_threshold, 0.5)
        
        # Test boundary values
        rule_min = EntityResolutionRule(
            id="min-rule",
            name="Min Rule",
            source_table="source",
            source_column="src_col",
            target_table="target",
            target_column="tgt_col",
            resolution_strategy="exact_match",
            confidence_threshold=0.0
        )
        self.assertEqual(rule_min.confidence_threshold, 0.0)
        
        rule_max = EntityResolutionRule(
            id="max-rule",
            name="Max Rule",
            source_table="source",
            source_column="src_col",
            target_table="target",
            target_column="tgt_col",
            resolution_strategy="pattern_match",
            confidence_threshold=1.0
        )
        self.assertEqual(rule_max.confidence_threshold, 1.0)


class TestTransformationConfiguration(unittest.TestCase):
    """Test TransformationConfiguration dataclass"""
    
    def test_transformation_configuration_creation(self):
        """Test basic transformation configuration creation"""
        # Create sample components
        pattern_rule = PatternRule(
            id="pattern-1",
            name="Pattern",
            pattern_type=PatternType.PREFIX,
            pattern_value="user_",
            target_fields=["name"]
        )
        
        mapping_rule = MappingRule(
            id="mapping-1",
            name="User Mapping",
            mapping_type=MappingType.TYPE_ASSIGNMENT,
            pattern_rule=pattern_rule,
            target_semantic_type="User"
        )
        
        relationship_template = RelationshipTemplate(
            id="rel-1",
            name="User Manager",
            source_column="user_id",
            target_column="manager_id",
            relationship_predicate="reportsTo",
            source_entity_type="User",
            target_entity_type="Manager"
        )
        
        entity_resolution_rule = EntityResolutionRule(
            id="resolution-1",
            name="User Resolution",
            source_table="employees",
            source_column="name",
            target_table="users",
            target_column="full_name",
            resolution_strategy="fuzzy_match"
        )
        
        config = TransformationConfiguration(
            id="config-1",
            name="Complete Configuration",
            description="Configuration with all components",
            mapping_rules=[mapping_rule],
            relationship_templates=[relationship_template],
            entity_resolution_rules=[entity_resolution_rule],
            global_settings={"max_batch_size": 1000, "enable_logging": True},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T12:00:00"
        )
        
        self.assertEqual(config.id, "config-1")
        self.assertEqual(config.name, "Complete Configuration")
        self.assertEqual(config.description, "Configuration with all components")
        self.assertEqual(len(config.mapping_rules), 1)
        self.assertEqual(len(config.relationship_templates), 1)
        self.assertEqual(len(config.entity_resolution_rules), 1)
        self.assertEqual(config.global_settings["max_batch_size"], 1000)
        self.assertTrue(config.global_settings["enable_logging"])
        self.assertEqual(config.created_at, "2024-01-01T00:00:00")
        self.assertEqual(config.updated_at, "2024-01-01T12:00:00")
        
        # Verify components
        self.assertEqual(config.mapping_rules[0].id, "mapping-1")
        self.assertEqual(config.relationship_templates[0].id, "rel-1")
        self.assertEqual(config.entity_resolution_rules[0].id, "resolution-1")
    
    def test_empty_transformation_configuration(self):
        """Test transformation configuration with empty collections"""
        config = TransformationConfiguration(
            id="empty-config",
            name="Empty Configuration",
            description="Configuration with no rules",
            mapping_rules=[],
            relationship_templates=[],
            entity_resolution_rules=[],
            global_settings={},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00"
        )
        
        self.assertEqual(len(config.mapping_rules), 0)
        self.assertEqual(len(config.relationship_templates), 0)
        self.assertEqual(len(config.entity_resolution_rules), 0)
        self.assertEqual(len(config.global_settings), 0)
    
    def test_configuration_component_access(self):
        """Test accessing configuration components"""
        # Create a configuration with multiple components
        mapping_rules = []
        relationship_templates = []
        
        for i in range(3):
            pattern_rule = PatternRule(
                id=f"pattern-{i}",
                name=f"Pattern {i}",
                pattern_type=PatternType.EXACT,
                pattern_value=f"value_{i}",
                target_fields=["name"]
            )
            
            mapping_rule = MappingRule(
                id=f"mapping-{i}",
                name=f"Mapping {i}",
                mapping_type=MappingType.PROPERTY_MAPPING,
                pattern_rule=pattern_rule,
                target_semantic_type=f"Type{i}"
            )
            mapping_rules.append(mapping_rule)
            
            relationship_template = RelationshipTemplate(
                id=f"rel-{i}",
                name=f"Relationship {i}",
                source_column=f"src_{i}",
                target_column=f"tgt_{i}",
                relationship_predicate=f"predicate_{i}",
                source_entity_type=f"Source{i}",
                target_entity_type=f"Target{i}"
            )
            relationship_templates.append(relationship_template)
        
        config = TransformationConfiguration(
            id="multi-config",
            name="Multi-component Configuration",
            description="Configuration with multiple components",
            mapping_rules=mapping_rules,
            relationship_templates=relationship_templates,
            entity_resolution_rules=[],
            global_settings={"component_count": 3},
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00"
        )
        
        # Test component counts
        self.assertEqual(len(config.mapping_rules), 3)
        self.assertEqual(len(config.relationship_templates), 3)
        
        # Test component access
        for i in range(3):
            self.assertEqual(config.mapping_rules[i].id, f"mapping-{i}")
            self.assertEqual(config.relationship_templates[i].id, f"rel-{i}")
            self.assertEqual(config.mapping_rules[i].target_semantic_type, f"Type{i}")
            self.assertEqual(config.relationship_templates[i].relationship_predicate, f"predicate_{i}")


class TestMappingConfigurationService(unittest.TestCase):
    """Test MappingConfigurationService core functionality"""
    
    def setUp(self):
        self.service = MappingConfigurationService()
    
    def test_service_initialization(self):
        """Test service initialization"""
        self.assertEqual(len(self.service._configurations), 0)
        self.assertIsNone(self.service._active_configuration_id)
        self.assertIsNone(self.service.session_storage)
    
    def test_service_initialization_with_session(self):
        """Test service initialization with session storage"""
        mock_session = Mock()
        service = MappingConfigurationService(session_storage=mock_session)
        self.assertEqual(service.session_storage, mock_session)
    
    @patch('uuid.uuid4')
    def test_create_pattern_rule(self, mock_uuid):
        """Test pattern rule creation"""
        mock_uuid.return_value = Mock(spec=uuid.UUID)
        mock_uuid.return_value.__str__ = Mock(return_value="test-uuid")
        
        rule = self.service.create_pattern_rule(
            name="Test Pattern",
            pattern_type="prefix",
            pattern_value="test_",
            target_fields=["name", "uri"],
            description="Test description"
        )
        
        self.assertEqual(rule.id, "test-uuid")
        self.assertEqual(rule.name, "Test Pattern")
        self.assertEqual(rule.pattern_type, PatternType.PREFIX)
        self.assertEqual(rule.pattern_value, "test_")
        self.assertEqual(rule.target_fields, ["name", "uri"])
        self.assertEqual(rule.description, "Test description")
    
    @patch('uuid.uuid4')
    def test_create_mapping_rule(self, mock_uuid):
        """Test mapping rule creation"""
        mock_uuid.return_value = Mock(spec=uuid.UUID)
        mock_uuid.return_value.__str__ = Mock(return_value="mapping-uuid")
        
        pattern_rule = PatternRule(
            id="pattern-id",
            name="Pattern",
            pattern_type=PatternType.SUFFIX,
            pattern_value="_id",
            target_fields=["name"]
        )
        
        rule = self.service.create_mapping_rule(
            name="ID Mapping",
            pattern_rule=pattern_rule,
            mapping_type="type_assignment",
            target_semantic_type="Identifier",
            target_predicate="hasId",
            conditions={"not_null": True},
            priority=20
        )
        
        self.assertEqual(rule.id, "mapping-uuid")
        self.assertEqual(rule.name, "ID Mapping")
        self.assertEqual(rule.mapping_type, MappingType.TYPE_ASSIGNMENT)
        self.assertEqual(rule.pattern_rule, pattern_rule)
        self.assertEqual(rule.target_semantic_type, "Identifier")
        self.assertEqual(rule.target_predicate, "hasId")
        self.assertEqual(rule.conditions, {"not_null": True})
        self.assertEqual(rule.priority, 20)
    
    @patch('uuid.uuid4')
    @patch('datetime.datetime')
    def test_create_configuration(self, mock_datetime, mock_uuid):
        """Test configuration creation"""
        mock_uuid.return_value = Mock(spec=uuid.UUID)
        mock_uuid.return_value.__str__ = Mock(return_value="config-uuid")
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"
        
        config = self.service.create_configuration(
            name="Test Configuration",
            description="Test description"
        )
        
        self.assertEqual(config.id, "config-uuid")
        self.assertEqual(config.name, "Test Configuration")
        self.assertEqual(config.description, "Test description")
        self.assertEqual(len(config.mapping_rules), 0)
        self.assertEqual(len(config.relationship_templates), 0)
        self.assertEqual(len(config.entity_resolution_rules), 0)
        self.assertEqual(config.global_settings, {})
        self.assertEqual(config.created_at, "2024-01-01T00:00:00")
        self.assertEqual(config.updated_at, "2024-01-01T00:00:00")
        
        # Check that configuration is stored and set as active
        self.assertIn("config-uuid", self.service._configurations)
        self.assertEqual(self.service._active_configuration_id, "config-uuid")
    
    def test_get_configuration(self):
        """Test getting configuration by ID"""
        config = self.service.create_configuration("Test Config")
        config_id = config.id
        
        retrieved_config = self.service.get_configuration(config_id)
        self.assertEqual(retrieved_config, config)
        
        # Test getting non-existent configuration
        non_existent = self.service.get_configuration("non-existent-id")
        self.assertIsNone(non_existent)
    
    def test_get_active_configuration(self):
        """Test getting active configuration"""
        # No active configuration initially
        self.assertIsNone(self.service.get_active_configuration())
        
        # Create configuration (becomes active)
        config = self.service.create_configuration("Active Config")
        active_config = self.service.get_active_configuration()
        self.assertEqual(active_config, config)
    
    def test_set_active_configuration(self):
        """Test setting active configuration"""
        config1 = self.service.create_configuration("Config 1")
        config2 = self.service.create_configuration("Config 2")
        
        # Config 2 is currently active
        self.assertEqual(self.service._active_configuration_id, config2.id)
        
        # Set config 1 as active
        result = self.service.set_active_configuration(config1.id)
        self.assertTrue(result)
        self.assertEqual(self.service._active_configuration_id, config1.id)
        
        # Try to set non-existent configuration as active
        result = self.service.set_active_configuration("non-existent")
        self.assertFalse(result)
        self.assertEqual(self.service._active_configuration_id, config1.id)
    
    @patch('datetime.datetime')
    def test_add_mapping_rule_to_configuration(self, mock_datetime):
        """Test adding mapping rule to configuration"""
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
        
        config = self.service.create_configuration("Test Config")
        
        pattern_rule = PatternRule(
            id="pattern-1",
            name="Pattern",
            pattern_type=PatternType.EXACT,
            pattern_value="name",
            target_fields=["name"]
        )
        
        mapping_rule = MappingRule(
            id="mapping-1",
            name="Name Mapping",
            mapping_type=MappingType.PROPERTY_MAPPING,
            pattern_rule=pattern_rule,
            target_semantic_type="Name"
        )
        
        result = self.service.add_mapping_rule_to_configuration(config.id, mapping_rule)
        self.assertTrue(result)
        
        updated_config = self.service.get_configuration(config.id)
        self.assertEqual(len(updated_config.mapping_rules), 1)
        self.assertEqual(updated_config.mapping_rules[0], mapping_rule)
        self.assertEqual(updated_config.updated_at, "2024-01-01T12:00:00")
        
        # Test adding to non-existent configuration
        result = self.service.add_mapping_rule_to_configuration("non-existent", mapping_rule)
        self.assertFalse(result)
    
    @patch('uuid.uuid4')
    def test_create_relationship_template(self, mock_uuid):
        """Test relationship template creation"""
        mock_uuid.return_value = Mock(spec=uuid.UUID)
        mock_uuid.return_value.__str__ = Mock(return_value="rel-template-uuid")
        
        template = self.service.create_relationship_template(
            name="Employee Manager",
            source_column="employee_id",
            target_column="manager_id",
            relationship_predicate="reportsTo",
            source_entity_type="Employee",
            target_entity_type="Manager",
            metadata_columns=["start_date", "department"],  # Correct parameter name
            bidirectional=False
        )
        
        self.assertEqual(template.id, "rel-template-uuid")
        self.assertEqual(template.name, "Employee Manager")
        self.assertEqual(template.source_column, "employee_id")
        self.assertEqual(template.target_column, "manager_id")
        self.assertEqual(template.relationship_predicate, "reportsTo")
        self.assertEqual(template.source_entity_type, "Employee")
        self.assertEqual(template.target_entity_type, "Manager")
        self.assertEqual(template.relationship_metadata_columns, ["start_date", "department"])
        self.assertFalse(template.bidirectional)
    
    @patch('uuid.uuid4')
    def test_create_entity_resolution_rule(self, mock_uuid):
        """Test entity resolution rule creation"""
        mock_uuid.return_value = Mock(spec=uuid.UUID)
        mock_uuid.return_value.__str__ = Mock(return_value="resolution-rule-uuid")
        
        rule = self.service.create_entity_resolution_rule(
            name="Customer Name Resolution",
            source_table="orders",
            source_column="customer_name",
            target_table="customers",
            target_column="full_name",
            resolution_strategy="fuzzy_match",
            fallback_strategy="create_placeholder"
            # Note: confidence_threshold is not a parameter in the service method
        )
        
        self.assertEqual(rule.id, "resolution-rule-uuid")
        self.assertEqual(rule.name, "Customer Name Resolution")
        self.assertEqual(rule.source_table, "orders")
        self.assertEqual(rule.source_column, "customer_name")
        self.assertEqual(rule.target_table, "customers")
        self.assertEqual(rule.target_column, "full_name")
        self.assertEqual(rule.resolution_strategy, "fuzzy_match")
        self.assertEqual(rule.fallback_strategy, "create_placeholder")
        self.assertEqual(rule.confidence_threshold, 0.8)  # Default value
    
    @patch('datetime.datetime')
    def test_add_relationship_template_to_configuration(self, mock_datetime):
        """Test adding relationship template to configuration"""
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T15:00:00"
        
        config = self.service.create_configuration("Relationship Test Config")
        
        template = RelationshipTemplate(
            id="template-1",
            name="User Friend",
            source_column="user_id",
            target_column="friend_id",
            relationship_predicate="friendOf",
            source_entity_type="User",
            target_entity_type="User",
            bidirectional=True
        )
        
        result = self.service.add_relationship_template_to_configuration(config.id, template)
        self.assertTrue(result)
        
        updated_config = self.service.get_configuration(config.id)
        self.assertEqual(len(updated_config.relationship_templates), 1)
        self.assertEqual(updated_config.relationship_templates[0], template)
        self.assertEqual(updated_config.updated_at, "2024-01-01T15:00:00")
        
        # Test adding to non-existent configuration
        result = self.service.add_relationship_template_to_configuration("non-existent", template)
        self.assertFalse(result)
    
    @patch('datetime.datetime')
    def test_add_entity_resolution_rule_to_configuration(self, mock_datetime):
        """Test adding entity resolution rule to configuration"""
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T16:00:00"
        
        config = self.service.create_configuration("Resolution Test Config")
        
        resolution_rule = EntityResolutionRule(
            id="resolution-1",
            name="Product Resolution",
            source_table="sales",
            source_column="product_name",
            target_table="products",
            target_column="name",
            resolution_strategy="fuzzy_match",
            confidence_threshold=0.8
        )
        
        result = self.service.add_entity_resolution_rule_to_configuration(config.id, resolution_rule)
        self.assertTrue(result)
        
        updated_config = self.service.get_configuration(config.id)
        self.assertEqual(len(updated_config.entity_resolution_rules), 1)
        self.assertEqual(updated_config.entity_resolution_rules[0], resolution_rule)
        self.assertEqual(updated_config.updated_at, "2024-01-01T16:00:00")
        
        # Test adding to non-existent configuration
        result = self.service.add_entity_resolution_rule_to_configuration("non-existent", resolution_rule)
        self.assertFalse(result)
    
    def test_configuration_with_templates_and_resolution_rules(self):
        """Test configuration operations with relationship templates and entity resolution rules"""
        config = self.service.create_configuration("Full Test Config")
        
        # Create relationship template
        template = self.service.create_relationship_template(
            name="User Manager",
            source_column="user_id",
            target_column="manager_id",
            relationship_predicate="reportsTo",
            source_entity_type="User",
            target_entity_type="Manager"
        )
        
        # Create entity resolution rule
        resolution_rule = self.service.create_entity_resolution_rule(
            name="User Resolution",
            source_table="employees",
            source_column="name",
            target_table="users",
            target_column="full_name",
            resolution_strategy="fuzzy_match"
        )
        
        # Add to configuration
        self.service.add_relationship_template_to_configuration(config.id, template)
        self.service.add_entity_resolution_rule_to_configuration(config.id, resolution_rule)
        
        # Verify they were added
        updated_config = self.service.get_configuration(config.id)
        self.assertEqual(len(updated_config.relationship_templates), 1)
        self.assertEqual(len(updated_config.entity_resolution_rules), 1)
        
        # Verify the components
        self.assertEqual(updated_config.relationship_templates[0].id, template.id)
        self.assertEqual(updated_config.entity_resolution_rules[0].id, resolution_rule.id)
        
        # Test adding to non-existent configuration
        result = self.service.add_relationship_template_to_configuration("non-existent", template)
        self.assertFalse(result)
        
        result = self.service.add_entity_resolution_rule_to_configuration("non-existent", resolution_rule)
        self.assertFalse(result)


class TestPatternMatching(unittest.TestCase):
    """Test pattern matching logic - critical for the system"""
    
    def setUp(self):
        self.service = MappingConfigurationService()
        self.config = self.service.create_configuration("Pattern Test Config")
        
        # Create various pattern rules for testing
        self.prefix_rule = self.service.create_mapping_rule(
            name="Prefix Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Prefix Pattern",
                pattern_type="prefix",
                pattern_value="user_",
                target_fields=["name"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="User",
            priority=10
        )
        
        self.suffix_rule = self.service.create_mapping_rule(
            name="Suffix Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Suffix Pattern",
                pattern_type="suffix",
                pattern_value="_id",
                target_fields=["name"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="Identifier",
            priority=20
        )
        
        self.contains_rule = self.service.create_mapping_rule(
            name="Contains Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Contains Pattern",
                pattern_type="contains",
                pattern_value="address",
                target_fields=["name"]
            ),
            mapping_type="property_mapping",
            target_semantic_type="Address",
            priority=30
        )
        
        self.exact_rule = self.service.create_mapping_rule(
            name="Exact Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Exact Pattern",
                pattern_type="exact",
                pattern_value="email",
                target_fields=["name"]
            ),
            mapping_type="property_mapping",
            target_semantic_type="Email",
            priority=5
        )
        
        self.regex_rule = self.service.create_mapping_rule(
            name="Regex Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Regex Pattern",
                pattern_type="regex",
                pattern_value=r"^phone_\d+$",
                target_fields=["name"]
            ),
            mapping_type="property_mapping",
            target_semantic_type="Phone",
            priority=40
        )
        
        # Add all rules to configuration
        for rule in [self.prefix_rule, self.suffix_rule, self.contains_rule, 
                    self.exact_rule, self.regex_rule]:
            self.service.add_mapping_rule_to_configuration(self.config.id, rule)
    
    def test_prefix_pattern_matching(self):
        """Test prefix pattern matching"""
        matches = self.service.get_matching_rules("user_name", "name")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, self.prefix_rule.id)
        
        # Should not match
        no_matches = self.service.get_matching_rules("name_user", "name")
        self.assertEqual(len(no_matches), 0)
    
    def test_suffix_pattern_matching(self):
        """Test suffix pattern matching"""
        matches = self.service.get_matching_rules("customer_id", "name")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, self.suffix_rule.id)
        
        # Should not match
        no_matches = self.service.get_matching_rules("id_customer", "name")
        self.assertEqual(len(no_matches), 0)
    
    def test_contains_pattern_matching(self):
        """Test contains pattern matching"""
        matches = self.service.get_matching_rules("home_address", "name")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, self.contains_rule.id)
        
        matches = self.service.get_matching_rules("address_line_1", "name")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, self.contains_rule.id)
        
        # Should not match
        no_matches = self.service.get_matching_rules("location", "name")
        self.assertEqual(len(no_matches), 0)
    
    def test_exact_pattern_matching(self):
        """Test exact pattern matching"""
        matches = self.service.get_matching_rules("email", "name")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, self.exact_rule.id)
        
        # Should not match exact rule (but might match contains rule for "address")
        no_exact_matches = self.service.get_matching_rules("email_something", "name")
        # Check that exact rule is not in the matches
        exact_rule_in_matches = any(match.id == self.exact_rule.id for match in no_exact_matches)
        self.assertFalse(exact_rule_in_matches)
    
    def test_regex_pattern_matching(self):
        """Test regex pattern matching"""
        matches = self.service.get_matching_rules("phone_123", "name")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, self.regex_rule.id)
        
        matches = self.service.get_matching_rules("phone_0", "name")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, self.regex_rule.id)
        
        # Should not match
        no_matches = self.service.get_matching_rules("phone_abc", "name")
        self.assertEqual(len(no_matches), 0)
        
        no_matches = self.service.get_matching_rules("phone", "name")
        self.assertEqual(len(no_matches), 0)
    
    def test_multiple_pattern_matches_priority_sorting(self):
        """Test that multiple matches are sorted by priority"""
        # Create a value that matches multiple patterns
        # "user_address_id" should match prefix (user_), contains (address), and suffix (_id)
        
        matches = self.service.get_matching_rules("user_address_id", "name")
        
        # Should have 3 matches
        self.assertEqual(len(matches), 3)
        
        # Check they are sorted by priority (lower number = higher priority)
        priorities = [match.priority for match in matches]
        self.assertEqual(priorities, [10, 20, 30])  # prefix=10, suffix=20, contains=30
        
        # Check specific rules
        self.assertEqual(matches[0].id, self.prefix_rule.id)
        self.assertEqual(matches[1].id, self.suffix_rule.id)
        self.assertEqual(matches[2].id, self.contains_rule.id)
    
    def test_pattern_matching_field_filter(self):
        """Test that patterns only match specified target fields"""
        # Create a rule that only targets 'uri' field
        uri_rule = self.service.create_mapping_rule(
            name="URI Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="URI Pattern",
                pattern_type="contains",
                pattern_value="http",
                target_fields=["uri"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="URI"
        )
        
        self.service.add_mapping_rule_to_configuration(self.config.id, uri_rule)
        
        # Should match for 'uri' field
        uri_matches = self.service.get_matching_rules("http://example.com", "uri")
        self.assertEqual(len(uri_matches), 1)
        self.assertEqual(uri_matches[0].id, uri_rule.id)
        
        # Should not match for 'name' field
        name_matches = self.service.get_matching_rules("http://example.com", "name")
        uri_rule_in_matches = any(match.id == uri_rule.id for match in name_matches)
        self.assertFalse(uri_rule_in_matches)
    
    def test_inactive_rules_excluded(self):
        """Test that inactive rules are excluded from matching"""
        # Make the exact rule inactive
        self.exact_rule.active = False
        
        # Should not match inactive rule
        matches = self.service.get_matching_rules("email", "name")
        self.assertEqual(len(matches), 0)
        
        # Reactivate and test again
        self.exact_rule.active = True
        matches = self.service.get_matching_rules("email", "name")
        self.assertEqual(len(matches), 1)
    
    def test_invalid_regex_pattern(self):
        """Test handling of invalid regex patterns"""
        invalid_regex_rule = self.service.create_mapping_rule(
            name="Invalid Regex Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Invalid Regex Pattern",
                pattern_type="regex",
                pattern_value="[invalid regex",  # Missing closing bracket
                target_fields=["name"]
            ),
            mapping_type="property_mapping",
            target_semantic_type="Invalid"
        )
        
        self.service.add_mapping_rule_to_configuration(self.config.id, invalid_regex_rule)
        
        with patch('arkumu.metadata.services.metadata_models_mapping.mapping_configuration.logger') as mock_logger:
            matches = self.service.get_matching_rules("test_value", "name")
            
            # Should not crash and should log warning
            mock_logger.warning.assert_called()
            
            # Should not include the invalid regex rule in results
            invalid_rule_in_matches = any(match.id == invalid_regex_rule.id for match in matches)
            self.assertFalse(invalid_rule_in_matches)
    
    def test_no_active_configuration(self):
        """Test pattern matching with no active configuration"""
        service = MappingConfigurationService()  # Fresh service with no configurations
        
        matches = service.get_matching_rules("test_value", "name")
        self.assertEqual(len(matches), 0)


class TestConfigurationManagement(unittest.TestCase):
    """Test configuration management operations"""
    
    def setUp(self):
        self.service = MappingConfigurationService()
    
    def test_list_configurations(self):
        """Test listing configurations"""
        # Initially empty
        configs = self.service.list_configurations()
        self.assertEqual(len(configs), 0)
        
        # Create some configurations
        config1 = self.service.create_configuration("Config 1", "First config")
        config2 = self.service.create_configuration("Config 2", "Second config")
        
        configs = self.service.list_configurations()
        self.assertEqual(len(configs), 2)
        
        # Check config summary information
        config1_summary = next(c for c in configs if c['id'] == config1.id)
        self.assertEqual(config1_summary['name'], "Config 1")
        self.assertEqual(config1_summary['description'], "First config")
        self.assertEqual(config1_summary['rule_count'], 0)
        self.assertEqual(config1_summary['template_count'], 0)
        self.assertEqual(config1_summary['resolution_rule_count'], 0)
        self.assertFalse(config1_summary['is_active'])  # config2 is active
        
        config2_summary = next(c for c in configs if c['id'] == config2.id)
        self.assertTrue(config2_summary['is_active'])  # config2 is active
    
    def test_remove_mapping_rule(self):
        """Test removing mapping rules from configuration"""
        config = self.service.create_configuration("Test Config")
        
        # Add some rules
        rule1 = self.service.create_mapping_rule(
            name="Rule 1",
            pattern_rule=self.service.create_pattern_rule(
                name="Pattern 1", pattern_type="exact", pattern_value="test1", target_fields=["name"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="Type1"
        )
        
        rule2 = self.service.create_mapping_rule(
            name="Rule 2",
            pattern_rule=self.service.create_pattern_rule(
                name="Pattern 2", pattern_type="exact", pattern_value="test2", target_fields=["name"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="Type2"
        )
        
        self.service.add_mapping_rule_to_configuration(config.id, rule1)
        self.service.add_mapping_rule_to_configuration(config.id, rule2)
        
        # Verify rules were added
        updated_config = self.service.get_configuration(config.id)
        self.assertEqual(len(updated_config.mapping_rules), 2)
        
        # Remove one rule
        result = self.service.remove_mapping_rule(config.id, rule1.id)
        self.assertTrue(result)
        
        # Verify rule was removed
        updated_config = self.service.get_configuration(config.id)
        self.assertEqual(len(updated_config.mapping_rules), 1)
        self.assertEqual(updated_config.mapping_rules[0].id, rule2.id)
        
        # Try to remove non-existent rule
        result = self.service.remove_mapping_rule(config.id, "non-existent")
        self.assertFalse(result)
        
        # Try to remove from non-existent configuration
        result = self.service.remove_mapping_rule("non-existent", rule2.id)
        self.assertFalse(result)
    
    def test_update_mapping_rule(self):
        """Test updating mapping rules"""
        config = self.service.create_configuration("Test Config")
        
        rule = self.service.create_mapping_rule(
            name="Original Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Pattern", pattern_type="exact", pattern_value="test", target_fields=["name"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="OriginalType",
            priority=100
        )
        
        self.service.add_mapping_rule_to_configuration(config.id, rule)
        
        # Update the rule
        updates = {
            'name': 'Updated Rule',
            'target_semantic_type': 'UpdatedType',
            'priority': 50,
            'active': False
        }
        
        result = self.service.update_mapping_rule(config.id, rule.id, updates)
        self.assertTrue(result)
        
        # Verify updates
        updated_config = self.service.get_configuration(config.id)
        updated_rule = updated_config.mapping_rules[0]
        
        self.assertEqual(updated_rule.name, 'Updated Rule')
        self.assertEqual(updated_rule.target_semantic_type, 'UpdatedType')
        self.assertEqual(updated_rule.priority, 50)
        self.assertFalse(updated_rule.active)
        
        # Try to update non-existent rule
        result = self.service.update_mapping_rule(config.id, "non-existent", updates)
        self.assertFalse(result)
        
        # Try to update invalid field (should be ignored)
        result = self.service.update_mapping_rule(config.id, rule.id, {'invalid_field': 'value'})
        self.assertTrue(result)  # Operation succeeds but field is not updated
    
    def test_get_configuration_summary(self):
        """Test getting configuration summary"""
        # Test with no active configuration
        summary = self.service.get_configuration_summary()
        self.assertEqual(summary, {})
        
        # Create configuration with rules
        config = self.service.create_configuration("Test Config", "Test description")
        
        # Add different types of rules
        type_rule = self.service.create_mapping_rule(
            name="Type Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Pattern", pattern_type="exact", pattern_value="test", target_fields=["name"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="Type"
        )
        
        property_rule = self.service.create_mapping_rule(
            name="Property Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Pattern", pattern_type="exact", pattern_value="test2", target_fields=["name"]
            ),
            mapping_type="property_mapping",
            target_semantic_type="Property"
        )
        
        inactive_rule = self.service.create_mapping_rule(
            name="Inactive Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Pattern", pattern_type="exact", pattern_value="test3", target_fields=["name"]
            ),
            mapping_type="relationship",
            target_semantic_type="Relationship"
        )
        inactive_rule.active = False
        
        self.service.add_mapping_rule_to_configuration(config.id, type_rule)
        self.service.add_mapping_rule_to_configuration(config.id, property_rule)
        self.service.add_mapping_rule_to_configuration(config.id, inactive_rule)
        
        # Add relationship template
        template = self.service.create_relationship_template(
            name="Test Template",
            source_column="source",
            target_column="target",
            relationship_predicate="relatedTo",
            source_entity_type="Source",
            target_entity_type="Target"
        )
        self.service.add_relationship_template_to_configuration(config.id, template)
        
        # Get summary
        summary = self.service.get_configuration_summary()
        
        self.assertEqual(summary['id'], config.id)
        self.assertEqual(summary['name'], "Test Config")
        self.assertEqual(summary['description'], "Test description")
        self.assertEqual(summary['total_rules'], 3)
        self.assertEqual(summary['active_rules'], 2)  # inactive_rule is not active
        self.assertEqual(summary['relationship_templates'], 1)
        self.assertEqual(summary['entity_resolution_rules'], 0)
        
        # Check rule type counts
        expected_rule_types = {
            'type_assignment': 1,
            'property_mapping': 1,
            'relationship': 1
        }
        self.assertEqual(summary['rule_types'], expected_rule_types)


class TestImportExport(unittest.TestCase):
    """Test configuration import/export functionality"""
    
    def setUp(self):
        self.service = MappingConfigurationService()
    
    def test_export_configuration(self):
        """Test exporting configuration to JSON"""
        config = self.service.create_configuration("Export Test", "Test export")
        
        # Add a mapping rule
        rule = self.service.create_mapping_rule(
            name="Test Rule",
            pattern_rule=self.service.create_pattern_rule(
                name="Pattern", pattern_type="prefix", pattern_value="test_", target_fields=["name"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="TestType",
            conditions={"test": "value"},
            priority=50
        )
        
        self.service.add_mapping_rule_to_configuration(config.id, rule)
        
        # Export configuration
        exported_json = self.service.export_configuration(config.id)
        self.assertIsNotNone(exported_json)
        
        # Parse and verify JSON
        exported_data = json.loads(exported_json)
        
        self.assertEqual(exported_data['id'], config.id)
        self.assertEqual(exported_data['name'], "Export Test")
        self.assertEqual(exported_data['description'], "Test export")
        
        # Verify mapping rule
        self.assertEqual(len(exported_data['mapping_rules']), 1)
        exported_rule = exported_data['mapping_rules'][0]
        
        self.assertEqual(exported_rule['name'], "Test Rule")
        self.assertEqual(exported_rule['mapping_type'], "type_assignment")  # Should be string
        self.assertEqual(exported_rule['target_semantic_type'], "TestType")
        self.assertEqual(exported_rule['conditions'], {"test": "value"})
        self.assertEqual(exported_rule['priority'], 50)
        
        # Verify pattern rule
        exported_pattern = exported_rule['pattern_rule']
        self.assertEqual(exported_pattern['pattern_type'], "prefix")  # Should be string
        self.assertEqual(exported_pattern['pattern_value'], "test_")
        
        # Test exporting non-existent configuration
        result = self.service.export_configuration("non-existent")
        self.assertIsNone(result)
    
    def test_import_configuration(self):
        """Test importing configuration from JSON"""
        # Create test configuration data
        config_data = {
            "id": "imported-config-id",
            "name": "Imported Config",
            "description": "Imported from JSON",
            "mapping_rules": [
                {
                    "id": "rule-1",
                    "name": "Imported Rule",
                    "mapping_type": "property_mapping",
                    "pattern_rule": {
                        "id": "pattern-1",
                        "name": "Imported Pattern",
                        "pattern_type": "contains",
                        "pattern_value": "address",
                        "target_fields": ["name", "uri"],
                        "description": "Address pattern",
                        "active": True
                    },
                    "target_semantic_type": "Address",
                    "target_predicate": "hasAddress",
                    "conditions": {"type": "string"},
                    "metadata": {"source": "import"},
                    "priority": 75,
                    "active": True
                }
            ],
            "relationship_templates": [],
            "entity_resolution_rules": [],
            "global_settings": {"test_setting": "value"},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T12:00:00"
        }
        
        config_json = json.dumps(config_data)
        
        # Import configuration
        imported_id = self.service.import_configuration(config_json)
        self.assertEqual(imported_id, "imported-config-id")
        
        # Verify imported configuration
        imported_config = self.service.get_configuration(imported_id)
        self.assertIsNotNone(imported_config)
        
        self.assertEqual(imported_config.name, "Imported Config")
        self.assertEqual(imported_config.description, "Imported from JSON")
        self.assertEqual(imported_config.global_settings, {"test_setting": "value"})
        
        # Verify mapping rule
        self.assertEqual(len(imported_config.mapping_rules), 1)
        imported_rule = imported_config.mapping_rules[0]
        
        self.assertEqual(imported_rule.name, "Imported Rule")
        self.assertEqual(imported_rule.mapping_type, MappingType.PROPERTY_MAPPING)
        self.assertEqual(imported_rule.target_semantic_type, "Address")
        self.assertEqual(imported_rule.target_predicate, "hasAddress")
        self.assertEqual(imported_rule.conditions, {"type": "string"})
        self.assertEqual(imported_rule.metadata, {"source": "import"})
        self.assertEqual(imported_rule.priority, 75)
        
        # Verify pattern rule
        pattern_rule = imported_rule.pattern_rule
        self.assertEqual(pattern_rule.name, "Imported Pattern")
        self.assertEqual(pattern_rule.pattern_type, PatternType.CONTAINS)
        self.assertEqual(pattern_rule.pattern_value, "address")
        self.assertEqual(pattern_rule.target_fields, ["name", "uri"])
    
    def test_import_invalid_json(self):
        """Test importing invalid JSON"""
        # Test malformed JSON
        result = self.service.import_configuration("invalid json")
        self.assertIsNone(result)
        
        # Test JSON with invalid enum values
        invalid_config = {
            "id": "invalid-config",
            "name": "Invalid Config",
            "description": "",
            "mapping_rules": [
                {
                    "id": "rule-1",
                    "name": "Invalid Rule",
                    "mapping_type": "invalid_type",  # Invalid enum value
                    "pattern_rule": {
                        "id": "pattern-1",
                        "name": "Pattern",
                        "pattern_type": "prefix",
                        "pattern_value": "test",
                        "target_fields": ["name"],
                        "active": True
                    },
                    "target_semantic_type": "Type",
                    "active": True
                }
            ],
            "relationship_templates": [],
            "entity_resolution_rules": [],
            "global_settings": {},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00"
        }
        
        with patch('arkumu.metadata.services.metadata_models_mapping.mapping_configuration.logger') as mock_logger:
            result = self.service.import_configuration(json.dumps(invalid_config))
            self.assertIsNone(result)
            mock_logger.error.assert_called()


class TestSessionStorage(unittest.TestCase):
    """Test session storage functionality"""
    
    def test_service_with_session_storage(self):
        """Test service operations with session storage"""
        mock_session = {}
        service = MappingConfigurationService(session_storage=mock_session)
        
        # Create configuration (should trigger save to session)
        config = service.create_configuration("Session Test")
        
        # Verify session storage was called
        self.assertIn('mapping_configurations', mock_session)
        session_data = mock_session['mapping_configurations']
        
        self.assertEqual(session_data['active_configuration_id'], config.id)
        self.assertIn(config.id, session_data['configurations'])
    
    def test_save_to_session_converts_enums(self):
        """Test that enums are converted to strings when saving to session"""
        mock_session = {}
        service = MappingConfigurationService(session_storage=mock_session)
        
        config = service.create_configuration("Enum Test")
        
        # Add rule with enums
        rule = service.create_mapping_rule(
            name="Test Rule",
            pattern_rule=service.create_pattern_rule(
                name="Pattern", pattern_type="prefix", pattern_value="test_", target_fields=["name"]
            ),
            mapping_type="type_assignment",
            target_semantic_type="Type"
        )
        
        service.add_mapping_rule_to_configuration(config.id, rule)
        
        # Check session data
        session_data = mock_session['mapping_configurations']
        stored_rule = session_data['configurations'][config.id]['mapping_rules'][0]
        
        # Enums should be converted to strings
        self.assertEqual(stored_rule['mapping_type'], 'type_assignment')
        self.assertEqual(stored_rule['pattern_rule']['pattern_type'], 'prefix')


if __name__ == '__main__':
    unittest.main()
