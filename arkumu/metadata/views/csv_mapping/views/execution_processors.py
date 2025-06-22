"""
CSV Mapping Execution Processors

This module contains the core processing logic for different execution strategies:
- Multi-phase streaming processors
- Entity-centric processors  
- Relationship and context processors
- Phase-specific batch processors

Extracted from execution_views.py to improve maintainability.
"""

import logging
import polars as pl
from django.db import transaction
from typing import Dict, List, Any, Optional

from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.smart_bulk_updater import BulkUpdateStats, UpdateStrategy
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
from arkumu.importer.services.importer.entity_centric_processor import EntityCentricMappingProcessor
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer

logger = logging.getLogger(__name__)


class MultiPhaseProcessor:
    """Handles multi-phase streaming execution with proper dependency ordering."""
    
    def __init__(self, organization_id: str, base_uri: str = "http://arkumu.org/data"):
        self.organization_id = organization_id
        self.base_uri = base_uri
    
    def process_phase_streaming(self, smart_updater, dataset_sources, phase_columns, 
                               phase_type, strategy, request=None):
        """Process a specific phase across all datasets using streaming."""
        analyzer = S3DirectDataAnalyzer()
        phase_stats = None
        
        # Get column names for this phase
        phase_column_names = [col.get('name') for col in phase_columns if col.get('name')]
        logger.info(f"Processing phase '{phase_type}' with columns: {phase_column_names}")
        
        for source_data in dataset_sources:
            source_info = source_data['source_info']
            ds_name = source_data['dataset_name']
            
            try:
                batch_size = 5000  # Process 5K rows at a time
                total_rows = analyzer._get_total_row_count_safe(source_info, ds_name)
                
                for offset in range(0, total_rows, batch_size):
                    # Get batch data
                    batch_preview = analyzer.get_s3_table_preview(
                        source_info, ds_name,
                        offset=offset, 
                        limit=min(batch_size, total_rows - offset)
                    )
                    
                    if not batch_preview.data_rows:
                        break
                    
                    # Filter batch to only include columns relevant to this phase
                    filtered_batch_data = []
                    column_indices = {}
                    
                    # Map column names to indices
                    for i, col_name in enumerate(batch_preview.column_headers):
                        column_indices[col_name] = i
                    
                    # Process each row, but only include phase-relevant columns
                    for row in batch_preview.data_rows:
                        row_dict = {}
                        
                        # Always include the primary identifier columns for entity linking
                        for i, col_name in enumerate(batch_preview.column_headers):
                            if col_name in phase_column_names:
                                # Include columns relevant to this phase
                                row_dict[col_name] = row[i]
                            elif phase_type in ['relationships', 'contexts'] and self._is_identifier_column(col_name):
                                # Include ID columns for relationship processing
                                row_dict[col_name] = row[i]
                        
                        # Add dataset context
                        row_dict['__dataset_name__'] = ds_name
                        row_dict['__source_name__'] = self.organization_id
                        row_dict['__phase_type__'] = phase_type
                        
                        if row_dict:  # Only add if we have relevant data
                            filtered_batch_data.append(row_dict)
                    
                    if not filtered_batch_data:
                        continue
                    
                    # Convert to DataFrame for processing
                    batch_df = pl.DataFrame(filtered_batch_data)
                    
                    # Process batch with phase-specific configuration
                    with transaction.atomic():
                        if phase_type == "entities":
                            # Choose between predicate-based or standard cell-based processing
                            use_predicates = (request and 
                                            request.POST.get('use_column_predicates', 'true').lower() == 'true')
                            
                            if use_predicates:
                                # NEW: Use column names as predicates for semantic RDF
                                processor = EntityProcessor(self.organization_id, self.base_uri)
                                batch_stats = processor.process_entity_batch_with_predicates(
                                    batch_df, ds_name, phase_columns, strategy
                                )
                            else:
                                # EXISTING: Use standard cell-based processing
                                batch_stats = smart_updater.import_csv_with_smart_updates(
                                    csv_data=batch_df,
                                    dataset_name=f"{ds_name}_entities",
                                    strategy=self._convert_strategy_string(strategy)
                                )
                        elif phase_type == "literals":
                            # For literals: Use standard cell-based approach
                            batch_stats = smart_updater.import_csv_with_smart_updates(
                                csv_data=batch_df,
                                dataset_name=f"{ds_name}_literals",
                                strategy=self._convert_strategy_string(strategy)
                            )
                        elif phase_type == "relationships":
                            # For relationships: Custom FK processing
                            processor = RelationshipProcessor(self.organization_id, self.base_uri)
                            batch_stats = processor.process_relationship_batch(
                                batch_df, ds_name, phase_columns, strategy
                            )
                        elif phase_type == "contexts":
                            # For contexts: Custom junction table processing
                            processor = ContextProcessor(self.organization_id, self.base_uri)
                            batch_stats = processor.process_context_batch(
                                smart_updater, batch_df, ds_name, phase_columns, strategy
                            )
                        else:
                            # Fallback to standard processing
                            batch_stats = smart_updater.import_csv_with_smart_updates(
                                csv_data=batch_df,
                                dataset_name=f"{ds_name}_{phase_type}",
                                strategy=self._convert_strategy_string(strategy)
                            )
                    
                    # Merge with cumulative stats
                    if phase_stats is None:
                        phase_stats = batch_stats
                    else:
                        phase_stats.merge(batch_stats)
                    
                    logger.info(f"Processed batch {offset//batch_size + 1}: {len(filtered_batch_data)} rows")
                
            except Exception as e:
                logger.error(f"Error processing {ds_name} in phase {phase_type}: {e}", exc_info=True)
                raise
        
        return phase_stats or BulkUpdateStats()
    
    def _is_identifier_column(self, column_name):
        """Check if a column is likely an identifier (for relationship processing)."""
        id_patterns = ['id', 'uuid', 'key', 'identifier', 'ref']
        column_lower = column_name.lower()
        return any(pattern in column_lower for pattern in id_patterns)
    
    def _convert_strategy_string(self, strategy_str: str) -> UpdateStrategy:
        """Convert string strategy to UpdateStrategy enum."""
        strategy_map = {
            'SKIP_EXISTING': UpdateStrategy.SKIP_EXISTING,
            'UPDATE_VALUES': UpdateStrategy.UPDATE_VALUES,
            'REPLACE_ALL': UpdateStrategy.UPDATE_VALUES,  # Map to UPDATE_VALUES
            'TIMESTAMP_BASED': UpdateStrategy.TIMESTAMP_BASED
        }
        return strategy_map.get(strategy_str, UpdateStrategy.SKIP_EXISTING)


