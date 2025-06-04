"""
Mapping Configuration Service

Manages mapping rules, templates, and configurations for semantic transformations.
Provides flexible, declarative configuration system for any semantic model.
"""

import json
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class PatternType(Enum):
    PREFIX = "prefix"
    SUFFIX = "suffix"
    CONTAINS = "contains"
    REGEX = "regex"
    EXACT = "exact"


class MappingType(Enum):
    TYPE_ASSIGNMENT = "type_assignment"
    PROPERTY_MAPPING = "property_mapping"
    RELATIONSHIP = "relationship"
    ENTITY_RESOLUTION = "entity_resolution"


@dataclass
class PatternRule:
    """A pattern-based mapping rule"""
    id: str
    name: str
    pattern_type: PatternType
    pattern_value: str
    target_fields: List[str]  # Which fields to search (uri, name, value, source)
    description: str = ""
    active: bool = True


@dataclass
class MappingRule:
    """A complete mapping rule"""
    id: str
    name: str
    mapping_type: MappingType
    pattern_rule: PatternRule
    target_semantic_type: str
    target_predicate: Optional[str] = None
    conditions: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    priority: int = 100
    active: bool = True


@dataclass
class RelationshipTemplate:
    """Template for creating relationships between entities"""
    id: str
    name: str
    source_column: str
    target_column: str
    relationship_predicate: str
    source_entity_type: str
    target_entity_type: str
    relationship_metadata_columns: List[str] = None
    bidirectional: bool = False
    description: str = ""


@dataclass
class EntityResolutionRule:
    """Rule for resolving cross-table entity references"""
    id: str
    name: str
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    resolution_strategy: str  # 'exact_match', 'fuzzy_match', 'pattern_match'
    fallback_strategy: str = 'create_placeholder'  # 'skip', 'create_placeholder', 'error'
    confidence_threshold: float = 0.8


@dataclass
class TransformationConfiguration:
    """Complete configuration for a transformation pipeline"""
    id: str
    name: str
    description: str
    mapping_rules: List[MappingRule]
    relationship_templates: List[RelationshipTemplate]
    entity_resolution_rules: List[EntityResolutionRule]
    global_settings: Dict[str, Any]
    created_at: str
    updated_at: str


