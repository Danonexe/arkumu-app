"""
Main execution engine for mapping-aware data import.
"""

import logging
from typing import Dict, List, Any, Optional, Union
import polars as pl

from arkumu.importer.services.importer.smart_bulk_updater import UpdateStrategy
from arkumu.metadata.services.mapping import MappingCoordinator, FKProcessingPlan
from .data_processor import DataProcessor
from .resource_manager import ResourceManager
from .update_analyzer import UpdateAnalyzer
from .statistics import ExecutionStatistics, ExecutionMetrics

logger = logging.getLogger(__name__)


class MappingExecutionEngine:
    """
    High-performance execution engine with mapping configuration support.
    
    Orchestrates data processing, resource management, and update analysis
    to execute sophisticated mapping configurations including FK relationships,
    external ontologies, and multi-value fields.
    """
    
    def __init__(self,
                 organization_id: str,
                 base_uri: str,
                 default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
                 timestamp_column: Optional[str] = None,
                 batch_size: int = 1000):
        """
        Initialize the mapping execution engine.
        
        Args:
            organization_id: Organization identifier for URI generation
            base_uri: Base URI for resource generation
            default_strategy: Default update strategy
            timestamp_column: Column for timestamp-based updates
            batch_size: Batch size for bulk operations
        """
        self.organization_id = organization_id
        self.base_uri = base_uri
        self.default_strategy = default_strategy
        self.timestamp_column = timestamp_column
        self.batch_size = batch_size
        
        # Initialize component services
        self.statistics = ExecutionStatistics()
        self.data_processor = DataProcessor()
        self.resource_manager = ResourceManager(
            institution=organization_id,
            base_uri=base_uri,
            statistics=self.statistics
        )
        self.update_analyzer = UpdateAnalyzer(
            resource_manager=self.resource_manager,
            default_strategy=default_strategy,
            timestamp_column=timestamp_column
        )
        
        # Initialize mapping coordinator for FK/ontology processing
        self.mapping_coordinator = MappingCoordinator(organization_id, base_uri)
    
    def execute_with_processing_plan(self,
                                   csv_data: Union[List[Dict[str, Any]], pl.DataFrame],
                                   processing_plan: FKProcessingPlan,
                                   dataset_name: str,
                                   workspace_columns: List[Dict]) -> ExecutionMetrics:
        """
        Execute import using a complete FK processing plan.
        
        Args:
            csv_data: Input data
            processing_plan: Complete processing plan from mapping coordinator
            dataset_name: Name of the dataset
            workspace_columns: Column configurations
            
        Returns:
            Execution metrics
        """
        logger.info(f"Starting execution with processing plan for dataset: {dataset_name}")
        self.statistics.start_execution()
        self.statistics.start_dataset(dataset_name)
        
        try:
            # Extract mapping configuration for this dataset
            mapping_config = self._extract_mapping_config(dataset_name, workspace_columns)
            
            # Execute the import
            return self._execute_dataset_import(csv_data, dataset_name, mapping_config)
            
        except Exception as e:
            self.statistics.add_error(f"Execution failed: {e}", dataset_name)
            logger.error(f"Execution failed for {dataset_name}: {e}", exc_info=True)
            raise
        finally:
            self.statistics.end_dataset(dataset_name)
            self.statistics.end_execution()
    
    def execute_simple_import(self,
                            csv_data: Union[List[Dict[str, Any]], pl.DataFrame],
                            dataset_name: str,
                            mapping_config: Optional[Dict] = None) -> ExecutionMetrics:
        """
        Execute a simple import without complex FK processing.
        
        Args:
            csv_data: Input data
            dataset_name: Name of the dataset
            mapping_config: Optional mapping configuration
            
        Returns:
            Execution metrics
        """
        logger.info(f"Starting simple import for dataset: {dataset_name}")
        self.statistics.start_execution()
        self.statistics.start_dataset(dataset_name)
        
        try:
            return self._execute_dataset_import(csv_data, dataset_name, mapping_config)
        except Exception as e:
            self.statistics.add_error(f"Simple import failed: {e}", dataset_name)
            logger.error(f"Simple import failed for {dataset_name}: {e}", exc_info=True)
            raise
        finally:
            self.statistics.end_dataset(dataset_name)
            self.statistics.end_execution()
    
    def analyze_import_impact(self,
                            csv_data: Union[List[Dict[str, Any]], pl.DataFrame],
                            dataset_name: str,
                            mapping_config: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Analyze what would happen if we imported this data (dry run).
        
        Args:
            csv_data: Input data
            dataset_name: Name of the dataset
            mapping_config: Optional mapping configuration
            
        Returns:
            Analysis report
        """
        logger.info(f"Analyzing import impact for dataset: {dataset_name}")
        
        # Prepare data
        df = self.data_processor.prepare_for_processing(csv_data, mapping_config)
        
        # Analyze changes
        return self.update_analyzer.analyze_dataset_changes(dataset_name, df, mapping_config)
    
    def _execute_dataset_import(self,
                              csv_data: Union[List[Dict[str, Any]], pl.DataFrame],
                              dataset_name: str,
                              mapping_config: Optional[Dict] = None) -> ExecutionMetrics:
        """
        Execute the actual dataset import.
        
        Args:
            csv_data: Input data
            dataset_name: Name of the dataset
            mapping_config: Optional mapping configuration
            
        Returns:
            Execution metrics
        """
        # Step 1: Prepare data
        logger.info(f"Step 1: Preparing data for {dataset_name}")
        df = self.data_processor.prepare_for_processing(csv_data, mapping_config)
        
        if df.height == 0:
            logger.warning(f"No data to import for {dataset_name}")
            return self.statistics.current_metrics
        
        # Step 2: Create dataset and structural resources
        logger.info(f"Step 2: Creating dataset and structural resources")
        dataset_resource = self.resource_manager.create_dataset_resource(dataset_name)
        
        # Get column names (excluding row_id)
        data_columns = [col for col in df.columns if col != 'row_id']
        column_resources = self.resource_manager.create_column_resources(dataset_name, data_columns)
        
        # Create row resources if needed (based on topology)
        row_resources = None
        if self._should_create_row_resources(mapping_config):
            row_ids = set(str(int(row_id) + 1) for row_id in df['row_id'].to_list())
            row_resources = self.resource_manager.create_row_resources(dataset_name, row_ids)
        
        # Create structural triples
        self.resource_manager.create_structural_triples_bulk(
            dataset_resource, column_resources, row_resources
        )
        
        # Step 3: Process data in batches
        logger.info(f"Step 3: Processing {df.height} rows in batches of {self.batch_size}")
        total_rows = df.height
        
        for batch_start in range(0, total_rows, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total_rows)
            batch_df = df[batch_start:batch_end]
            
            logger.debug(f"Processing batch {batch_start}-{batch_end}")
            self._process_batch(batch_df, dataset_name, mapping_config, column_resources)
        
        # Step 4: Handle special column types (FK, external ontology, etc.)
        if mapping_config:
            self._process_special_columns(df, dataset_name, mapping_config)
        
        return self.statistics.current_metrics
    
    def _process_batch(self,
                      batch_df: pl.DataFrame,
                      dataset_name: str,
                      mapping_config: Optional[Dict],
                      column_resources: Dict[str, Any]) -> None:
        """Process a batch of rows."""
        logger.debug(f"Processing batch with {batch_df.height} rows")
        cell_data = []
        value_data = []
        
        # Collect cell and value data
        for row_data in batch_df.iter_rows(named=True):
            row_id = row_data.get('row_id', 0)
            display_row_id = int(row_id) + 1 if str(row_id).isdigit() else row_id
            
            for column_name, value in row_data.items():
                if column_name == 'row_id' or value is None:
                    continue
                
                value_str = str(value).strip()
                if not value_str:
                    continue
                
                cell_data.append((dataset_name, column_name, str(display_row_id)))
                value_data.append((value_str, "http://www.w3.org/2001/XMLSchema#string"))
        
        logger.debug(f"Collected {len(cell_data)} cell data items, {len(value_data)} value data items")
        
        if not cell_data:
            logger.debug("No cell data to process, returning early")
            return
        
        # Create cell resources
        logger.debug("Creating cell resources...")
        cell_resources = self.resource_manager.create_cell_resources_bulk(cell_data)
        logger.debug(f"Created {len(cell_resources)} cell resources")
        
        # Create value resources
        logger.debug("Creating value resources...")
        unique_values = list(set(value_data))
        value_resources = self.resource_manager.create_value_resources_bulk(unique_values)
        logger.debug(f"Created {len(value_resources)} value resources")
        
        # Create value triples
        cell_value_pairs = []
        value_index = 0
        
        for row_data in batch_df.iter_rows(named=True):
            row_id = row_data.get('row_id', 0)
            display_row_id = int(row_id) + 1 if str(row_id).isdigit() else row_id
            
            for column_name, value in row_data.items():
                if column_name == 'row_id' or value is None:
                    continue
                
                value_str = str(value).strip()
                if not value_str:
                    continue
                
                cell_uri = self.resource_manager.generate_cell_uri(
                    dataset_name, column_name, str(display_row_id)
                )
                
                if cell_uri in cell_resources and value_str in value_resources:
                    cell_value_pairs.append((cell_resources[cell_uri], value_resources[value_str]))
        
        logger.debug(f"Prepared {len(cell_value_pairs)} cell-value pairs")
        
        # Create all value triples at once
        if cell_value_pairs:
            logger.debug("Creating value triples...")
            self.resource_manager.create_value_triples_bulk(cell_value_pairs)
            logger.debug("Value triples created successfully")
        
        # Update statistics
        self.statistics.current_metrics.cells_processed += len(cell_data)
        logger.debug(f"Updated statistics: cells_processed = {self.statistics.current_metrics.cells_processed}")
    
    def _extract_mapping_config(self, dataset_name: str, workspace_columns: List[Dict]) -> Optional[Dict]:
        """Extract mapping configuration for a specific dataset."""
        # Find columns for this dataset
        dataset_columns = [
            col for col in workspace_columns 
            if col.get('dataset_name') == dataset_name
        ]
        
        if not dataset_columns:
            return None
        
        mapping_config = {
            'columns': {}
        }
        
        for col in dataset_columns:
            col_name = col.get('column_name')
            if col_name:
                mapping_config['columns'][col_name] = {
                    'is_anchor': col.get('is_anchor', False),
                    'is_fk': col.get('is_fk', False),
                    'is_multi_value': col.get('is_multi_value', False),
                    'is_relationship_context': col.get('is_relationship_context', False),
                    'is_external_ontology': col.get('is_external_ontology', False),
                    'target_dataset': col.get('target_dataset'),
                    'target_column': col.get('target_column'),
                    'separator': col.get('separator', ',')
                }
        
        return mapping_config
    
    def _should_create_row_resources(self, mapping_config: Optional[Dict]) -> bool:
        """Determine if row resources should be created based on configuration."""
        # For now, default to not creating row resources (column-only topology)
        # This can be made configurable later
        return False
    
    def _process_special_columns(self,
                               df: pl.DataFrame,
                               dataset_name: str,
                               mapping_config: Dict) -> None:
        """Process special column types (FK, external ontology, etc.)."""
        if 'columns' not in mapping_config:
            return
        
        # Count special column types for statistics
        for col_name, col_config in mapping_config['columns'].items():
            if col_config.get('is_fk', False):
                # Placeholder for FK processing
                logger.debug(f"FK column detected: {col_name} -> {col_config.get('target_dataset')}")
                # TODO: Implement FK relationship creation
                
            elif col_config.get('is_external_ontology', False):
                # Placeholder for external ontology processing
                logger.debug(f"External ontology column detected: {col_name}")
                # TODO: Implement external ontology lookup
                
            elif col_config.get('is_multi_value', False):
                # Placeholder for multi-value processing
                logger.debug(f"Multi-value column detected: {col_name}")
                # TODO: Implement multi-value splitting
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get a complete execution summary."""
        summary = self.statistics.get_summary()
        summary['engine_info'] = {
            'organization_id': self.organization_id,
            'base_uri': self.base_uri,
            'batch_size': self.batch_size,
            'default_strategy': self.default_strategy.name
        }
        return summary 