class EntityProcessor:
    """Handles entity creation with direct predicate relationships."""
    
    def __init__(self, organization_id: str, base_uri: str = "http://arkumu.org/data"):
        self.organization_id = organization_id
        self.base_uri = base_uri
    
    def process_entity_batch_with_predicates(self, batch_df, dataset_name, anchor_columns, strategy):
        """
        Process entity batch using column names as predicates instead of cell-based approach.
        Creates: Entity → columnName → literalValue (direct predicate relationships)
        """
        stats = BulkUpdateStats()
        
        if batch_df.height == 0:
            return stats
        
        logger.info(f"Processing {batch_df.height} entity rows with predicate approach for dataset: {dataset_name}")
        
        # Extract column configurations
        column_configs = {col.get('name'): col for col in anchor_columns}
        
        # Process each row to create entities with direct predicate relationships
        for row_data in batch_df.iter_rows(named=True):
            try:
                # Determine entity ID (use first anchor column or row index)
                entity_id = None
                for col_name, col_config in column_configs.items():
                    if col_config.get('is_primary_key', False) or not entity_id:
                        entity_id = row_data.get(col_name)
                        if entity_id:
                            break
                
                if not entity_id:
                    continue
                
                # Create entity resource
                safe_entity_id = slugify_uri_part(str(entity_id))
                entity_uri = mint_uri(self.base_uri, self.organization_id, "entities", dataset_name, safe_entity_id)
                
                entity_resource, entity_created = Resource.objects.get_or_create(
                    uri=entity_uri,
                    defaults={
                        "resource_type": ResourceType.IRI,
                        "name": f"{dataset_name} Entity {entity_id}",
                        "source": self.organization_id
                    }
                )
                
                if entity_created:
                    stats.resources_created += 1
                
                # Create property triples for each column
                for col_name, col_config in column_configs.items():
                    value = row_data.get(col_name)
                    if value is None or str(value).strip() == '':
                        continue
                    
                    # Create property resource
                    arkumu_type = col_config.get('arkumu_type', col_name)
                    safe_property_name = slugify_uri_part(arkumu_type)
                    
                    # Use semantic property URI based on arkumu_type
                    if arkumu_type.startswith('http://') or arkumu_type.startswith('https://'):
                        property_uri = arkumu_type  # Use external ontology URI directly
                    else:
                        property_uri = mint_uri(self.base_uri, self.organization_id, "properties", safe_property_name)
                    
                    property_resource, prop_created = Resource.objects.get_or_create(
                        uri=property_uri,
                        defaults={
                            "resource_type": ResourceType.PROPERTY,
                            "name": arkumu_type,
                            "source": self.organization_id
                        }
                    )
                    
                    if prop_created:
                        stats.resources_created += 1
                    
                    # Create literal value resource
                    value_str = str(value).strip()
                    datatype = col_config.get('datatype', 'http://www.w3.org/2001/XMLSchema#string')
                    
                    literal_resource, lit_created = Resource.objects.get_or_create(
                        value=value_str,
                        resource_type=ResourceType.LITERAL,
                        datatype=datatype,
                        defaults={
                            "name": value_str,
                            "source": self.organization_id
                        }
                    )
                    
                    if lit_created:
                        stats.resources_created += 1
                    
                    # Create the direct predicate triple: Entity → Property → Literal
                    triple, triple_created = Triple.objects.get_or_create(
                        subject=entity_resource,
                        predicate=property_resource,
                        object=literal_resource
                    )
                    
                    if triple_created:
                        stats.triples_created += 1
                        stats.total_values_created += 1
                
                stats.rows_processed += 1
                
            except Exception as e:
                logger.error(f"Error processing entity row: {e}", exc_info=True)
                stats.errors += 1
        
        logger.info(f"Entity predicate processing completed: {stats.rows_processed} entities, "
                   f"{stats.triples_created} direct predicate triples created")
        
        return stats