class MappingConfigurationService:
    """Service for managing mapping configurations and rules"""
    
    def __init__(self, session_storage=None):
        """
        Initialize with optional session storage
        
        Args:
            session_storage: Django session or other storage mechanism
        """
        self.session_storage = session_storage
        self._configurations = {}
        self._active_configuration_id = None
    
    def create_pattern_rule(self, name: str, pattern_type: str, pattern_value: str, 
                          target_fields: List[str], description: str = "") -> PatternRule:
        """Create a new pattern rule"""
        import uuid
        
        rule_id = str(uuid.uuid4())
        pattern_rule = PatternRule(
            id=rule_id,
            name=name,
            pattern_type=PatternType(pattern_type),
            pattern_value=pattern_value,
            target_fields=target_fields,
            description=description
        )
        
        return pattern_rule
    
    def create_mapping_rule(self, name: str, pattern_rule: PatternRule, 
                          mapping_type: str, target_semantic_type: str,
                          target_predicate: str = None, conditions: Dict = None,
                          priority: int = 100) -> MappingRule:
        """Create a new mapping rule"""
        import uuid
        
        rule_id = str(uuid.uuid4())
        mapping_rule = MappingRule(
            id=rule_id,
            name=name,
            mapping_type=MappingType(mapping_type),
            pattern_rule=pattern_rule,
            target_semantic_type=target_semantic_type,
            target_predicate=target_predicate,
            conditions=conditions or {},
            priority=priority
        )
        
        return mapping_rule
    
    def create_relationship_template(self, name: str, source_column: str, 
                                   target_column: str, relationship_predicate: str,
                                   source_entity_type: str, target_entity_type: str,
                                   metadata_columns: List[str] = None,
                                   bidirectional: bool = False) -> RelationshipTemplate:
        """Create a relationship template"""
        import uuid
        
        template_id = str(uuid.uuid4())
        template = RelationshipTemplate(
            id=template_id,
            name=name,
            source_column=source_column,
            target_column=target_column,
            relationship_predicate=relationship_predicate,
            source_entity_type=source_entity_type,
            target_entity_type=target_entity_type,
            relationship_metadata_columns=metadata_columns or [],
            bidirectional=bidirectional
        )
        
        return template
    
    def create_entity_resolution_rule(self, name: str, source_table: str, 
                                    source_column: str, target_table: str,
                                    target_column: str, resolution_strategy: str = 'exact_match',
                                    fallback_strategy: str = 'create_placeholder') -> EntityResolutionRule:
        """Create an entity resolution rule"""
        import uuid
        
        rule_id = str(uuid.uuid4())
        rule = EntityResolutionRule(
            id=rule_id,
            name=name,
            source_table=source_table,
            source_column=source_column,
            target_table=target_table,
            target_column=target_column,
            resolution_strategy=resolution_strategy,
            fallback_strategy=fallback_strategy
        )
        
        return rule
    
    def create_configuration(self, name: str, description: str = "") -> TransformationConfiguration:
        """Create a new transformation configuration"""
        import uuid
        from datetime import datetime
        
        config_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        configuration = TransformationConfiguration(
            id=config_id,
            name=name,
            description=description,
            mapping_rules=[],
            relationship_templates=[],
            entity_resolution_rules=[],
            global_settings={},
            created_at=now,
            updated_at=now
        )
        
        self._configurations[config_id] = configuration
        self._active_configuration_id = config_id
        
        # Save to session if available
        self._save_to_session()
        
        return configuration
    
    def add_mapping_rule_to_configuration(self, config_id: str, mapping_rule: MappingRule) -> bool:
        """Add a mapping rule to a configuration"""
        if config_id not in self._configurations:
            return False
        
        configuration = self._configurations[config_id]
        configuration.mapping_rules.append(mapping_rule)
        
        # Update timestamp
        from datetime import datetime
        configuration.updated_at = datetime.now().isoformat()
        
        # Save to session if available
        self._save_to_session()
        
        return True
    
    def add_relationship_template_to_configuration(self, config_id: str, 
                                                 template: RelationshipTemplate) -> bool:
        """Add a relationship template to a configuration"""
        if config_id not in self._configurations:
            return False
        
        configuration = self._configurations[config_id]
        configuration.relationship_templates.append(template)
        
        # Update timestamp
        from datetime import datetime
        configuration.updated_at = datetime.now().isoformat()
        
        # Save to session if available
        self._save_to_session()
        
        return True
    
    def add_entity_resolution_rule_to_configuration(self, config_id: str, 
                                                  rule: EntityResolutionRule) -> bool:
        """Add an entity resolution rule to a configuration"""
        if config_id not in self._configurations:
            return False
        
        configuration = self._configurations[config_id]
        configuration.entity_resolution_rules.append(rule)
        
        # Update timestamp
        from datetime import datetime
        configuration.updated_at = datetime.now().isoformat()
        
        # Save to session if available
        self._save_to_session()
        
        return True
    
    def get_configuration(self, config_id: str) -> Optional[TransformationConfiguration]:
        """Get a configuration by ID"""
        return self._configurations.get(config_id)
    
    def get_active_configuration(self) -> Optional[TransformationConfiguration]:
        """Get the currently active configuration"""
        if self._active_configuration_id:
            return self._configurations.get(self._active_configuration_id)
        return None
    
    def set_active_configuration(self, config_id: str) -> bool:
        """Set the active configuration"""
        if config_id in self._configurations:
            self._active_configuration_id = config_id
            self._save_to_session()
            return True
        return False
    
    def list_configurations(self) -> List[Dict[str, Any]]:
        """List all configurations with summary info"""
        configs = []
        for config in self._configurations.values():
            configs.append({
                'id': config.id,
                'name': config.name,
                'description': config.description,
                'rule_count': len(config.mapping_rules),
                'template_count': len(config.relationship_templates),
                'resolution_rule_count': len(config.entity_resolution_rules),
                'created_at': config.created_at,
                'updated_at': config.updated_at,
                'is_active': config.id == self._active_configuration_id
            })
        return configs
    
    def remove_mapping_rule(self, config_id: str, rule_id: str) -> bool:
        """Remove a mapping rule from a configuration"""
        if config_id not in self._configurations:
            return False
        
        configuration = self._configurations[config_id]
        original_count = len(configuration.mapping_rules)
        configuration.mapping_rules = [rule for rule in configuration.mapping_rules if rule.id != rule_id]
        
        if len(configuration.mapping_rules) < original_count:
            from datetime import datetime
            configuration.updated_at = datetime.now().isoformat()
            self._save_to_session()
            return True
        
        return False
    
    def update_mapping_rule(self, config_id: str, rule_id: str, updates: Dict[str, Any]) -> bool:
        """Update a mapping rule"""
        if config_id not in self._configurations:
            return False
        
        configuration = self._configurations[config_id]
        
        for rule in configuration.mapping_rules:
            if rule.id == rule_id:
                # Update allowed fields
                for field, value in updates.items():
                    if hasattr(rule, field):
                        setattr(rule, field, value)
                
                from datetime import datetime
                configuration.updated_at = datetime.now().isoformat()
                self._save_to_session()
                return True
        
        return False
    
    def get_matching_rules(self, value: str, field_name: str, 
                          config_id: str = None) -> List[MappingRule]:
        """Get all mapping rules that match a given value and field"""
        import re
        
        config = self.get_configuration(config_id) if config_id else self.get_active_configuration()
        if not config:
            return []
        
        matching_rules = []
        
        for rule in config.mapping_rules:
            if not rule.active:
                continue
                
            # Check if the field is in target fields
            if field_name not in rule.pattern_rule.target_fields:
                continue
            
            # Apply pattern matching
            pattern_rule = rule.pattern_rule
            matches = False
            
            if pattern_rule.pattern_type == PatternType.PREFIX:
                matches = value.startswith(pattern_rule.pattern_value)
            elif pattern_rule.pattern_type == PatternType.SUFFIX:
                matches = value.endswith(pattern_rule.pattern_value)
            elif pattern_rule.pattern_type == PatternType.CONTAINS:
                matches = pattern_rule.pattern_value in value
            elif pattern_rule.pattern_type == PatternType.EXACT:
                matches = value == pattern_rule.pattern_value
            elif pattern_rule.pattern_type == PatternType.REGEX:
                try:
                    matches = bool(re.match(pattern_rule.pattern_value, value))
                except re.error:
                    logger.warning(f"Invalid regex pattern: {pattern_rule.pattern_value}")
                    matches = False
            
            if matches:
                matching_rules.append(rule)
        
        # Sort by priority (lower number = higher priority)
        matching_rules.sort(key=lambda r: r.priority)
        
        return matching_rules
    
    def export_configuration(self, config_id: str) -> Optional[str]:
        """Export a configuration as JSON"""
        config = self.get_configuration(config_id)
        if not config:
            return None
        
        # Convert to dictionary
        config_dict = asdict(config)
        
        # Convert enums to strings
        for rule in config_dict['mapping_rules']:
            rule['mapping_type'] = rule['mapping_type'].value
            rule['pattern_rule']['pattern_type'] = rule['pattern_rule']['pattern_type'].value
        
        return json.dumps(config_dict, indent=2)
    
    def import_configuration(self, config_json: str) -> Optional[str]:
        """Import a configuration from JSON"""
        try:
            config_dict = json.loads(config_json)
            
            # Reconstruct enums
            for rule in config_dict['mapping_rules']:
                rule['mapping_type'] = MappingType(rule['mapping_type'])
                rule['pattern_rule']['pattern_type'] = PatternType(rule['pattern_rule']['pattern_type'])
                
                # Convert nested dictionaries back to dataclasses
                rule['pattern_rule'] = PatternRule(**rule['pattern_rule'])
            
            # Create dataclass objects
            mapping_rules = [MappingRule(**rule) for rule in config_dict['mapping_rules']]
            relationship_templates = [RelationshipTemplate(**template) for template in config_dict.get('relationship_templates', [])]
            entity_resolution_rules = [EntityResolutionRule(**rule) for rule in config_dict.get('entity_resolution_rules', [])]
            
            # Create configuration
            config = TransformationConfiguration(
                id=config_dict['id'],
                name=config_dict['name'],
                description=config_dict['description'],
                mapping_rules=mapping_rules,
                relationship_templates=relationship_templates,
                entity_resolution_rules=entity_resolution_rules,
                global_settings=config_dict.get('global_settings', {}),
                created_at=config_dict['created_at'],
                updated_at=config_dict['updated_at']
            )
            
            self._configurations[config.id] = config
            self._save_to_session()
            
            return config.id
            
        except Exception as e:
            logger.error(f"Error importing configuration: {str(e)}")
            return None
    
    def _save_to_session(self):
        """Save configurations to session storage"""
        if self.session_storage is not None:
            try:
                # Convert to JSON-serializable format
                session_data = {
                    'configurations': {},
                    'active_configuration_id': self._active_configuration_id
                }
                
                for config_id, config in self._configurations.items():
                    session_data['configurations'][config_id] = asdict(config)
                    
                    # Convert enums to strings for JSON serialization
                    for rule in session_data['configurations'][config_id]['mapping_rules']:
                        rule['mapping_type'] = rule['mapping_type'].value
                        rule['pattern_rule']['pattern_type'] = rule['pattern_rule']['pattern_type'].value
                
                self.session_storage['mapping_configurations'] = session_data
            except Exception as e:
                logger.error(f"Error saving to session: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
    
    def _load_from_session(self):
        """Load configurations from session storage"""
        if self.session_storage is not None and 'mapping_configurations' in self.session_storage:
            try:
                session_data = self.session_storage['mapping_configurations']
                
                self._active_configuration_id = session_data.get('active_configuration_id')
                
                for config_id, config_dict in session_data.get('configurations', {}).items():
                    # Reconstruct configuration from session data
                    # (Similar to import_configuration logic)
                    # ... reconstruction logic here ...
                    pass
                    
            except Exception as e:
                logger.error(f"Error loading configurations from session: {str(e)}")
    
    def get_configuration_summary(self, config_id: str = None) -> Dict[str, Any]:
        """Get a summary of the configuration for display purposes"""
        config = self.get_configuration(config_id) if config_id else self.get_active_configuration()
        if not config:
            return {}
        
        summary = {
            'id': config.id,
            'name': config.name,
            'description': config.description,
            'total_rules': len(config.mapping_rules),
            'active_rules': len([r for r in config.mapping_rules if r.active]),
            'rule_types': {},
            'relationship_templates': len(config.relationship_templates),
            'entity_resolution_rules': len(config.entity_resolution_rules),
            'last_updated': config.updated_at
        }
        
        # Count rule types
        for rule in config.mapping_rules:
            rule_type = rule.mapping_type.value
            summary['rule_types'][rule_type] = summary['rule_types'].get(rule_type, 0) + 1
        
        return summary 