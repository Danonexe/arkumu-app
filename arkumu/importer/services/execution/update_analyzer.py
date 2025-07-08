"""
Update analysis and change detection for execution engine.
"""

import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timezone
import dateutil.parser
import polars as pl

from arkumu.metadata.models import Resource
from arkumu.metadata.models.triples import Triple
from arkumu.common.enums import UpdateStrategy
from .resource_manager import ResourceManager
from .statistics import ExecutionStatistics

logger = logging.getLogger(__name__)


class UpdateAnalyzer:
    """
    Analyzes data changes and determines update strategies.
    
    Handles change detection, conflict resolution, and update
    strategy determination based on existing data and policies.
    """
    
    def __init__(self,
                 resource_manager: ResourceManager,
                 default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
                 timestamp_column: Optional[str] = None):
        """
        Initialize the update analyzer.
        
        Args:
            resource_manager: Resource manager for URI operations
            default_strategy: Default update strategy
            timestamp_column: Column name for timestamp-based updates
        """
        self.resource_manager = resource_manager
        self.default_strategy = default_strategy
        self.timestamp_column = timestamp_column
    
    def analyze_dataset_changes(self, 
                              dataset_name: str,
                              df: pl.DataFrame,
                              mapping_config: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Analyze what would change if we imported this DataFrame.
        
        Args:
            dataset_name: Name of the dataset
            df: Polars DataFrame with CSV data
            mapping_config: Optional mapping configuration
            
        Returns:
            Analysis report with statistics and recommendations
        """
        analysis = {
            "total_rows": df.height,
            "total_cells": 0,
            "new_resources": 0,
            "existing_resources": 0,
            "potential_updates": 0,
            "conflicts": [],
            "recommendations": [],
            "anchor_columns": [],
            "fk_columns": [],
            "multi_value_columns": []
        }
        
        if df.height == 0:
            return analysis
        
        # Identify special column types from mapping config
        if mapping_config and 'columns' in mapping_config:
            for col_name, col_config in mapping_config['columns'].items():
                if col_config.get('is_anchor', False):
                    analysis["anchor_columns"].append(col_name)
                if col_config.get('is_fk', False):
                    analysis["fk_columns"].append(col_name)
                if col_config.get('is_multi_value', False):
                    analysis["multi_value_columns"].append(col_name)
        
        # Get existing resources for this dataset
        dataset_uri_prefix = self.resource_manager.generate_dataset_uri(dataset_name)
        existing_resources = Resource.objects.filter(
            uri__startswith=dataset_uri_prefix
        ).values('uri', 'value', 'name', 'updated_at')
        
        existing_uri_map = {res['uri']: res for res in existing_resources}
        
        # Analyze each row
        for row_data in df.iter_rows(named=True):
            row_id = row_data.get('row_id', 0)
            
            for column_name, value in row_data.items():
                if column_name == 'row_id' or value is None:
                    continue
                    
                value_str = str(value).strip()
                if not value_str:
                    continue
                
                analysis["total_cells"] += 1
                
                # Generate cell URI
                display_row_id = int(row_id) + 1 if str(row_id).isdigit() else row_id
                cell_uri = self.resource_manager.generate_cell_uri(
                    dataset_name, column_name, str(display_row_id)
                )
                
                if cell_uri in existing_uri_map:
                    existing = existing_uri_map[cell_uri]
                    analysis["existing_resources"] += 1
                    
                    # Check for value changes
                    if self._would_value_change(existing, value_str):
                        analysis["potential_updates"] += 1
                        
                        conflict_info = {
                            "uri": cell_uri,
                            "column": column_name,
                            "row_id": display_row_id,
                            "existing_value": existing.get('value', ''),
                            "new_value": value_str,
                            "last_updated": existing.get('updated_at'),
                            "column_type": self._get_column_type(column_name, mapping_config)
                        }
                        
                        # Add timestamp comparison if applicable
                        if self.timestamp_column and self.timestamp_column in row_data:
                            self._add_timestamp_analysis(conflict_info, row_data, existing)
                        
                        analysis["conflicts"].append(conflict_info)
                else:
                    analysis["new_resources"] += 1
        
        # Generate recommendations
        self._generate_recommendations(analysis)
        
        return analysis
    
    def _would_value_change(self, existing_resource: Dict, new_value: str) -> bool:
        """Check if importing would change an existing value."""
        existing_value = existing_resource.get('value', '')
        
        # Handle None - consider it different from any value (including empty string)  
        if existing_value is None:
            return True
        
        return existing_value != new_value
    
    def _get_column_type(self, column_name: str, mapping_config: Optional[Dict]) -> str:
        """Get the type of column based on mapping configuration."""
        if not mapping_config or 'columns' not in mapping_config:
            return "regular"
        
        # Handle case where columns is None or not a dict
        columns = mapping_config.get('columns')
        if not columns or not isinstance(columns, dict):
            return "regular"
        
        column_config = columns.get(column_name, {})
        
        if column_config.get('is_anchor', False):
            return "anchor"
        elif column_config.get('is_fk', False):
            return "foreign_key"
        elif column_config.get('is_multi_value', False):
            return "multi_value"
        elif column_config.get('is_relationship_context', False):
            return "relationship_context"
        elif column_config.get('is_external_ontology', False):
            return "external_ontology"
        else:
            return "regular"
    
    def _add_timestamp_analysis(self, conflict_info: Dict, row_data: Dict, existing_resource: Dict) -> None:
        """Add timestamp comparison to conflict analysis."""
        new_timestamp_str = str(row_data.get(self.timestamp_column, '')).strip()
        new_timestamp = self._parse_timestamp(new_timestamp_str)
        
        if new_timestamp:
            existing_timestamp = existing_resource.get('updated_at')
            
            conflict_info.update({
                "new_timestamp": new_timestamp_str,
                "new_timestamp_parsed": new_timestamp.isoformat(),
                "existing_timestamp": existing_timestamp.isoformat() if existing_timestamp else None,
                "timestamp_comparison": self._compare_timestamps(new_timestamp, existing_timestamp)
            })
    
    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse a timestamp string into a datetime object."""
        if not timestamp_str:
            return None
        
        try:
            # Try common formats first
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d",
                "%d.%m.%Y",
                "%d/%m/%Y",
                "%m/%d/%Y"
            ]:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue
            
            # Fallback to dateutil parser
            return dateutil.parser.parse(timestamp_str, default=datetime.now(timezone.utc))
            
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None
    
    def _compare_timestamps(self, new_timestamp: datetime, existing_timestamp: Optional[datetime]) -> str:
        """Compare timestamps and return comparison result."""
        if not existing_timestamp:
            return "unknown"
        
        if new_timestamp > existing_timestamp:
            return "newer"
        elif new_timestamp < existing_timestamp:
            return "older"
        else:
            return "equal"
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> None:
        """Generate recommendations based on analysis results."""
        recommendations = []
        
        if analysis["potential_updates"] > 0:
            recommendations.append(
                f"Found {analysis['potential_updates']} potential updates. "
                f"Consider using UPDATE_VALUES strategy."
            )
        
        if analysis["existing_resources"] > analysis["new_resources"]:
            recommendations.append(
                "Mostly existing data detected. Consider SKIP_EXISTING for faster processing."
            )
        
        if analysis["fk_columns"]:
            recommendations.append(
                f"Foreign key columns detected: {analysis['fk_columns']}. "
                f"Ensure target datasets are imported first."
            )
        
        if analysis["anchor_columns"]:
            recommendations.append(
                f"Anchor columns detected: {analysis['anchor_columns']}. "
                f"These will be used for cross-dataset linking."
            )
        
        if analysis["multi_value_columns"]:
            recommendations.append(
                f"Multi-value columns detected: {analysis['multi_value_columns']}. "
                f"Values will be split according to mapping configuration."
            )
        
        analysis["recommendations"] = recommendations
    
    def determine_update_strategy(self, 
                                existing_resource: Optional[Resource],
                                new_value: str,
                                row_data: Dict,
                                column_config: Optional[Dict] = None) -> UpdateStrategy:
        """
        Determine the appropriate update strategy for a specific cell.
        
        Args:
            existing_resource: Existing resource if any
            new_value: New value to be imported
            row_data: Full row data for context
            column_config: Configuration for this column
            
        Returns:
            Appropriate update strategy
        """
        if not existing_resource:
            return UpdateStrategy.UPDATE_VALUES  # Create new
        
        # Check if value would actually change
        if existing_resource.value == new_value:
            return UpdateStrategy.SKIP_EXISTING
        
        # Use default strategy for most cases
        if self.default_strategy == UpdateStrategy.SKIP_EXISTING:
            return UpdateStrategy.SKIP_EXISTING
        elif self.default_strategy == UpdateStrategy.UPDATE_VALUES:
            return UpdateStrategy.UPDATE_VALUES
        elif self.default_strategy == UpdateStrategy.TIMESTAMP_BASED:
            return self._determine_timestamp_based_strategy(existing_resource, row_data)
        else:
            return UpdateStrategy.UPDATE_VALUES
    
    def _determine_timestamp_based_strategy(self, 
                                          existing_resource: Resource,
                                          row_data: Dict) -> UpdateStrategy:
        """Determine strategy based on timestamp comparison."""
        if not self.timestamp_column or self.timestamp_column not in row_data:
            return UpdateStrategy.UPDATE_VALUES
        
        new_timestamp_str = str(row_data.get(self.timestamp_column, '')).strip()
        new_timestamp = self._parse_timestamp(new_timestamp_str)
        
        if not new_timestamp:
            return UpdateStrategy.UPDATE_VALUES
        
        existing_timestamp = existing_resource.updated_at
        if not existing_timestamp:
            return UpdateStrategy.UPDATE_VALUES
        
        # Update if new timestamp is newer
        if new_timestamp > existing_timestamp:
            return UpdateStrategy.UPDATE_VALUES
        else:
            return UpdateStrategy.SKIP_EXISTING 