class RelationshipProcessor:
    """Handles FK relationship processing with proper relationship triples."""
    
    def __init__(self, organization_id: str, base_uri: str = "http://arkumu.org/data"):
        self.organization_id = organization_id
        self.base_uri = base_uri
    
    def process_relationship_batch(self, batch_df, ds_name, phase_columns, strategy):
        """Process FK relationship columns to create proper relationship triples.
        
        CRITICAL FIX: Previous implementation stored FK values as literals instead of relationships.
        This implementation creates proper RDF relationship triples.
        """
        stats = BulkUpdateStats()
        
        if batch_df.height == 0:
            return stats
        
        logger.info(f"Processing {batch_df.height} relationship rows for dataset: {ds_name}")
        
        # Extract relationship column configurations
        relationship_configs = {col.get('name'): col for col in phase_columns}
        
        # Process each row to create relationship triples
        for row_data in batch_df.iter_rows(named=True):
            try:
                # Find source entity (using identifier columns)
                source_entity_id = None
                for col_name, value in row_data.items():
                    if self._is_identifier_column(col_name) and value:
                        source_entity_id = value
                        break
                
                if not source_entity_id:
                    continue
                
                # Generate source entity URI
                safe_source_id = slugify_uri_part(str(source_entity_id))
                source_entity_uri = mint_uri(self.base_uri, row_data.get('__source_name__'), 
                                           "entities", ds_name, safe_source_id)
                
                # Get source entity (should exist from Phase 1)
                try:
                    source_entity = Resource.objects.get(uri=source_entity_uri)
                except Resource.DoesNotExist:
                    logger.warning(f"Source entity not found: {source_entity_uri}")
                    continue
                
                # Process each relationship column
                for col_name, col_config in relationship_configs.items():
                    fk_value = row_data.get(col_name)
                    if not fk_value or str(fk_value).strip() == '':
                        continue
                    
                    # Handle multi-value FKs (comma-separated)
                    if col_config.get('is_multi_value', False):
                        separator = col_config.get('multi_value_separator', ',')
                        fk_values = [v.strip() for v in str(fk_value).split(separator) if v.strip()]
                    else:
                        fk_values = [str(fk_value).strip()]
                    
                    # Create relationship triples for each FK value
                    for fk_val in fk_values:
                        # Generate target entity URI
                        target_dataset = col_config.get('target_dataset', 'unknown')
                        safe_target_id = slugify_uri_part(str(fk_val))
                        target_entity_uri = mint_uri(self.base_uri, row_data.get('__source_name__'),
                                                   "entities", target_dataset, safe_target_id)
                        
                        # Get or create target entity (stub if needed)
                        target_entity, target_created = Resource.objects.get_or_create(
                            uri=target_entity_uri,
                            defaults={
                                "resource_type": ResourceType.IRI,
                                "name": f"{target_dataset} Entity {fk_val}",
                                "source": row_data.get('__source_name__')
                            }
                        )
                        
                        if target_created:
                            stats.resources_created += 1
                            logger.debug(f"Created stub entity: {target_entity_uri}")
                        
                        # Create relationship property
                        relationship_type = col_config.get('arkumu_type', col_name)
                        safe_rel_name = slugify_uri_part(relationship_type)
                        relationship_uri = mint_uri(self.base_uri, row_data.get('__source_name__'),
                                                  "relationships", safe_rel_name)
                        
                        relationship_property, rel_created = Resource.objects.get_or_create(
                            uri=relationship_uri,
                            defaults={
                                "resource_type": ResourceType.PROPERTY,
                                "name": relationship_type,
                                "source": row_data.get('__source_name__')
                            }
                        )
                        
                        # Create relationship triple
                        triple, triple_created = Triple.objects.get_or_create(
                            subject=source_entity,
                            predicate=relationship_property,
                            object=target_entity
                        )
                        
                        if triple_created:
                            stats.triples_created += 1
                            logger.debug(f"Created relationship: {source_entity_uri} → {relationship_type} → {target_entity_uri}")
                
                stats.rows_processed += 1
                
            except Exception as e:
                logger.error(f"Error processing relationship row: {e}", exc_info=True)
                stats.errors += 1
        
        logger.info(f"Relationship processing completed: {stats}")
        return stats
    
    def _is_identifier_column(self, column_name):
        """Check if a column is likely an identifier (for relationship processing)."""
        id_patterns = ['id', 'uuid', 'key', 'identifier', 'ref']
        column_lower = column_name.lower()
        return any(pattern in column_lower for pattern in id_patterns)


