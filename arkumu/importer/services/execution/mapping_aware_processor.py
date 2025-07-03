"""
Mapping-Aware Processor

Enhanced processor that consumes mapping configurations and handles
complex column types including FK relationships, external ontologies,
and multi-value columns.
"""

import logging
from typing import Dict, Any, List, Optional, Union, Tuple, Set
from dataclasses import dataclass
from datetime import datetime
import polars as pl

from arkumu.importer.services.mapping_consumer import ExecutionConfig, ColumnConfig, FKRelationship as MappingFKRelationship, ProcessingStrategy
from .data_processor import DataProcessor
from .resource_manager import ResourceManager
from .statistics import ExecutionStatistics, ExecutionMetrics
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars, FKRelationship as BulkFKRelationship, UpdateStrategy

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """Context for mapping-aware processing"""
    execution_config: ExecutionConfig
    current_dataset: str
    all_csv_sources: Dict[str, Any]
    entity_cache: Dict[str, Any]  # Cache for FK resolution
    processed_datasets: Set[str]  # Track which datasets have been processed


class MappingAwareProcessor:
    """
    Enhanced processor that handles mapping configurations.
    
    Supports all column types from the GUI mapping system including:
    - Anchor columns (custom primary keys)
    - Foreign key relationships (cross-dataset)
    - Multi-value columns (comma-separated values)
    - Relationship contexts (junction table attributes)
    - External ontology integration (ORCID, Wikidata, etc.)
    """
    
    def __init__(self,
                 institution: str,
                 base_uri: str,
                 statistics: ExecutionStatistics):
        """
        Initialize mapping-aware processor.
        
        Args:
            institution: Institution identifier
            base_uri: Base URI for resource generation
            statistics: Statistics tracker
        """
        self.institution = institution
        self.base_uri = base_uri
        self.statistics = statistics
        
        # Initialize component processors
        self.data_processor = DataProcessor()
        self.resource_manager = ResourceManager(
            institution=institution,
            base_uri=base_uri,
            statistics=statistics
        )
        
        # Initialize the optimized bulk updater for actual data processing
        self.bulk_updater = SmartBulkUpdaterPolars(
            default_strategy=UpdateStrategy.UPDATE_VALUES,
            institution=institution,
            base_uri=base_uri,
            link_row_cells=True,
            link_topology="row"
        )
        
        # Processing state
        self.entity_cache = {}
        self.pending_relationships = []
    
    def process_with_execution_config(self,
                                    execution_config: ExecutionConfig,
                                    csv_sources: Dict[str, Any],
                                    strategy: ProcessingStrategy) -> ExecutionMetrics:
        """
        Process datasets using execution configuration.
        
        Args:
            execution_config: Complete execution configuration
            csv_sources: Dictionary mapping dataset names to CSV data
            strategy: Processing strategy to use
            
        Returns:
            Aggregated execution metrics
        """
        logger.info(f"Starting mapping-aware processing with {strategy} strategy")
        
        # Create processing context
        context = ProcessingContext(
            execution_config=execution_config,
            current_dataset="",
            all_csv_sources=csv_sources,
            entity_cache={},
            processed_datasets=set()
        )
        
        # Execute based on strategy
        if strategy == ProcessingStrategy.ENTITY_CENTRIC:
            return self._process_entity_centric(context)
        elif strategy == ProcessingStrategy.STREAMING_ENTITY_CENTRIC:
            return self._process_streaming_entity_centric(context)
        elif strategy == ProcessingStrategy.MULTI_PHASE:
            return self._process_multi_phase(context)
        else:
            raise ValueError(f"Unsupported processing strategy: {strategy}")
    
    def _process_entity_centric(self, context: ProcessingContext) -> ExecutionMetrics:
        """Process using entity-centric approach with optimized bulk updater"""
        
        logger.info("Processing with entity-centric strategy using SmartBulkUpdaterPolars")
        
        # Convert mapping FK relationships to bulk updater format
        bulk_fk_relationships = []
        for fk_rel in context.execution_config.fk_relationships:
            bulk_fk_relationships.append(BulkFKRelationship(
                source_column=fk_rel.source_column,
                source_dataset=fk_rel.source_dataset,
                target_column=fk_rel.target_column,
                target_dataset=fk_rel.target_dataset,
                relationship_type=fk_rel.relationship_type
            ))
        
        # Update bulk updater with FK relationships
        self.bulk_updater.fk_relationships = bulk_fk_relationships
        
        # Process each dataset with the optimized bulk updater
        for dataset_config in context.execution_config.datasets:
            if dataset_config.dataset_name not in context.all_csv_sources:
                logger.warning(f"No CSV data for dataset: {dataset_config.dataset_name}")
                continue
            
            csv_data = context.all_csv_sources[dataset_config.dataset_name]
            
            # Convert column configs to bulk updater format
            column_configs = self._convert_column_configs_to_bulk_format(dataset_config.columns)
            
            # Use the optimized bulk updater for data processing
            logger.info(f"Processing dataset '{dataset_config.dataset_name}' with mapping-aware bulk updater")
            
            # Update the bulk updater's determine_update_actions_polars to accept column_configs
            df = self.bulk_updater._ensure_dataframe(csv_data)
            updates, action_stats = self.bulk_updater.determine_update_actions_polars(
                df, dataset_config.dataset_name, column_configs
            )
            
            # Execute the updates
            execution_stats = self.bulk_updater.execute_bulk_update(
                updates, dataset_config.dataset_name, action_stats
            )
            
            # Merge statistics
            self._merge_bulk_stats_to_execution_metrics(execution_stats)
            
            context.processed_datasets.add(dataset_config.dataset_name)
        
        # Process FK relationships using the bulk updater
        if bulk_fk_relationships:
            fk_stats = self.bulk_updater.process_fk_relationships(context.all_csv_sources)
            self._merge_bulk_stats_to_execution_metrics(fk_stats)
        
        return self.statistics.current_metrics
    
    def _process_streaming_entity_centric(self, context: ProcessingContext) -> ExecutionMetrics:
        """Process using streaming entity-centric approach"""
        
        logger.info("Processing with streaming entity-centric strategy")
        
        # For now, use chunked processing with smaller batches
        chunk_size = 1000
        
        for dataset_config in context.execution_config.datasets:
            if dataset_config.dataset_name not in context.all_csv_sources:
                continue
            
            context.current_dataset = dataset_config.dataset_name
            csv_data = context.all_csv_sources[dataset_config.dataset_name]
            
            # Convert to DataFrame for chunked processing
            df = self.data_processor._ensure_dataframe(csv_data)
            
            # Process in chunks
            total_rows = df.height
            for chunk_start in range(0, total_rows, chunk_size):
                chunk_end = min(chunk_start + chunk_size, total_rows)
                chunk_df = df[chunk_start:chunk_end]
                
                # Convert chunk back to list format
                chunk_data = chunk_df.to_dicts()
                
                # Process entities in this chunk
                self._process_dataset_with_entities(dataset_config, chunk_data, context)
            
            context.processed_datasets.add(dataset_config.dataset_name)
        
        # Resolve relationships
        self._resolve_pending_relationships(context)
        
        return self.statistics.current_metrics
    
    def _process_multi_phase(self, context: ProcessingContext) -> ExecutionMetrics:
        """Process using multi-phase approach"""
        
        logger.info("Processing with multi-phase strategy")
        
        # Phase 1: Create all entities (without relationships)
        logger.info("Phase 1: Creating entities")
        for dataset_config in context.execution_config.datasets:
            if dataset_config.dataset_name not in context.all_csv_sources:
                continue
            
            context.current_dataset = dataset_config.dataset_name
            csv_data = context.all_csv_sources[dataset_config.dataset_name]
            
            # Process entities only (no relationships)
            self._process_entities_only(dataset_config, csv_data, context)
            context.processed_datasets.add(dataset_config.dataset_name)
        
        # Phase 2: Create FK relationships
        logger.info("Phase 2: Creating FK relationships")
        self._process_all_fk_relationships(context)
        
        # Phase 3: Process relationship contexts
        logger.info("Phase 3: Processing relationship contexts")
        self._process_all_relationship_contexts(context)
        
        return self.statistics.current_metrics
    
    def _process_dataset_with_entities(self,
                                     dataset_config,
                                     csv_data: List[Dict[str, Any]],
                                     context: ProcessingContext):
        """Process a dataset with complete entity creation"""
        
        dataset_name = dataset_config.dataset_name
        logger.info(f"Processing dataset '{dataset_name}' with {len(csv_data)} rows")
        
        # Prepare data
        df = self.data_processor.prepare_for_processing(csv_data)
        if df.height == 0:
            return
        
        # Create dataset and structural resources
        dataset_resource = self.resource_manager.create_dataset_resource(dataset_name)
        
        # Group columns by type for efficient processing
        column_groups = self._group_columns_by_type(dataset_config.columns)
        
        # Process each row as a complete entity
        for row_data in df.iter_rows(named=True):
            entity_uri = self._generate_entity_uri(dataset_name, row_data, dataset_config)
            
            # Create the main entity
            entity_resource = self.resource_manager.create_entity_resource(entity_uri, dataset_name)
            context.entity_cache[entity_uri] = entity_resource
            
            # Process regular columns
            self._process_regular_columns(entity_resource, row_data, column_groups['regular'], context)
            
            # Process anchor columns
            self._process_anchor_columns(entity_resource, row_data, column_groups['anchor'], context)
            
            # Process multi-value columns
            self._process_multi_value_columns(entity_resource, row_data, column_groups['multi_value'], context)
            
            # Queue FK relationships for later resolution
            self._queue_fk_relationships(entity_uri, row_data, column_groups['foreign_key'], context)
            
            # Process external ontology columns
            self._process_external_ontology_columns(entity_resource, row_data, column_groups['external_ontology'], context)
    
    def _process_entities_only(self,
                             dataset_config,
                             csv_data: List[Dict[str, Any]],
                             context: ProcessingContext):
        """Process entities without relationships (for multi-phase)"""
        
        dataset_name = dataset_config.dataset_name
        logger.info(f"Processing entities only for dataset '{dataset_name}'")
        
        # Prepare data
        df = self.data_processor.prepare_for_processing(csv_data)
        if df.height == 0:
            return
        
        # Create dataset resource
        dataset_resource = self.resource_manager.create_dataset_resource(dataset_name)
        
        # Group columns (exclude FK columns in this phase)
        column_groups = self._group_columns_by_type(dataset_config.columns)
        
        # Process each row (entities only)
        for row_data in df.iter_rows(named=True):
            entity_uri = self._generate_entity_uri(dataset_name, row_data, dataset_config)
            entity_resource = self.resource_manager.create_entity_resource(entity_uri, dataset_name)
            context.entity_cache[entity_uri] = entity_resource
            
            # Process only non-relationship columns
            self._process_regular_columns(entity_resource, row_data, column_groups['regular'], context)
            self._process_anchor_columns(entity_resource, row_data, column_groups['anchor'], context)
            self._process_multi_value_columns(entity_resource, row_data, column_groups['multi_value'], context)
            self._process_external_ontology_columns(entity_resource, row_data, column_groups['external_ontology'], context)
    
    def _group_columns_by_type(self, columns: List[ColumnConfig]) -> Dict[str, List[ColumnConfig]]:
        """Group columns by their type for efficient processing"""
        
        groups = {
            'regular': [],
            'anchor': [],
            'foreign_key': [],
            'multi_value': [],
            'relationship_context': [],
            'external_ontology': []
        }
        
        for column in columns:
            if column.is_anchor:
                groups['anchor'].append(column)
            elif column.column_type.value == 'foreign_key':
                groups['foreign_key'].append(column)
            elif column.is_multi_value:
                groups['multi_value'].append(column)
            elif column.column_type.value == 'relationship_context':
                groups['relationship_context'].append(column)
            elif column.is_external_ontology:
                groups['external_ontology'].append(column)
            else:
                groups['regular'].append(column)
        
        return groups
    
    def _generate_entity_uri(self,
                           dataset_name: str,
                           row_data: Dict[str, Any],
                           dataset_config) -> str:
        """Generate URI for an entity based on anchor columns or row ID"""
        
        # Find anchor columns for this dataset
        anchor_columns = [col.column_name for col in dataset_config.columns if col.is_anchor]
        
        if anchor_columns:
            # Use anchor columns to generate URI
            anchor_values = []
            for col_name in anchor_columns:
                value = row_data.get(col_name, '')
                if value:
                    anchor_values.append(str(value).strip())
            
            if anchor_values:
                entity_id = '_'.join(anchor_values)
                return self.resource_manager.generate_entity_uri(dataset_name, entity_id)
        
        # Fall back to row ID
        row_id = row_data.get('row_id', 0)
        display_row_id = int(row_id) + 1 if str(row_id).isdigit() else row_id
        return self.resource_manager.generate_entity_uri(dataset_name, str(display_row_id))
    
    def _process_regular_columns(self,
                               entity_resource,
                               row_data: Dict[str, Any],
                               columns: List[ColumnConfig],
                               context: ProcessingContext):
        """Process regular columns as simple properties"""
        
        for column in columns:
            value = row_data.get(column.column_name)
            if value is not None and str(value).strip():
                # Create property URI from arkumu_type
                property_uri = self._generate_property_uri(column.arkumu_type)
                
                # Create property triple
                self.resource_manager.create_property_triple(
                    entity_resource,
                    property_uri,
                    str(value).strip(),
                    column.datatype
                )
    
    def _process_anchor_columns(self,
                              entity_resource,
                              row_data: Dict[str, Any],
                              columns: List[ColumnConfig],
                              context: ProcessingContext):
        """Process anchor columns (primary key properties)"""
        
        for column in columns:
            value = row_data.get(column.column_name)
            if value is not None and str(value).strip():
                # Create identifier property
                property_uri = self._generate_property_uri(f"identifier_{column.arkumu_type}")
                
                # Create property triple
                self.resource_manager.create_property_triple(
                    entity_resource,
                    property_uri,
                    str(value).strip(),
                    column.datatype
                )
    
    def _process_multi_value_columns(self,
                                   entity_resource,
                                   row_data: Dict[str, Any],
                                   columns: List[ColumnConfig],
                                   context: ProcessingContext):
        """Process multi-value columns (comma-separated values)"""
        
        for column in columns:
            value = row_data.get(column.column_name)
            if value is not None and str(value).strip():
                # Split the value using the configured separator
                values = self._split_multi_value(str(value), column.multi_value_separator)
                
                # Create property URI
                property_uri = self._generate_property_uri(column.arkumu_type)
                
                # Create a property triple for each value
                for single_value in values:
                    if single_value.strip():
                        self.resource_manager.create_property_triple(
                            entity_resource,
                            property_uri,
                            single_value.strip(),
                            column.datatype
                        )
    
    def _queue_fk_relationships(self,
                              entity_uri: str,
                              row_data: Dict[str, Any],
                              columns: List[ColumnConfig],
                              context: ProcessingContext):
        """Queue FK relationships for later resolution"""
        
        for column in columns:
            value = row_data.get(column.column_name)
            if value is not None and str(value).strip():
                # Handle multi-value FKs
                if column.is_multi_value:
                    fk_values = self._split_multi_value(str(value), column.multi_value_separator)
                else:
                    fk_values = [str(value).strip()]
                
                # Queue each FK relationship
                for fk_value in fk_values:
                    if fk_value.strip():
                        self.pending_relationships.append({
                            'source_entity_uri': entity_uri,
                            'source_column': column.column_name,
                            'target_value': fk_value.strip(),
                            'target_dataset': self._get_target_dataset_for_column(column, context),
                            'relationship_type': column.arkumu_type
                        })
    
    def _process_external_ontology_columns(self,
                                         entity_resource,
                                         row_data: Dict[str, Any],
                                         columns: List[ColumnConfig],
                                         context: ProcessingContext):
        """Process external ontology columns"""
        
        for column in columns:
            value = row_data.get(column.column_name)
            if value is not None and str(value).strip():
                # Generate external URI based on ontology configuration
                external_uri = self._generate_external_ontology_uri(column, str(value).strip())
                
                if external_uri:
                    # Create relationship to external ontology resource
                    property_uri = self._generate_property_uri(column.arkumu_type)
                    
                    # Create external resource (stub)
                    external_resource = self.resource_manager.create_external_resource(
                        external_uri,
                        column.external_ontology_config.get('ontology_type', 'external')
                    )
                    
                    # Create relationship triple
                    self.resource_manager.create_relationship_triple(
                        entity_resource,
                        property_uri,
                        external_resource
                    )
    
    def _resolve_pending_relationships(self, context: ProcessingContext):
        """Resolve all pending FK relationships"""
        
        logger.info(f"Resolving {len(self.pending_relationships)} pending FK relationships")
        
        resolved_count = 0
        failed_count = 0
        
        for relationship in self.pending_relationships:
            try:
                # Generate target entity URI
                target_entity_uri = self._generate_target_entity_uri(
                    relationship['target_dataset'],
                    relationship['target_value'],
                    context
                )
                
                # Get or create target entity
                target_entity = self._get_or_create_target_entity(target_entity_uri, relationship, context)
                
                # Get source entity
                source_entity = context.entity_cache.get(relationship['source_entity_uri'])
                
                if source_entity and target_entity:
                    # Create relationship triple
                    property_uri = self._generate_property_uri(relationship['relationship_type'])
                    self.resource_manager.create_relationship_triple(
                        source_entity,
                        property_uri,
                        target_entity
                    )
                    resolved_count += 1
                else:
                    logger.warning(f"Could not resolve FK relationship: {relationship}")
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to resolve FK relationship {relationship}: {e}")
                failed_count += 1
        
        logger.info(f"FK resolution completed: {resolved_count} resolved, {failed_count} failed")
        
        # Clear pending relationships
        self.pending_relationships = []
    
    def _process_all_fk_relationships(self, context: ProcessingContext):
        """Process all FK relationships (for multi-phase)"""
        
        logger.info("Processing all FK relationships")
        
        for execution_config in context.execution_config.datasets:
            if execution_config.dataset_name not in context.all_csv_sources:
                continue
            
            csv_data = context.all_csv_sources[execution_config.dataset_name]
            df = self.data_processor.prepare_for_processing(csv_data)
            
            # Find FK columns for this dataset
            fk_columns = [col for col in execution_config.columns if col.column_type.value == 'foreign_key']
            
            if not fk_columns:
                continue
            
            # Process FK relationships for each row
            for row_data in df.iter_rows(named=True):
                entity_uri = self._generate_entity_uri(execution_config.dataset_name, row_data, execution_config)
                self._queue_fk_relationships(entity_uri, row_data, fk_columns, context)
        
        # Resolve all relationships
        self._resolve_pending_relationships(context)
    
    def _process_all_relationship_contexts(self, context: ProcessingContext):
        """Process all relationship contexts (junction table attributes)"""
        
        logger.info("Processing relationship contexts")
        
        for rel_context in context.execution_config.relationship_contexts:
            logger.info(f"Processing relationship context: {rel_context.context_id}")
            
            # Find the dataset for this context
            if rel_context.dataset_name not in context.all_csv_sources:
                logger.warning(f"No CSV data for relationship context dataset: {rel_context.dataset_name}")
                continue
            
            csv_data = context.all_csv_sources[rel_context.dataset_name]
            df = self.data_processor.prepare_for_processing(csv_data)
            
            # Process each row as a junction entity
            for row_data in df.iter_rows(named=True):
                self._process_junction_entity(rel_context, row_data, context)
    
    def _process_junction_entity(self, rel_context, row_data: Dict[str, Any], context: ProcessingContext):
        """Process a single junction entity with relationship context"""
        
        # Generate junction entity URI
        primary_value = row_data.get(rel_context.primary_fk, '')
        secondary_value = row_data.get(rel_context.secondary_fk, '')
        
        if not primary_value or not secondary_value:
            logger.warning(f"Missing FK values for junction entity: {rel_context.context_id}")
            return
        
        junction_uri = self.resource_manager.generate_junction_uri(
            rel_context.dataset_name,
            str(primary_value),
            str(secondary_value)
        )
        
        # Create junction entity
        junction_entity = self.resource_manager.create_entity_resource(
            junction_uri,
            f"{rel_context.dataset_name}_junction"
        )
        
        # Add context properties
        for context_column in rel_context.context_columns:
            value = row_data.get(context_column)
            if value is not None and str(value).strip():
                property_uri = self._generate_property_uri(f"context_{context_column}")
                self.resource_manager.create_property_triple(
                    junction_entity,
                    property_uri,
                    str(value).strip(),
                    "http://www.w3.org/2001/XMLSchema#string"
                )
        
        # Create relationships to primary and secondary entities
        primary_entity_uri = self._generate_target_entity_uri(
            self._get_target_dataset_from_fk(rel_context.primary_fk, context),
            str(primary_value),
            context
        )
        
        secondary_entity_uri = self._generate_target_entity_uri(
            self._get_target_dataset_from_fk(rel_context.secondary_fk, context),
            str(secondary_value),
            context
        )
        
        # Create relationship triples
        if primary_entity_uri in context.entity_cache:
            property_uri = self._generate_property_uri("involves_primary")
            self.resource_manager.create_relationship_triple(
                junction_entity,
                property_uri,
                context.entity_cache[primary_entity_uri]
            )
        
        if secondary_entity_uri in context.entity_cache:
            property_uri = self._generate_property_uri("involves_secondary")
            self.resource_manager.create_relationship_triple(
                junction_entity,
                property_uri,
                context.entity_cache[secondary_entity_uri]
            )
    
    # Helper methods
    
    def _split_multi_value(self, value: str, separator: str) -> List[str]:
        """Split multi-value string using separator"""
        if not value or not separator:
            return [value] if value else []
        
        return [v.strip() for v in value.split(separator) if v.strip()]
    
    def _generate_property_uri(self, arkumu_type: str) -> str:
        """Generate property URI from arkumu_type"""
        # Check if it's already a full URI
        if arkumu_type.startswith('http://') or arkumu_type.startswith('https://'):
            return arkumu_type
        
        # Generate arkumu property URI
        return f"{self.base_uri}/properties/{arkumu_type}"
    
    def _generate_external_ontology_uri(self, column: ColumnConfig, value: str) -> Optional[str]:
        """Generate external ontology URI"""
        if not column.external_ontology_config:
            return None
        
        uri_template = column.external_ontology_config.get('uri_template', '')
        if '{identifier}' in uri_template:
            return uri_template.replace('{identifier}', value)
        
        return None
    
    def _get_target_dataset_for_column(self, column: ColumnConfig, context: ProcessingContext) -> str:
        """Get target dataset for an FK column"""
        # Look up the target dataset from FK relationships
        for fk_rel in context.execution_config.fk_relationships:
            if fk_rel.source_column == column.column_name:
                return fk_rel.target_dataset
        
        # Fallback to placeholder if not found
        return f"target_dataset_for_{column.column_name}"
    
    def _generate_target_entity_uri(self, target_dataset: str, target_value: str, context: ProcessingContext) -> str:
        """Generate URI for target entity"""
        return self.resource_manager.generate_entity_uri(target_dataset, target_value)
    
    def _get_or_create_target_entity(self, target_uri: str, relationship: Dict, context: ProcessingContext):
        """Get existing target entity or create stub"""
        # Check cache first
        if target_uri in context.entity_cache:
            return context.entity_cache[target_uri]
        
        # Create stub entity
        stub_entity = self.resource_manager.create_entity_resource(
            target_uri,
            relationship['target_dataset'],
            is_stub=True
        )
        
        context.entity_cache[target_uri] = stub_entity
        return stub_entity
    
    def _get_target_dataset_from_fk(self, fk_column: str, context: ProcessingContext) -> str:
        """Get target dataset for FK column from configuration"""
        for fk_rel in context.execution_config.fk_relationships:
            if fk_rel.source_column == fk_column:
                return fk_rel.target_dataset
        
        return f"unknown_target_for_{fk_column}"
    
    def _convert_column_configs_to_bulk_format(self, columns: List[ColumnConfig]) -> Dict[str, Dict[str, Any]]:
        """Convert mapping column configs to bulk updater format."""
        column_configs = {}
        
        for column in columns:
            column_configs[column.column_name] = {
                "is_multi_value": column.is_multi_value,
                "multi_value_separator": column.multi_value_separator or ",",
                "column_type": column.column_type.value if hasattr(column.column_type, 'value') else str(column.column_type),
                "is_anchor": column.is_anchor,
                "arkumu_type": column.arkumu_type,
                "datatype": column.datatype
            }
        
        return column_configs
    
    def _merge_bulk_stats_to_execution_metrics(self, bulk_stats):
        """Merge BulkUpdateStats into ExecutionMetrics."""
        if not bulk_stats:
            return
        
        metrics = self.statistics.current_metrics
        
        # Map BulkUpdateStats fields to ExecutionMetrics fields
        if hasattr(bulk_stats, 'resources_created'):
            metrics.resources_created += bulk_stats.resources_created
        if hasattr(bulk_stats, 'triples_created'):
            metrics.triples_created += bulk_stats.triples_created
        if hasattr(bulk_stats, 'relationships_created'):
            metrics.relationships_created += bulk_stats.relationships_created
        if hasattr(bulk_stats, 'rows_processed'):
            metrics.rows_processed += bulk_stats.rows_processed
        if hasattr(bulk_stats, 'cells_processed'):
            metrics.cells_processed += bulk_stats.cells_processed
        if hasattr(bulk_stats, 'errors'):
            metrics.errors += bulk_stats.errors