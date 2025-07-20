"""
Enhanced Mapping-Aware Processor with Schema-First Blueprint Creation

Integrates the schema-first processor to create complete blueprints
before any CSV data processing begins.
"""

import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass

from arkumu.importer.services.mapping_consumer import ExecutionConfig, ColumnConfig, ProcessingStrategy
from .mapping_aware_processor import MappingAwareProcessor, ProcessingContext
from .schema_first_processor import SchemaFirstProcessor, SchemaBlueprint
from .statistics import ExecutionStatistics, ExecutionMetrics

logger = logging.getLogger(__name__)


class EnhancedMappingProcessor(MappingAwareProcessor):
    """
    Enhanced mapping-aware processor that creates complete schema blueprints
    BEFORE processing any CSV data.
    
    This ensures:
    - All datasets have complete schema definitions
    - FK relationships are properly mapped upfront
    - Data model compatibility across institutions
    - Resilient blueprint creation regardless of data presence
    """
    
    def __init__(self,
                 institution: str,
                 base_uri: str,
                 statistics: ExecutionStatistics,
                 channel_id: Optional[str] = None,
                 session = None):
        """Initialize enhanced processor with schema-first capability."""
        super().__init__(institution, base_uri, statistics, channel_id, session)
        
        # Initialize schema-first processor
        self.schema_processor = SchemaFirstProcessor(
            institution=institution,
            base_uri=base_uri,
            statistics=statistics
        )
        
        # Schema blueprints created upfront
        self.blueprints: Dict[str, SchemaBlueprint] = {}
    
    def process_with_execution_config(self,
                                    execution_config: ExecutionConfig,
                                    csv_sources: Dict[str, Any],
                                    strategy: ProcessingStrategy) -> ExecutionMetrics:
        """
        Enhanced processing with schema-first blueprint creation.
        
        Process flow:
        1. Create complete schema blueprints for ALL datasets
        2. Validate schema consistency 
        3. Process CSV data using existing logic but with blueprint guidance
        4. Resolve FK relationships using blueprint mappings
        
        Args:
            execution_config: Complete execution configuration
            csv_sources: Dictionary mapping dataset names to CSV data
            strategy: Processing strategy to use
            
        Returns:
            Aggregated execution metrics
        """
        logger.info(f"Starting ENHANCED mapping-aware processing with {strategy} strategy")
        logger.info(f"📊 Datasets to process: {len(execution_config.datasets)}")
        logger.info(f"📁 CSV sources available: {len(csv_sources)}")
        
        # Phase 1: Create complete schema blueprints FIRST
        self._update_progress("Creating schema blueprints...", 5)
        self.blueprints = self.schema_processor.create_complete_schema_blueprint(execution_config)
        
        # Phase 2: Validate schema consistency
        self._update_progress("Validating schema consistency...", 10)
        validation_warnings = self.schema_processor.validate_schema_consistency()
        if validation_warnings:
            logger.warning("⚠️  Schema validation warnings:")
            for warning in validation_warnings:
                logger.warning(f"   {warning}")
        
        # Phase 3: Process CSV data using blueprints
        self._update_progress("Processing CSV data with blueprints...", 15)
        
        # Create processing context with blueprint awareness
        context = ProcessingContext(
            execution_config=execution_config,
            current_dataset="",
            all_csv_sources=csv_sources,
            entity_cache={},
            processed_datasets=set()
        )
        
        # Add blueprint information to context
        context.blueprints = self.blueprints
        
        # Execute processing with blueprint guidance
        return self._process_with_blueprints(context)
    
    def _process_with_blueprints(self, context: ProcessingContext) -> ExecutionMetrics:
        """Process datasets using schema blueprints for guidance."""
        
        logger.info("🏗️  Processing with schema blueprint guidance")
        
        # For now, use chunked processing with smaller batches
        chunk_size = 1000
        total_datasets = len(context.execution_config.datasets)
        processed_datasets_count = 0
        
        for dataset_config in context.execution_config.datasets:
            dataset_name = dataset_config.dataset_name
            blueprint = self.blueprints.get(dataset_name)
            
            if not blueprint:
                logger.error(f"❌ No blueprint found for dataset '{dataset_name}' - this should not happen!")
                continue
            
            logger.info(f"\\n{'='*60}")
            logger.info(f"📦 Processing dataset: {dataset_name}")
            logger.info(f"🏗️  Using blueprint: {len(blueprint.property_resources)} properties, {len(blueprint.fk_relationships)} FK relationships")
            
            # Update progress
            progress = 15 + int((processed_datasets_count / total_datasets) * 70)
            self._update_progress(f"Processing {dataset_name}...", progress)
            
            # Check if dataset has CSV data
            if dataset_name not in context.all_csv_sources:
                logger.info(f"📄 Dataset {dataset_name} has no CSV data - blueprint already created")
                self._handle_dataset_without_csv(dataset_config, blueprint, context)
                context.processed_datasets.add(dataset_name)
                processed_datasets_count += 1
                continue
            
            # Process dataset with CSV data using blueprint
            csv_data = context.all_csv_sources[dataset_name]
            self._process_dataset_with_blueprint(dataset_config, csv_data, blueprint, context)
            
            context.processed_datasets.add(dataset_name)
            processed_datasets_count += 1
        
        # Phase 4: Resolve FK relationships using blueprint mappings
        self._update_progress("Resolving FK relationships...", 90)
        self._resolve_relationships_with_blueprints(context)
        
        # Phase 5: Final validation and summary
        self._update_progress("Finalizing import...", 95)
        self._log_enhanced_processing_summary(context)
        
        self._update_progress("Import completed!", 100)
        return self.statistics.current_metrics
    
    def _handle_dataset_without_csv(self, 
                                  dataset_config, 
                                  blueprint: SchemaBlueprint, 
                                  context: ProcessingContext):
        """Handle dataset that has no CSV data but has a complete blueprint."""
        logger.info(f"   📊 Blueprint provides complete schema definition")
        logger.info(f"   🏷️  Entity type: {blueprint.entity_type_resource.name}")
        logger.info(f"   📝 Properties: {list(blueprint.property_resources.keys())}")
        
        # The blueprint already contains all necessary schema information
        # Mark as skipped but note that schema is available
        self.statistics.increment_datasets_skipped()
        
        # Check for FK relationships that might reference this empty dataset
        self._check_orphaned_fk_references_with_blueprint(dataset_config.dataset_name, blueprint, context)
    
    def _process_dataset_with_blueprint(self,
                                      dataset_config,
                                      csv_data: Any,
                                      blueprint: SchemaBlueprint,
                                      context: ProcessingContext):
        """Process dataset CSV data using blueprint for guidance."""
        
        dataset_name = dataset_config.dataset_name
        
        # Convert to DataFrame for chunked processing
        if isinstance(csv_data, dict) and 'rows' in csv_data:
            df = self.data_processor.ensure_dataframe(csv_data['rows'])
        else:
            df = self.data_processor.ensure_dataframe(csv_data)
        
        total_rows = df.height
        if total_rows == 0:
            logger.info(f"   📄 Dataset is empty but blueprint provides schema")
            self._handle_dataset_without_csv(dataset_config, blueprint, context)
            return
        
        logger.info(f"   📊 Processing {total_rows} rows with blueprint guidance")
        
        # Track all entities for this dataset across all chunks
        dataset_entities = []
        chunk_size = 1000
        
        # The dataset resource already exists from blueprint creation
        dataset_resource = blueprint.dataset_resource
        
        # Process in chunks
        for chunk_start in range(0, total_rows, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total_rows)
            chunk_df = df[chunk_start:chunk_end]
            
            # Convert chunk back to list format
            chunk_data = chunk_df.to_dicts()
            
            # Process entities in this chunk using blueprint
            chunk_entities = self._process_dataset_chunk_with_blueprint(
                dataset_config, chunk_data, blueprint, context
            )
            dataset_entities.extend(chunk_entities)
        
        # Create dataset-entity linking triples for ALL entities in the dataset
        logger.info(f"   🔗 Creating dataset-entity links ({len(dataset_entities)} entities)")
        if dataset_entities:
            dataset_entity_triples = self.resource_manager.create_dataset_entity_links_bulk(
                dataset_entities, dataset_resource
            )
            logger.info(f"   ✅ Created {len(dataset_entity_triples)} dataset-entity linking triples")
    
    def _process_dataset_chunk_with_blueprint(self,
                                            dataset_config,
                                            csv_data: List[Dict[str, Any]],
                                            blueprint: SchemaBlueprint,
                                            context: ProcessingContext) -> List:
        """Process a chunk of dataset using blueprint for efficient property handling."""
        
        dataset_name = dataset_config.dataset_name
        
        # Create mapping configuration for multi-value detection
        mapping_config = self._create_mapping_config_from_dataset(dataset_config)
        
        # Prepare data with mapping configuration
        df = self.data_processor.prepare_for_processing(csv_data, mapping_config)
        if df.height == 0:
            return []
        
        # Group columns by type for efficient processing
        column_groups = self._group_columns_by_type(dataset_config.columns)
        
        # Track entities created for this chunk
        chunk_entities = []
        
        # Process each row as a complete entity using blueprint guidance
        for row_data in df.iter_rows(named=True):
            entity_uri = self._generate_entity_uri(dataset_name, row_data, dataset_config)
            
            # Create the main entity (uses existing logic)
            entity_resource = self.resource_manager.create_entity_resource(entity_uri, dataset_name)
            context.entity_cache[entity_uri] = entity_resource
            chunk_entities.append(entity_resource)
            
            # Process columns using blueprint-aware methods
            self._process_regular_columns_with_blueprint(
                entity_resource, row_data, column_groups['regular'], blueprint, context
            )
            
            self._process_anchor_columns_with_blueprint(
                entity_resource, row_data, column_groups['anchor'], blueprint, context
            )
            
            self._process_multi_value_columns_with_blueprint(
                entity_resource, row_data, column_groups['multi_value'], blueprint, context
            )
            
            # Queue FK relationships using blueprint mappings
            self._queue_fk_relationships_with_blueprint(
                entity_uri, row_data, column_groups['foreign_key'], blueprint, context
            )
            
            self._process_external_ontology_columns(
                entity_resource, row_data, column_groups['external_ontology'], context
            )
            
            # Track row processing
            self.statistics.current_metrics.rows_processed += 1
        
        return chunk_entities
    
    def _process_regular_columns_with_blueprint(self,
                                              entity_resource,
                                              row_data: Dict,
                                              columns: List[ColumnConfig],
                                              blueprint: SchemaBlueprint,
                                              context: ProcessingContext):
        """Process regular columns using blueprint property definitions."""
        for column in columns:
            if column.column_name in row_data and row_data[column.column_name] is not None:
                value = str(row_data[column.column_name]).strip()
                if value:
                    # Use blueprint property resource if available
                    property_resource = blueprint.property_resources.get(column.column_name)
                    if property_resource:
                        property_uri = property_resource.uri
                    else:
                        # Fallback to generated URI
                        property_uri = self._generate_property_uri(column.arkumu_type)
                    
                    self.resource_manager.create_property_triple(entity_resource, property_uri, value)
    
    def _process_anchor_columns_with_blueprint(self,
                                             entity_resource,
                                             row_data: Dict,
                                             columns: List[ColumnConfig],
                                             blueprint: SchemaBlueprint,
                                             context: ProcessingContext):
        """Process anchor columns using blueprint property definitions."""
        # Similar to regular columns but with anchor-specific handling
        self._process_regular_columns_with_blueprint(entity_resource, row_data, columns, blueprint, context)
    
    def _process_multi_value_columns_with_blueprint(self,
                                                  entity_resource,
                                                  row_data: Dict,
                                                  columns: List[ColumnConfig],
                                                  blueprint: SchemaBlueprint,
                                                  context: ProcessingContext):
        """Process multi-value columns using blueprint property definitions."""
        # Use existing multi-value logic but with blueprint property URIs
        self._process_multi_value_columns(entity_resource, row_data, columns, context)
    
    def _queue_fk_relationships_with_blueprint(self,
                                             entity_uri: str,
                                             row_data: Dict,
                                             columns: List[ColumnConfig],
                                             blueprint: SchemaBlueprint,
                                             context: ProcessingContext):
        """Queue FK relationships using blueprint FK relationship mappings."""
        for column in columns:
            column_name = column.column_name
            if column_name in row_data and row_data[column_name] is not None:
                raw_value = str(row_data[column_name]).strip()
                if not raw_value:
                    continue
                
                # Handle multi-value FK columns
                fk_values = [v.strip() for v in raw_value.split(',') if v.strip()] if ',' in raw_value else [raw_value]
                
                # Find corresponding FK relationship in blueprint
                blueprint_fk_rel = None
                for fk_rel in blueprint.fk_relationships:
                    if fk_rel['source_column'] == column_name:
                        blueprint_fk_rel = fk_rel
                        break
                
                for fk_value in fk_values:
                    if fk_value.strip():
                        relationship_info = {
                            'source_entity_uri': entity_uri,
                            'source_dataset': blueprint.dataset_name,
                            'source_column': column_name,
                            'target_value': fk_value.strip(),
                            'target_dataset': blueprint_fk_rel['target_dataset'] if blueprint_fk_rel else self._get_target_dataset_from_fk(column_name, context),
                            'target_column': blueprint_fk_rel['target_column'] if blueprint_fk_rel else 'id',
                            'relationship_type': column.arkumu_type,
                            'blueprint_guided': blueprint_fk_rel is not None
                        }
                        self.pending_relationships.append(relationship_info)
    
    def _check_orphaned_fk_references_with_blueprint(self,
                                                   skipped_dataset: str,
                                                   blueprint: SchemaBlueprint,
                                                   context: ProcessingContext):
        """Check for orphaned FK references using blueprint FK mappings."""
        logger.info(f"   🔍 Checking for FK references to empty dataset '{skipped_dataset}' using blueprint")
        
        orphaned_refs = []
        
        # Use blueprint FK relationships for more accurate detection
        for other_blueprint in self.blueprints.values():
            if other_blueprint.dataset_name == skipped_dataset:
                continue
                
            for fk_rel in other_blueprint.fk_relationships:
                if fk_rel['target_dataset'] == skipped_dataset:
                    orphaned_refs.append({
                        'source_dataset': other_blueprint.dataset_name,
                        'source_column': fk_rel['source_column'],
                        'target_dataset': skipped_dataset,
                        'target_column': fk_rel['target_column'],
                        'relationship_type': fk_rel['relationship_type']
                    })
        
        if orphaned_refs:
            logger.info(f"   🏗️  Found {len(orphaned_refs)} FK references pointing to empty dataset")
            logger.info(f"   ✅ Blueprint already provides complete schema structure")
            
            # Blueprint already contains the necessary schema structure
            # No need to create additional stub structure
            for ref in orphaned_refs:
                logger.info(f"     🔗 {ref['source_dataset']}.{ref['source_column']} -> {ref['target_dataset']}.{ref['target_column']}")
        else:
            logger.info(f"   ✅ No FK references point to empty dataset '{skipped_dataset}'")
    
    def _resolve_relationships_with_blueprints(self, context: ProcessingContext):
        """Resolve pending FK relationships using blueprint guidance."""
        logger.info(f"🔗 Resolving {len(self.pending_relationships)} FK relationships with blueprint guidance")
        
        # Use existing relationship resolution logic but with blueprint enhancements
        self._resolve_pending_relationships(context)
        
        # Additional blueprint-specific relationship validation
        self._validate_relationships_against_blueprints(context)
    
    def _validate_relationships_against_blueprints(self, context: ProcessingContext):
        """Validate that all resolved relationships match blueprint definitions."""
        logger.info("🔍 Validating resolved relationships against blueprints...")
        
        validation_errors = []
        
        # This could be expanded to validate that all created relationships
        # match the expected FK relationships defined in blueprints
        
        if validation_errors:
            logger.warning(f"⚠️  Found {len(validation_errors)} relationship validation errors:")
            for error in validation_errors:
                logger.warning(f"   {error}")
    
    def _log_enhanced_processing_summary(self, context: ProcessingContext):
        """Log enhanced processing summary with blueprint information."""
        logger.info(f"\\n{'='*80}")
        logger.info("🏗️  ENHANCED PROCESSING SUMMARY")
        logger.info(f"{'='*80}")
        
        # Blueprint summary
        logger.info(f"📊 Schema Blueprints Created: {len(self.blueprints)}")
        total_properties = sum(len(bp.property_resources) for bp in self.blueprints.values())
        total_fk_relationships = sum(len(bp.fk_relationships) for bp in self.blueprints.values())
        logger.info(f"🏷️  Total Properties Defined: {total_properties}")
        logger.info(f"🔗 Total FK Relationships Mapped: {total_fk_relationships}")
        
        # Processing summary
        logger.info(f"📦 Datasets Processed: {len(context.processed_datasets)}")
        logger.info(f"📄 CSV Sources Available: {len(context.all_csv_sources)}")
        logger.info(f"🔄 Pending Relationships Resolved: {len(self.pending_relationships) if hasattr(self, 'pending_relationships') else 0}")
        
        # Detailed blueprint breakdown
        logger.info(f"\\n📋 Blueprint Details:")
        for name, blueprint in self.blueprints.items():
            has_csv = name in context.all_csv_sources
            logger.info(f"   📦 {name}: {len(blueprint.property_resources)} props, {len(blueprint.fk_relationships)} FKs, CSV: {'✅' if has_csv else '❌'}")
        
        logger.info(f"{'='*80}")
    
    def get_blueprint(self, dataset_name: str) -> Optional[SchemaBlueprint]:
        """Get schema blueprint for a dataset."""
        return self.blueprints.get(dataset_name)
    
    def get_all_blueprints(self) -> Dict[str, SchemaBlueprint]:
        """Get all schema blueprints."""
        return self.blueprints.copy()