class ContextProcessor:
    """Handles junction table and relationship context processing."""
    
    def __init__(self, organization_id: str, base_uri: str = "http://arkumu.org/data"):
        self.organization_id = organization_id
        self.base_uri = base_uri
    
    def process_context_batch(self, smart_updater, batch_df, ds_name, phase_columns, strategy):
        """Process relationship context columns (junction tables)."""
        # TODO: Implement proper junction table processing
        # For now, use standard processing but this could be enhanced
        # to create proper junction entities and linking triples
        from arkumu.importer.services.importer.smart_bulk_updater import UpdateStrategy
        
        strategy_map = {
            'SKIP_EXISTING': UpdateStrategy.SKIP_EXISTING,
            'UPDATE_VALUES': UpdateStrategy.UPDATE_VALUES,
            'REPLACE_ALL': UpdateStrategy.UPDATE_VALUES,
            'TIMESTAMP_BASED': UpdateStrategy.TIMESTAMP_BASED
        }
        
        return smart_updater.import_csv_with_smart_updates(
            csv_data=batch_df,
            dataset_name=f"{ds_name}_contexts",
            strategy=strategy_map.get(strategy, UpdateStrategy.SKIP_EXISTING)
        )


class EntityCentricProcessor:
    """Handles entity-centric single-pass processing."""
    
    def __init__(self, organization_id: str, base_uri: str = "http://arkumu.org/data"):
        self.organization_id = organization_id
        self.base_uri = base_uri
    
    def execute_mapping_entity_centric(self, mapping_config: Dict[str, Any],
                                     dataset_sources: List[Dict[str, Any]],
                                     dataset_name: str,
                                     strategy: str = 'SKIP_EXISTING') -> Dict[str, Any]:
        """Execute mapping using entity-centric approach - single pass, complete entities."""
        
        logger.info(f"Starting entity-centric mapping execution for {dataset_name}")
        
        # Initialize entity-centric processor
        entity_processor = EntityCentricMappingProcessor(
            base_uri=self.base_uri,
            institution=self.organization_id,
            default_strategy=self._convert_strategy_string(strategy)
        )
        
        # Load data for all datasets (single pass approach)
        analyzer = S3DirectDataAnalyzer()
        all_data = []
        
        for source_data in dataset_sources:
            source_info = source_data['source_info']
            ds_name = source_data['dataset_name']
            
            try:
                # Load complete dataset (entity-centric needs full data for relationships)
                dataset_data = analyzer.get_full_dataset_data(self.organization_id, ds_name)
                
                # Add dataset context to each row
                for row in dataset_data:
                    row['__dataset_name__'] = ds_name
                    row['__source_name__'] = self.organization_id
                
                all_data.extend(dataset_data)
                logger.info(f"Loaded {len(dataset_data)} rows from dataset: {ds_name}")
                
            except Exception as e:
                logger.error(f"Error loading dataset {ds_name}: {e}")
                raise
        
        if not all_data:
            raise Exception("No data loaded for entity-centric processing")
        
        # Process with entity-centric approach
        try:
            results = entity_processor.process_gui_mapping_entity_centric(
                mapping_config=mapping_config,
                csv_data=all_data,
                organization_id=self.organization_id,
                dataset_name=dataset_name
            )
            
            # Convert to expected format
            return {
                'total_rows_processed': results.get('total_rows', 0),
                'total_resources_created': results.get('total_resources_created', 0),
                'total_triples_created': results.get('total_triples_created', 0),
                'total_values_created': results.get('total_values_created', 0),
                'resources_updated': 0,  # Entity-centric doesn't track updates separately
                'resources_skipped': 0,
                'errors': results.get('total_errors', 0),
                'truncated_values': 0,
                'cells_processed': len(all_data),
                'engine_used': 'EntityCentricMappingProcessor',
                'datasets_processed': len(dataset_sources),
                'processing_method': 'entity_centric_single_pass',
                'entity_models_used': results.get('entity_models_used', 0)
            }
            
        except Exception as e:
            logger.error(f"Entity-centric processing failed: {e}", exc_info=True)
            raise Exception(f"Entity-centric processing failed: {str(e)}")
    
    def _convert_strategy_string(self, strategy_str: str) -> UpdateStrategy:
        """Convert string strategy to UpdateStrategy enum."""
        strategy_map = {
            'SKIP_EXISTING': UpdateStrategy.SKIP_EXISTING,
            'UPDATE_VALUES': UpdateStrategy.UPDATE_VALUES,
            'REPLACE_ALL': UpdateStrategy.UPDATE_VALUES,
            'TIMESTAMP_BASED': UpdateStrategy.TIMESTAMP_BASED
        }
        return strategy_map.get(strategy_str, UpdateStrategy.SKIP_EXISTING) 