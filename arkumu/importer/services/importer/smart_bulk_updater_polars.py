import logging
import polars as pl
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timezone
import dateutil.parser
from django.db import transaction
import re

from arkumu.metadata.models import Resource
from arkumu.metadata.models.resource import ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
from arkumu.importer.services.importer.smart_bulk_updater import (
    UpdateStrategy, BulkUpdateStats, ResourceUpdate, MAX_INDEXED_VALUE_SIZE
)

# Note: We use vectorized Unicode normalization with Polars df.str.normalize("NFC") 
# instead of the old per-cell normalize_string_nfc() function for better performance

logger = logging.getLogger(__name__)


class SmartBulkUpdaterPolars:
    """
    Polars-optimized version of SmartBulkUpdater.
    
    This version uses Polars DataFrames for significantly better performance
    on data analysis and processing operations, especially for large datasets.
    """
    
    def __init__(self, 
                 default_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
                 timestamp_column: Optional[str] = None,
                 institution: str = "DEFAULT",
                 base_uri: str = "http://arkumu.org/data",
                 link_row_cells: bool = True,
                 link_topology: str = "row",
                 multi_value_threshold: float = 0.2
                 ):
        """
        Initialize the Polars-optimized smart bulk updater.
        
        Args:
            default_strategy: Default strategy for handling existing resources
            timestamp_column: Column name containing timestamps for timestamp-based updates
            institution: Institution code for URI generation
            base_uri: Base URI for resource generation
            link_row_cells: Whether to link cells to rows
            link_topology: Topology for linking cells to rows
            multi_value_threshold: Threshold for detecting multi-value columns (0.2 = 20%)
        """
        self.default_strategy = default_strategy
        self.timestamp_column = timestamp_column
        self.institution = institution
        self.base_uri = base_uri
        self.link_row_cells = link_row_cells
        self.link_topology = link_topology
        self.multi_value_threshold = multi_value_threshold
        
        # Initialize standard RDF properties
        try:
            with transaction.atomic():
                self.has_part_prop, _ = Resource.objects.update_or_create(
                    uri="http://purl.org/dc/terms/hasPart",
                    defaults={"resource_type": ResourceType.PROPERTY, "name": "hasPart", "source": self.institution, "is_placeholder": False}
                )
                self.rdf_value_prop, _ = Resource.objects.update_or_create(
                    uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
                    defaults={"resource_type": ResourceType.PROPERTY, "name": "value", "source": self.institution, "is_placeholder": False}
                )
                self.dcterms_relation_prop, _ = Resource.objects.update_or_create(
                    uri="http://purl.org/dc/terms/relation",
                    defaults={"resource_type": ResourceType.PROPERTY, "name": "relation", "source": self.institution, "is_placeholder": False}
                )
        except Exception as e:
            logger.error(f"SBU Polars __init__: Failed to pre-fetch standard RDF properties: {e}", exc_info=True)
            self.has_part_prop = None 
            self.rdf_value_prop = None
            self.dcterms_relation_prop = None

    def _ensure_dataframe(self, data: Union[List[Dict[str, Any]], pl.DataFrame]) -> pl.DataFrame:
        """Convert data to Polars DataFrame if it's not already."""
        if isinstance(data, pl.DataFrame):
            return data
        else:
            return pl.DataFrame(data)

    def _normalize_unicode_vectorized(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Vectorized Unicode normalization using Polars built-in string methods.
        This is much more efficient than normalizing each cell individually in Python.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with all string columns normalized to NFC
        """
        # Get all string columns
        string_columns = [col for col in df.columns if df[col].dtype == pl.Utf8]
        
        if not string_columns:
            return df
        
        logger.debug(f"Applying vectorized Unicode NFC normalization to {len(string_columns)} string columns")
        
        # Apply NFC normalization to all string columns at once
        normalized_columns = [
            pl.col(col).str.normalize("NFC").alias(col) for col in string_columns
        ]
        
        # Keep non-string columns unchanged
        non_string_columns = [col for col in df.columns if col not in string_columns]
        all_columns = non_string_columns + normalized_columns
        
        return df.with_columns(all_columns)

    def analyze_column_for_multi_values_polars(self, df: pl.DataFrame, column_name: str) -> dict:
        """
        Simplified analysis: If CSV likely uses semicolons as delimiters, 
        then commas within cells are probably multi-value separators.
        """
        if column_name not in df.columns:
            return {"is_multi_value": False, "separator": None, "stats": {"percentage": 0.0}}
        
        # Get the column as string
        col = df.select(pl.col(column_name).cast(pl.Utf8, strict=False))
        
        # Remove null/empty values for analysis
        non_empty = col.filter(
            (pl.col(column_name).is_not_null()) & 
            (pl.col(column_name).str.strip_chars() != "")
        )
        
        total_rows = non_empty.height
        if total_rows == 0:
            return {"is_multi_value": False, "separator": None, "stats": {"percentage": 0.0}}
        
        # Simple comma analysis
        comma_stats = non_empty.with_columns([
            pl.col(column_name).str.count_matches(",").alias("comma_count"),
            (pl.col(column_name).str.count_matches(",") > 0).alias("has_commas")
        ]).select([
            pl.col("has_commas").sum().alias("rows_with_commas"),
            pl.col("comma_count").mean().alias("avg_commas_per_row")
        ]).row(0)
        
        rows_with_commas = comma_stats[0] or 0
        avg_commas = comma_stats[1] or 0
        
        percentage_with_commas = (rows_with_commas / total_rows) * 100
        
        # Simple decision logic
        is_multi_value = False
        confidence_score = 0
        
        # If enough rows have commas, likely multi-value
        if percentage_with_commas >= self.multi_value_threshold * 100:  # 20% threshold
            confidence_score = min(percentage_with_commas, 80)  # Cap at 80
            
            # If most rows have commas and average > 1 comma per row, very likely multi-value
            if percentage_with_commas >= 60 and avg_commas >= 1.0:
                confidence_score += 20
                
            # Decision threshold
            if confidence_score >= 30:  # Lower threshold for simple detection
                is_multi_value = True
        
        return {
            "is_multi_value": is_multi_value,
            "separator": "," if is_multi_value else None,
            "stats": {
                "percentage": percentage_with_commas,
                "confidence_score": confidence_score,
                "avg_commas_per_row": avg_commas,
                "total_rows": total_rows,
                "rows_with_commas": rows_with_commas
            }
        }

    def analyze_dataset_multi_values_polars(self, df: pl.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Analyze all columns in the dataset to detect multi-value patterns using Polars.
        
        Args:
            df: Polars DataFrame
            
        Returns:
            Dictionary mapping column names to their multi-value analysis
        """
        if df.height == 0:
            return {}
        
        multi_value_analysis = {}
        
        for column_name in df.columns:
            analysis = self.analyze_column_for_multi_values_polars(df, column_name)
            multi_value_analysis[column_name] = analysis
            
            if analysis["is_multi_value"]:
                stats = analysis["stats"]
                logger.info(f"Column '{column_name}': Multi-value detected ({stats['percentage']}% of {stats['rows_with_commas']} rows)")
        
        return multi_value_analysis

    def split_cell_values_polars(self, value: str, separator: str = ",") -> List[str]:
        """
        Split cell values on separator, but respect quoted fields.
        This handles CSV data where commas might be inside quotes.
        """
        if not value or not separator or separator not in value:
            return [value.strip()] if value else []
        
        # Use a simple approach that respects quotes
        import csv
        from io import StringIO
        
        try:
            # Try to parse as a CSV row to handle quotes properly
            reader = csv.reader(StringIO(value), delimiter=separator, quotechar='"')
            row = next(reader)
            return [item.strip() for item in row if item.strip()]
        except Exception:
            # Fallback to simple split if CSV parsing fails
            return [item.strip() for item in value.split(separator) if item.strip()]

    def prepare_update_data_vectorized(self, df: pl.DataFrame, dataset_name: str) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        """
        OPTIMIZED: Fully vectorized approach for preparing update data.
        This efficiently handles mixed single/multi-value scenarios.
        
        Args:
            df: Polars DataFrame with CSV data
            dataset_name: Name of the dataset
            
        Returns:
            Tuple of (list of ResourceUpdate objects, BulkUpdateStats)
        """
        if df.height == 0:
            return [], BulkUpdateStats()
        
        # STEP 1: Apply vectorized Unicode normalization
        logger.debug(f"Step 1: Applying vectorized Unicode normalization")
        df_normalized = self._normalize_unicode_vectorized(df)
        
        # STEP 2: Analyze multi-value patterns (once per column)
        logger.debug(f"Step 2: Analyzing multi-value patterns")
        multi_value_analysis = self.analyze_dataset_multi_values_polars(df_normalized)
        
        # STEP 3: Vectorized multi-value processing 
        logger.debug(f"Step 3: Applying vectorized multi-value processing")
        df_processed = self._process_multi_values_vectorized(df_normalized, multi_value_analysis)
        
        # STEP 4: Add row identifiers
        logger.debug(f"Step 4: Adding row identifiers")
        df_with_ids = df_processed.with_row_index(name='row_id')
        
        # STEP 5: More efficient conversion to updates
        logger.debug(f"Step 5: Converting to ResourceUpdate objects")
        updates = []
        stats = BulkUpdateStats()
        
        # Pre-compute column analysis for efficiency
        multi_value_columns = {
            col: analysis for col, analysis in multi_value_analysis.items() 
            if analysis.get('is_multi_value', False)
        }
        
        row_iterator = df_with_ids.iter_rows(named=True)
        
        for row_data in row_iterator:
            row_id_val = row_data.get('row_id', 'unknown')
            safe_row_id = slugify_uri_part(str(row_id_val))
            
            for column_name, value in row_data.items():
                # Skip internal columns we added
                if column_name in ['row_id'] or column_name.endswith(('_has_separator', '_split_values', '_value_count')):
                    continue
                    
                if value is not None and str(value).strip():
                    current_value_str = str(value).strip()
                    
                    # Truncation logic (could be vectorized later)
                    try:
                        original_byte_size = len(current_value_str.encode('utf-8'))
                        if original_byte_size > MAX_INDEXED_VALUE_SIZE:
                            temp_val = current_value_str
                            while len(temp_val.encode('utf-8')) > MAX_INDEXED_VALUE_SIZE:
                                temp_val = temp_val[:-1]
                            current_value_str = temp_val + "..."
                            stats.truncated_values += 1
                            logger.warning(
                                f"SBU Polars: Value truncated for dataset '{dataset_name}', column '{column_name}', row_id '{safe_row_id}'. "
                                f"Original byte size: {original_byte_size}, new byte size: {len(current_value_str.encode('utf-8'))}"
                            )
                    except UnicodeEncodeError:
                        logger.warning(f"SBU Polars: Could not encode value to check size for dataset '{dataset_name}', column '{column_name}', row_id '{safe_row_id}'.")
                    
                    # Create resource update
                    safe_column_name = slugify_uri_part(column_name)
                    cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, safe_column_name, safe_row_id)
                    
                    update = ResourceUpdate(uri=cell_uri)
                    
                    # OPTIMIZED: Check if column is multi-value (pre-computed lookup)
                    if column_name in multi_value_columns:
                        # OPTIMIZED: Use pre-computed vectorized detection
                        has_separator_key = f"{column_name}_has_separator"
                        has_separator = row_data.get(has_separator_key, False)
                        
                        if has_separator:
                            # Actually a multi-value cell - apply splitting
                            separator = multi_value_columns[column_name].get('separator', ',')
                            update.new_values = self.split_cell_values_polars(current_value_str, separator)
                            update.is_multi_value = True
                            stats.multi_value_cells_detected += 1  # Only count actual multi-value cells!
                            stats.total_values_created += len(update.new_values)
                        else:
                            # Single-value cell in multi-value column (no parsing needed!)
                            update.new_values = [current_value_str]
                            update.is_multi_value = False  # Mark as single even though column is multi-value
                            stats.total_values_created += 1
                    else:
                        # Single-value column
                        update.new_values = [current_value_str]
                        update.is_multi_value = False
                        stats.total_values_created += 1
                    
                    update.new_name = column_name
                    update.new_datatype = "http://www.w3.org/2001/XMLSchema#string"
                    
                    updates.append(update)
        
        stats.cells_processed = len(updates)
        return updates, stats

    def get_existing_resources_bulk(self, uris: List[str]) -> Dict[str, Resource]:
        """
        Efficiently fetch existing resources for a list of URIs.
        Same as original implementation.
        """
        existing = Resource.objects.filter(uri__in=uris).select_related()
        return {resource.uri: resource for resource in existing}

    def determine_update_actions_polars(self, 
                                      df: pl.DataFrame, 
                                      dataset_name: str) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        """
        Determine update actions using Polars DataFrame operations.
        
        Args:
            df: Polars DataFrame with CSV data
            dataset_name: Name of the dataset
            
        Returns:
            Tuple of (list of ResourceUpdate objects, BulkUpdateStats)
        """
        # Prepare the basic update data
        updates, action_stats = self.prepare_update_data_vectorized(df, dataset_name)
        
        if not updates:
            return updates, action_stats
        
        # Get all URIs and check for existing resources
        all_uris = [update.uri for update in updates]
        existing_resources = self.get_existing_resources_bulk(all_uris)
        
        # Process each update to determine the action
        for update in updates:
            if update.uri in existing_resources:
                existing = existing_resources[update.uri]
                update.existing_resource = existing
                
                # Determine update strategy
                if self.default_strategy == UpdateStrategy.SKIP_EXISTING:
                    update.action = UpdateStrategy.SKIP_EXISTING
                elif self.default_strategy == UpdateStrategy.UPDATE_VALUES:
                    # For multi-value fields, we need to compare differently
                    if update.is_multi_value:
                        # For now, always update multi-value fields (complex comparison)
                        update.action = UpdateStrategy.UPDATE_VALUES
                    else:
                        if existing.value != update.new_values[0]:
                            update.action = UpdateStrategy.UPDATE_VALUES
                        else:
                            update.action = UpdateStrategy.SKIP_EXISTING
                elif self.default_strategy == UpdateStrategy.TIMESTAMP_BASED:
                    # This would need the row data for timestamp comparison
                    # For now, default to UPDATE_VALUES
                    update.action = UpdateStrategy.UPDATE_VALUES
                else:
                    update.action = self.default_strategy
            else:
                # New resource
                update.action = UpdateStrategy.UPDATE_VALUES  # Create new
        
        return updates, action_stats

    def execute_bulk_update(self, 
                          updates: List[ResourceUpdate],
                          dataset_name: str, 
                          action_phase_stats: BulkUpdateStats,
                          batch_size: int = 1000) -> BulkUpdateStats:
        """
        Execute bulk updates. This reuses the logic from the original implementation
        since the database operations don't benefit significantly from Polars optimization.
        """
        from arkumu.importer.services.importer.smart_bulk_updater import SmartBulkUpdater
        
        # Create a temporary instance of the original updater to reuse the execution logic
        temp_updater = SmartBulkUpdater(
            default_strategy=self.default_strategy,
            timestamp_column=self.timestamp_column,
            institution=self.institution,
            base_uri=self.base_uri,
            link_row_cells=self.link_row_cells,
            link_topology=self.link_topology,
            multi_value_threshold=self.multi_value_threshold
        )
        
        # Copy the properties
        temp_updater.has_part_prop = self.has_part_prop
        temp_updater.rdf_value_prop = self.rdf_value_prop
        temp_updater.dcterms_relation_prop = self.dcterms_relation_prop
        
        return temp_updater.execute_bulk_update(updates, dataset_name, action_phase_stats, batch_size)

    def import_csv_with_smart_updates(self,
                                    csv_data: Union[List[Dict[str, Any]], pl.DataFrame],
                                    dataset_name: str,
                                    strategy: Optional[UpdateStrategy] = None) -> BulkUpdateStats:
        """
        Import CSV data with intelligent update handling using Polars optimization.
        
        Args:
            csv_data: List of row dictionaries from CSV or Polars DataFrame
            dataset_name: Name of the dataset
            strategy: Override the default update strategy
            
        Returns:
            BulkUpdateStats with operation results
        """
        if strategy:
            original_strategy = self.default_strategy
            self.default_strategy = strategy
        
        overall_stats = BulkUpdateStats()
        try:
            logger.info(f"Starting Polars-optimized smart bulk import for dataset: {dataset_name} with linking: {self.link_row_cells}, topology: {self.link_topology}")
            
            # Convert to DataFrame if needed
            df = self._ensure_dataframe(csv_data)
            
            if df.height == 0:
                logger.warning(f"Empty dataset provided for {dataset_name}")
                return overall_stats
            
            # Use Polars-optimized processing
            updates, action_stats = self.determine_update_actions_polars(df, dataset_name)
            overall_stats.merge(action_stats)
            logger.info(f"Determined {len(updates)} update actions. Truncated values: {action_stats.truncated_values}")
            
            execution_stats = self.execute_bulk_update(updates, dataset_name, action_stats, batch_size=1000)
            overall_stats.merge(execution_stats)
            
            logger.info(f"Polars-optimized smart bulk import completed: {overall_stats}")
            return overall_stats
            
        finally:
            if strategy:
                self.default_strategy = original_strategy

    # Compatibility methods that delegate to Polars versions
    def analyze_column_for_multi_values(self, column_values: List[str]) -> Dict[str, Any]:
        """Compatibility method that converts to DataFrame and uses Polars analysis."""
        if not column_values:
            return {"is_multi_value": False, "separator": None, "stats": {}}
        
        # Create a temporary DataFrame with just this column
        df = pl.DataFrame({"temp_column": column_values})
        return self.analyze_column_for_multi_values_polars(df, "temp_column")

    def analyze_dataset_multi_values(self, csv_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Compatibility method that converts to DataFrame and uses Polars analysis."""
        df = self._ensure_dataframe(csv_data)
        return self.analyze_dataset_multi_values_polars(df)

    def split_cell_values(self, value: str, separator: str = ",") -> List[str]:
        """Compatibility method that uses the same splitting logic."""
        return self.split_cell_values_polars(value, separator)

    def _process_multi_values_vectorized(self, df: pl.DataFrame, multi_value_analysis: Dict[str, Dict[str, Any]]) -> pl.DataFrame:
        """
        Vectorized processing of multi-value columns using Polars operations.
        This efficiently detects which cells actually contain separators.
        
        Args:
            df: Input DataFrame with normalized Unicode
            multi_value_analysis: Analysis results per column
            
        Returns:
            DataFrame with additional columns for multi-value detection flags
        """
        result_df = df
        
        for column_name, analysis in multi_value_analysis.items():
            if not analysis.get('is_multi_value', False) or column_name not in df.columns:
                continue
                
            separator = analysis.get('separator', ',')
            
            logger.debug(f"Vectorizing multi-value detection for column '{column_name}' with separator '{separator}'")
            
            # Add vectorized column for efficient multi-value detection
            result_df = result_df.with_columns([
                # Detect which cells actually contain the separator
                pl.col(column_name).str.contains(f"\\{separator}").fill_null(False).alias(f"{column_name}_has_separator")
            ])
        
        return result_df

    def prepare_update_data_polars(self, df: pl.DataFrame, dataset_name: str) -> Tuple[List[ResourceUpdate], BulkUpdateStats]:
        """
        Legacy method for backward compatibility. 
        Delegates to the optimized vectorized version.
        """
        return self.prepare_update_data_vectorized(df, dataset_name)

    def analyze_dataset_changes(self, 
                              dataset_name: str,
                              csv_data: Union[List[Dict[str, Any]], pl.DataFrame]) -> Dict[str, Any]:
        """
        Analyze what would change if we imported this CSV data.
        This is a dry-run analysis without making any changes.
        Polars-optimized version.
        
        Args:
            dataset_name: Name of the dataset
            csv_data: List of row dictionaries from CSV or Polars DataFrame
            
        Returns:
            Analysis report with statistics and recommendations
        """
        # Ensure we have a DataFrame
        df = self._ensure_dataframe(csv_data)
        
        analysis = {
            "total_rows": df.height,
            "new_resources": 0,
            "existing_resources": 0,
            "potential_updates": 0,
            "conflicts": [],
            "recommendations": []
        }
        
        # Get all existing resources for this dataset
        dataset_uri_pattern = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, "", "")
        dataset_uri_prefix = dataset_uri_pattern.rsplit('/', 2)[0]  # Remove the last two empty parts
        
        existing_resources = Resource.objects.filter(
            uri__startswith=dataset_uri_prefix
        ).values('uri', 'value', 'name', 'updated_at')
        
        existing_uri_map = {res['uri']: res for res in existing_resources}
        
        # Add row indices for processing
        df_with_ids = df.with_row_index(name='row_id')
        
        # Analyze each row using Polars iteration
        for row_data in df_with_ids.iter_rows(named=True):
            row_num = row_data.get('row_id', 0)
            row_id_val = row_data.get('id', row_data.get('ID', str(row_num)))
            
            for column_name, value in row_data.items():
                # Skip internal columns
                if column_name == 'row_id':
                    continue
                    
                if value and str(value).strip():
                    # Ensure row_id is slugified for URI consistency
                    safe_row_id = slugify_uri_part(str(row_id_val))
                    safe_column_name = slugify_uri_part(column_name)
                    cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, safe_column_name, safe_row_id)
                    
                    if cell_uri in existing_uri_map:
                        existing = existing_uri_map[cell_uri]
                        analysis["existing_resources"] += 1
                        
                        # Check if value would change
                        if existing['value'] != str(value).strip():
                            analysis["potential_updates"] += 1
                            
                            conflict_info = {
                                "uri": cell_uri,
                                "column": column_name,
                                "row_id": row_id_val,
                                "existing_value": existing['value'],
                                "new_value": str(value).strip(),
                                "last_updated": existing.get('updated_at')
                            }
                            
                            # Add timestamp comparison if timestamp column is configured
                            if self.timestamp_column and self.timestamp_column in row_data:
                                new_timestamp_str = str(row_data.get(self.timestamp_column, '')).strip()
                                new_timestamp = self._parse_timestamp(new_timestamp_str)
                                
                                if new_timestamp:
                                    # Try to get existing timestamp for this row
                                    existing_timestamp = self._get_existing_timestamp_for_analysis(
                                        dataset_name, safe_row_id, existing.get('updated_at')
                                    )
                                    
                                    conflict_info.update({
                                        "new_timestamp": new_timestamp_str,
                                        "new_timestamp_parsed": new_timestamp.isoformat() if new_timestamp else None,
                                        "existing_timestamp": existing_timestamp.isoformat() if existing_timestamp else None,
                                        "timestamp_comparison": (
                                            "newer" if existing_timestamp and new_timestamp > existing_timestamp else
                                            "older" if existing_timestamp and new_timestamp < existing_timestamp else
                                            "equal" if existing_timestamp and new_timestamp == existing_timestamp else
                                            "unknown"
                                        )
                                    })
                            
                            analysis["conflicts"].append(conflict_info)
                    else:
                        analysis["new_resources"] += 1
        
        # Generate recommendations
        if analysis["potential_updates"] > 0:
            analysis["recommendations"].append(
                f"Found {analysis['potential_updates']} potential updates. "
                f"Consider using UPDATE_VALUES strategy."
            )
        
        if analysis["existing_resources"] > analysis["new_resources"]:
            analysis["recommendations"].append(
                "Mostly existing data detected. Consider SKIP_EXISTING for faster processing."
            )
        
        return analysis

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """
        Parse a timestamp string into a datetime object.
        """
        if not timestamp_str or not timestamp_str.strip():
            return None
            
        timestamp_str = timestamp_str.strip()
        
        try:
            # Try common ISO formats first
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%d",
                "%d.%m.%Y",
                "%d/%m/%Y",
                "%m/%d/%Y"
            ]:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    # Add timezone info if missing
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

    def _get_existing_timestamp_for_analysis(self, dataset_name: str, row_id: str, fallback_updated_at) -> Optional[datetime]:
        """
        Get existing timestamp for analysis purposes.
        """
        if not self.timestamp_column:
            return fallback_updated_at
            
        # Try to find the timestamp cell for this row
        safe_column_name = slugify_uri_part(self.timestamp_column)
        timestamp_cell_uri = mint_uri(self.base_uri, self.institution, "datasets", dataset_name, safe_column_name, row_id)
        
        try:
            timestamp_resource = Resource.objects.get(uri=timestamp_cell_uri)
            if timestamp_resource.value:
                return self._parse_timestamp(timestamp_resource.value)
        except Resource.DoesNotExist:
            pass
            
        return fallback_updated_at 