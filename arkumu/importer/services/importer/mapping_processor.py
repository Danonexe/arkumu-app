import logging
import json
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from arkumu.importer.services.importer.smart_bulk_updater import SmartBulkUpdater, UpdateStrategy, BulkUpdateStats
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part

logger = logging.getLogger(__name__)


class ProcessingPhase(Enum):
    """Phases for processing mapping configurations in dependency order."""
    PHASE_1_ENTITIES = "entities"           # Create anchor entities first
    PHASE_2_LITERALS = "literals"           # Process regular and multi-value columns
    PHASE_3_RELATIONSHIPS = "relationships" # Process FK relationships
    PHASE_4_CONTEXTS = "contexts"           # Process relationship contexts (junction tables)


@dataclass
class MappingExecutionPlan:
    """Execution plan for processing mapping configurations in phases."""
    phase_1_columns: List[Dict[str, Any]]  # Anchor columns
    phase_2_columns: List[Dict[str, Any]]  # Regular + multi-value columns
    phase_3_columns: List[Dict[str, Any]]  # FK columns
    phase_4_columns: List[Dict[str, Any]]  # Relationship context columns
    external_ontology_columns: List[Dict[str, Any]]  # Special handling
    
    def get_columns_for_phase(self, phase: ProcessingPhase) -> List[Dict[str, Any]]:
        """Get columns for a specific processing phase."""
        return {
            ProcessingPhase.PHASE_1_ENTITIES: self.phase_1_columns,
            ProcessingPhase.PHASE_2_LITERALS: self.phase_2_columns, 
            ProcessingPhase.PHASE_3_RELATIONSHIPS: self.phase_3_columns,
            ProcessingPhase.PHASE_4_CONTEXTS: self.phase_4_columns
        }.get(phase, [])


class GUIMappingProcessor:
    """
    Processes CSV mapping configurations created through the GUI system,
    integrating with SmartBulkUpdater for efficient execution with proper dependency handling.
    """
    
    def __init__(self, 
                 base_uri: str = "http://arkumu.org/data",
                 default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING):
        self.base_uri = base_uri
        self.default_strategy = default_strategy
        self.bulk_updater = None  # Will be initialized per import
        
    def analyze_gui_mapping_config(self, mapping_config: Dict[str, Any]) -> MappingExecutionPlan:
        """
        Analyze a GUI mapping configuration and create an execution plan
        with proper dependency ordering.
        
        Args:
            mapping_config: Serialized mapping configuration from CSV mapping GUI
            
        Returns:
            MappingExecutionPlan with columns organized by processing phase
        """
        workspace_columns = mapping_config.get('workspace_columns', [])
        
        # Sort columns into processing phases based on their types and dependencies
        phase_1_columns = []  # Anchor columns (entity creation)
        phase_2_columns = []  # Regular and multi-value columns (literals)
        phase_3_columns = []  # FK columns (relationships)
        phase_4_columns = []  # Relationship context columns (junction tables)
        external_ontology_columns = []  # Special processing
        
        for column in workspace_columns:
            column_type = self._determine_column_processing_type(column)
            
            if column_type == "anchor":
                phase_1_columns.append(column)
            elif column_type == "literal":
                phase_2_columns.append(column)
            elif column_type == "fk":
                phase_3_columns.append(column)
            elif column_type == "relationship_context":
                phase_4_columns.append(column)
            elif column_type == "external_ontology":
                external_ontology_columns.append(column)
        
        logger.info(f"GUI mapping analysis: {len(phase_1_columns)} anchors, "
                   f"{len(phase_2_columns)} literals, {len(phase_3_columns)} FKs, "
                   f"{len(phase_4_columns)} contexts, {len(external_ontology_columns)} external")
        
        return MappingExecutionPlan(
            phase_1_columns=phase_1_columns,
            phase_2_columns=phase_2_columns,
            phase_3_columns=phase_3_columns,
            phase_4_columns=phase_4_columns,
            external_ontology_columns=external_ontology_columns
        )
    
    def _determine_column_processing_type(self, column: Dict[str, Any]) -> str:
        """Determine the processing type for a column based on its configuration."""
        if column.get('is_anchor', False):
            return "anchor"
        elif column.get('is_fk', False):
            return "fk"
        elif column.get('is_relationship_context', False):
            return "relationship_context"
        elif column.get('is_external_ontology', False):
            return "external_ontology"
        else:
            return "literal"  # Regular or multi-value column
    
    def process_gui_mapping(self, 
                           mapping_config: Dict[str, Any],
                           csv_data: List[Dict[str, Any]],
                           organization_id: str,
                           dataset_name: str) -> Dict[str, Any]:
        """
        Process a complete GUI mapping configuration with proper dependency handling.
        
        Args:
            mapping_config: Serialized mapping from CSV mapping GUI
            csv_data: The actual CSV data to process
            organization_id: Organization identifier
            dataset_name: Dataset name
            
        Returns:
            Combined execution results from all phases
        """
        logger.info(f"Starting GUI mapping processing for {dataset_name} with {len(csv_data)} rows")
        
        # Initialize bulk updater for this import
        import_strategy = mapping_config.get('import_strategy', {})
        self.bulk_updater = SmartBulkUpdater(
            default_strategy=self._convert_import_strategy(import_strategy),
            institution=organization_id,
            base_uri=self.base_uri,
            link_row_cells=import_strategy.get('link_topology') != 'none',
            link_topology=import_strategy.get('link_topology', 'row'),
            multi_value_threshold=import_strategy.get('multi_value_threshold', 0.2)
        )
        
        # Analyze and create execution plan
        execution_plan = self.analyze_gui_mapping_config(mapping_config)
        
        # Execute phases in dependency order
        results = {
            'dataset_name': dataset_name,
            'organization_id': organization_id,
            'total_rows': len(csv_data),
            'phases_executed': [],
            'total_resources_created': 0,
            'total_triples_created': 0,
            'total_errors': 0,
            'external_ontology_results': []
        }
        
        try:
            # Phase 1: Create anchor entities
            if execution_plan.phase_1_columns:
                phase1_results = self._execute_phase_1_entities(
                    execution_plan.phase_1_columns, csv_data, dataset_name
                )
                results['phases_executed'].append(phase1_results)
                results['total_resources_created'] += phase1_results.get('resources_created', 0)
                results['total_triples_created'] += phase1_results.get('triples_created', 0)
                results['total_errors'] += phase1_results.get('errors', 0)
            
            # Phase 2: Process literal values (regular + multi-value)
            if execution_plan.phase_2_columns:
                phase2_results = self._execute_phase_2_literals(
                    execution_plan.phase_2_columns, csv_data, dataset_name
                )
                results['phases_executed'].append(phase2_results)
                results['total_resources_created'] += phase2_results.get('resources_created', 0)
                results['total_triples_created'] += phase2_results.get('triples_created', 0)
                results['total_errors'] += phase2_results.get('errors', 0)
            
            # Phase 3: Process FK relationships
            if execution_plan.phase_3_columns:
                phase3_results = self._execute_phase_3_relationships(
                    execution_plan.phase_3_columns, csv_data, dataset_name, organization_id
                )
                results['phases_executed'].append(phase3_results)
                results['total_resources_created'] += phase3_results.get('resources_created', 0)
                results['total_triples_created'] += phase3_results.get('triples_created', 0)
                results['total_errors'] += phase3_results.get('errors', 0)
            
            # Phase 4: Process relationship contexts (junction tables)
            if execution_plan.phase_4_columns:
                phase4_results = self._execute_phase_4_contexts(
                    execution_plan.phase_4_columns, csv_data, dataset_name, organization_id
                )
                results['phases_executed'].append(phase4_results)
                results['total_resources_created'] += phase4_results.get('resources_created', 0)
                results['total_triples_created'] += phase4_results.get('triples_created', 0)
                results['total_errors'] += phase4_results.get('errors', 0)
            
            # Special processing for external ontology columns
            if execution_plan.external_ontology_columns:
                external_results = self._process_external_ontology_columns(
                    execution_plan.external_ontology_columns, csv_data, dataset_name
                )
                results['external_ontology_results'] = external_results
            
            logger.info(f"GUI mapping processing completed: {results['total_resources_created']} resources, "
                       f"{results['total_triples_created']} triples, {results['total_errors']} errors")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in GUI mapping processing: {e}", exc_info=True)
            results['total_errors'] += 1
            results['error'] = str(e)
            return results
    
    def _execute_phase_1_entities(self, anchor_columns: List[Dict[str, Any]], 
                                 csv_data: List[Dict[str, Any]], 
                                 dataset_name: str) -> Dict[str, Any]:
        """Execute Phase 1: Create anchor entities from anchor columns."""
        logger.info(f"Phase 1: Processing {len(anchor_columns)} anchor columns")
        
        # Filter CSV data to only include anchor columns
        anchor_column_names = [col['name'] for col in anchor_columns]
        filtered_data = []
        
        for row in csv_data:
            filtered_row = {col_name: row.get(col_name) for col_name in anchor_column_names if col_name in row}
            if filtered_row:  # Only include rows with anchor data
                filtered_data.append(filtered_row)
        
        # Use SmartBulkUpdater to create anchor entities
        stats = self.bulk_updater.import_csv_with_smart_updates(
            filtered_data, f"{dataset_name}_anchors", UpdateStrategy.SKIP_EXISTING
        )
        
        return {
            'phase': 'entities',
            'columns_processed': len(anchor_columns),
            'rows_processed': stats.rows_processed,
            'resources_created': stats.resources_created,
            'triples_created': stats.triples_created,
            'errors': stats.errors
        }
    
    def _execute_phase_2_literals(self, literal_columns: List[Dict[str, Any]], 
                                 csv_data: List[Dict[str, Any]], 
                                 dataset_name: str) -> Dict[str, Any]:
        """Execute Phase 2: Process literal values (regular + multi-value columns)."""
        logger.info(f"Phase 2: Processing {len(literal_columns)} literal columns")
        
        # Filter CSV data for literal columns
        literal_column_names = [col['name'] for col in literal_columns]
        filtered_data = []
        
        for row in csv_data:
            filtered_row = {col_name: row.get(col_name) for col_name in literal_column_names if col_name in row}
            if filtered_row:
                filtered_data.append(filtered_row)
        
        # Use SmartBulkUpdater with multi-value detection
        stats = self.bulk_updater.import_csv_with_smart_updates(
            filtered_data, f"{dataset_name}_literals", self.default_strategy
        )
        
        return {
            'phase': 'literals',
            'columns_processed': len(literal_columns),
            'rows_processed': stats.rows_processed,
            'resources_created': stats.resources_created,
            'triples_created': stats.triples_created,
            'multi_value_cells': stats.multi_value_cells_detected,
            'errors': stats.errors
        }
    
    def _execute_phase_3_relationships(self, fk_columns: List[Dict[str, Any]], 
                                     csv_data: List[Dict[str, Any]], 
                                     dataset_name: str,
                                     organization_id: str) -> Dict[str, Any]:
        """Execute Phase 3: Process FK relationships."""
        logger.info(f"Phase 3: Processing {len(fk_columns)} FK columns")
        
        relationships_created = 0
        errors = 0
        
        # Process each FK column individually to handle relationships properly
        for fk_column in fk_columns:
            try:
                fk_config = fk_column.get('fk_config', {})
                source_column = fk_column['name']
                target_dataset = fk_config.get('target_dataset')
                target_column = fk_config.get('target_column')
                direction = fk_config.get('direction', 'outbound')
                
                logger.info(f"Processing FK: {source_column} -> {target_dataset}.{target_column} ({direction})")
                
                # Create relationship triples
                fk_stats = self._create_fk_relationships(
                    csv_data, source_column, target_dataset, target_column, 
                    direction, dataset_name, organization_id
                )
                
                relationships_created += fk_stats.get('relationships_created', 0)
                
            except Exception as e:
                logger.error(f"Error processing FK column {fk_column.get('name')}: {e}")
                errors += 1
        
        return {
            'phase': 'relationships',
            'columns_processed': len(fk_columns),
            'relationships_created': relationships_created,
            'triples_created': relationships_created,  # Each relationship = 1 triple
            'resources_created': 0,  # FKs link existing resources
            'errors': errors
        }
    
    def _execute_phase_4_contexts(self, context_columns: List[Dict[str, Any]], 
                                 csv_data: List[Dict[str, Any]], 
                                 dataset_name: str,
                                 organization_id: str) -> Dict[str, Any]:
        """Execute Phase 4: Process relationship contexts (junction tables)."""
        logger.info(f"Phase 4: Processing {len(context_columns)} relationship context columns")
        
        contexts_created = 0
        errors = 0
        
        # Process each relationship context column
        for context_column in context_columns:
            try:
                rel_context = context_column.get('relationship_context', {})
                
                # Create junction table entries with context attributes
                context_stats = self._create_relationship_contexts(
                    csv_data, context_column, rel_context, dataset_name, organization_id
                )
                
                contexts_created += context_stats.get('contexts_created', 0)
                
            except Exception as e:
                logger.error(f"Error processing relationship context {context_column.get('name')}: {e}")
                errors += 1
        
        return {
            'phase': 'contexts',
            'columns_processed': len(context_columns),
            'contexts_created': contexts_created,
            'triples_created': contexts_created * 3,  # Each context creates multiple triples
            'resources_created': contexts_created,  # Junction entities
            'errors': errors
        }
    
    def _create_fk_relationships(self, csv_data: List[Dict[str, Any]], 
                               source_column: str, target_dataset: str, target_column: str,
                               direction: str, dataset_name: str, organization_id: str) -> Dict[str, Any]:
        """Create FK relationship triples between entities."""
        from arkumu.metadata.models.resource import Resource, ResourceType
        from arkumu.metadata.models.triples import Triple
        
        relationships_created = 0
        errors = 0
        
        try:
            # Get or create the relationship property
            if direction == 'outbound':
                property_name = f"relates_to_{target_dataset}"
                property_uri = mint_uri(self.base_uri, organization_id, "properties", property_name)
            else:  # inbound
                property_name = f"related_from_{dataset_name}"
                property_uri = mint_uri(self.base_uri, organization_id, "properties", property_name)
            
            relationship_property, _ = Resource.objects.get_or_create(
                uri=property_uri,
                defaults={
                    "resource_type": ResourceType.PROPERTY,
                    "name": property_name,
                    "source": organization_id
                }
            )
            
            # Process each row to create relationships
            for row_idx, row in enumerate(csv_data):
                source_value = row.get(source_column)
                if not source_value:
                    continue
                
                try:
                    # Find source entity (from current dataset)
                    source_entity_uri = mint_uri(
                        self.base_uri, organization_id, "datasets", 
                        dataset_name, slugify_uri_part(source_column), 
                        slugify_uri_part(str(source_value))
                    )
                    
                    # Find target entity (from target dataset)  
                    target_entity_uri = mint_uri(
                        self.base_uri, organization_id, "datasets",
                        target_dataset, slugify_uri_part(target_column),
                        slugify_uri_part(str(source_value))  # Assume same value for FK lookup
                    )
                    
                    # Get the actual resource objects
                    try:
                        source_resource = Resource.objects.get(uri=source_entity_uri)
                        target_resource = Resource.objects.get(uri=target_entity_uri)
                        
                        # Create the relationship triple
                        if direction == 'outbound':
                            subject, object_ref = source_resource, target_resource
                        else:
                            subject, object_ref = target_resource, source_resource
                        
                        triple, created = Triple.objects.get_or_create(
                            subject=subject,
                            predicate=relationship_property,
                            object=object_ref
                        )
                        
                        if created:
                            relationships_created += 1
                            
                    except Resource.DoesNotExist as e:
                        logger.warning(f"FK relationship: Entity not found for {source_value}: {e}")
                        errors += 1
                        
                except Exception as e:
                    logger.error(f"Error creating FK relationship for row {row_idx}: {e}")
                    errors += 1
                    
        except Exception as e:
            logger.error(f"Error in FK relationship processing: {e}")
            errors += 1
        
        logger.info(f"FK relationships: {relationships_created} created, {errors} errors")
        return {'relationships_created': relationships_created, 'errors': errors}
    
    def _create_relationship_contexts(self, csv_data: List[Dict[str, Any]], 
                                    context_column: Dict[str, Any], 
                                    rel_context: Dict[str, Any],
                                    dataset_name: str, organization_id: str) -> Dict[str, Any]:
        """Create relationship context (junction table) entities with attributes."""
        from arkumu.metadata.models.resource import Resource, ResourceType
        from arkumu.metadata.models.triples import Triple
        
        contexts_created = 0
        errors = 0
        
        try:
            context_column_name = context_column.get('name')
            primary_fk_dataset = rel_context.get('primary_fk_dataset')
            primary_fk_column = rel_context.get('primary_fk_column') 
            secondary_fk_dataset = rel_context.get('secondary_fk_dataset')
            secondary_fk_column = rel_context.get('secondary_fk_column')
            context_predicate = rel_context.get('context_predicate', 'has_context')
            
            if not all([primary_fk_dataset, primary_fk_column, secondary_fk_dataset, secondary_fk_column]):
                logger.error(f"Missing FK configuration for relationship context {context_column_name}")
                return {'contexts_created': 0, 'errors': 1}
            
            # Get or create relationship context property
            context_property_uri = mint_uri(self.base_uri, organization_id, "properties", context_predicate)
            context_property, _ = Resource.objects.get_or_create(
                uri=context_property_uri,
                defaults={
                    "resource_type": ResourceType.PROPERTY,
                    "name": context_predicate,
                    "source": organization_id
                }
            )
            
            # Get or create junction property (connects primary to secondary through context)
            junction_property_uri = mint_uri(self.base_uri, organization_id, "properties", f"junction_{context_predicate}")
            junction_property, _ = Resource.objects.get_or_create(
                uri=junction_property_uri,
                defaults={
                    "resource_type": ResourceType.PROPERTY,
                    "name": f"junction_{context_predicate}",
                    "source": organization_id
                }
            )
            
            # Process each row to create junction entities
            for row_idx, row in enumerate(csv_data):
                context_value = row.get(context_column_name)
                if not context_value:
                    continue
                
                try:
                    # Create unique junction entity URI
                    junction_id = f"{row_idx}_{slugify_uri_part(str(context_value))}"
                    junction_uri = mint_uri(
                        self.base_uri, organization_id, "junctions",
                        dataset_name, context_column_name, junction_id
                    )
                    
                    # Create junction entity
                    junction_entity, created = Resource.objects.get_or_create(
                        uri=junction_uri,
                        defaults={
                            "resource_type": ResourceType.IRI,
                            "name": f"Junction {context_value}",
                            "source": organization_id
                        }
                    )
                    
                    if created:
                        contexts_created += 1
                        
                        # Find primary and secondary entities to link
                        # This is simplified - in reality you'd need to resolve the FK values
                        primary_value = "primary_entity_id"  # TODO: Extract from row based on FK config
                        secondary_value = "secondary_entity_id"  # TODO: Extract from row based on FK config
                        
                        # Create context attribute triple (junction -> context_value)
                        context_literal, _ = Resource.objects.get_or_create(
                            resource_type=ResourceType.LITERAL,
                            value=str(context_value),
                            source=organization_id,
                            defaults={"name": context_column_name}
                        )
                        
                        Triple.objects.get_or_create(
                            subject=junction_entity,
                            predicate=context_property,
                            object=context_literal
                        )
                        
                        # TODO: Create triples linking junction to primary and secondary entities
                        # This requires resolving the FK values from the row data
                        
                except Exception as e:
                    logger.error(f"Error creating relationship context for row {row_idx}: {e}")
                    errors += 1
                    
        except Exception as e:
            logger.error(f"Error in relationship context processing: {e}")
            errors += 1
        
        logger.info(f"Relationship contexts: {contexts_created} created, {errors} errors")
        return {'contexts_created': contexts_created, 'errors': errors}
    
    def _process_external_ontology_columns(self, external_columns: List[Dict[str, Any]], 
                                         csv_data: List[Dict[str, Any]], 
                                         dataset_name: str) -> List[Dict[str, Any]]:
        """Process external ontology columns with validation and URI generation."""
        results = []
        
        for column in external_columns:
            ext_config = column.get('external_ontology', {})
            ontology_type = ext_config.get('ontology_type')
            uri_template = ext_config.get('uri_template')
            validation_enabled = ext_config.get('validation_enabled', True)
            identifier_pattern = ext_config.get('identifier_pattern')
            column_name = column.get('name')
            
            validated_count = 0
            errors = 0
            
            if validation_enabled and identifier_pattern:
                import re
                pattern = re.compile(identifier_pattern)
                
                for row in csv_data:
                    value = row.get(column_name)
                    if value:
                        if pattern.match(str(value)):
                            validated_count += 1
                            # TODO: Create external URI links
                            if uri_template:
                                external_uri = uri_template.format(identifier=value)
                                logger.debug(f"Valid {ontology_type} identifier: {value} -> {external_uri}")
                        else:
                            errors += 1
                            logger.warning(f"Invalid {ontology_type} identifier: {value}")
            
            results.append({
                'column_name': column_name,
                'ontology_type': ontology_type,
                'processed': True,
                'validated_count': validated_count,
                'errors': errors
            })
        
        return results
    
    def _convert_import_strategy(self, import_strategy: Dict[str, Any]) -> UpdateStrategy:
        """Convert GUI import strategy to SmartBulkUpdater UpdateStrategy."""
        strategy_name = import_strategy.get('update_strategy', 'skip_existing')
        
        strategy_map = {
            'skip_existing': UpdateStrategy.SKIP_EXISTING,
            'update_values': UpdateStrategy.UPDATE_VALUES,
            'merge_triples': UpdateStrategy.MERGE_TRIPLES,
            'replace_all': UpdateStrategy.REPLACE_ALL,
            'timestamp_based': UpdateStrategy.TIMESTAMP_BASED
        }
        
        return strategy_map.get(strategy_name, UpdateStrategy.SKIP_EXISTING) 