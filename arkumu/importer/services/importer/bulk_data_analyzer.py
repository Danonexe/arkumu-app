import logging
import polars as pl
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timezone
import dateutil.parser

logger = logging.getLogger(__name__)

# Maximum size for values to avoid btree index errors (PostgreSQL limit is ~2704 bytes)
MAX_INDEXED_VALUE_SIZE = 1000


class BulkDataAnalyzer:
    """
    Handles data analysis and preparation for bulk import operations.
    
    Responsibilities:
    - Multi-value column detection and analysis
    - Dataset change analysis (dry-run functionality)
    - Data validation and normalization
    - Statistics generation for import decisions
    """
    
    def __init__(self, multi_value_threshold: float = 0.2):
        """
        Initialize the data analyzer.
        
        Args:
            multi_value_threshold: Threshold for detecting multi-value columns (0.2 = 20%)
        """
        self.multi_value_threshold = multi_value_threshold
    
    def normalize_unicode_vectorized(self, df: pl.DataFrame) -> pl.DataFrame:
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

    def analyze_column_for_multi_values(self, df: pl.DataFrame, column_name: str, 
                                      force_multi_value: bool = False, 
                                      separator: str = ",") -> dict:
        """
        Analyze a column for multi-value content using Polars vectorized operations.
        
        Args:
            df: Polars DataFrame
            column_name: Column to analyze
            force_multi_value: Force multi-value processing regardless of detection
            separator: Separator to check for (default: comma)
        """
        if column_name not in df.columns:
            return {"is_multi_value": False, "separator": None, "stats": {"percentage": 0.0}}
        
        # If forced, return multi-value immediately
        if force_multi_value:
            return {
                "is_multi_value": True,
                "separator": separator,
                "stats": {
                    "percentage": 100.0,
                    "confidence_score": 1.0,
                    "forced": True,
                    "total_rows": df.height
                }
            }
        
        # Get column data and filter out nulls
        column_data = df.select(pl.col(column_name).cast(pl.Utf8)).drop_nulls()
        
        if column_data.height == 0:
            return {"is_multi_value": False, "separator": None, "stats": {"percentage": 0.0}}
        
        # Use Polars to count rows containing the separator
        rows_with_separator = column_data.filter(
            pl.col(column_name).str.contains(f"\\{separator}", literal=False)
        ).height
        
        # Calculate statistics
        total_rows = column_data.height
        percentage = (rows_with_separator / total_rows) * 100 if total_rows > 0 else 0
        
        # Calculate average separators per row for confidence
        separator_counts = column_data.select(
            pl.col(column_name).str.count_matches(f"\\{separator}", literal=False).alias("count")
        )
        avg_separators = separator_counts.select(pl.col("count").mean()).item()
        
        # Determine if this is multi-value based on threshold
        is_multi_value = percentage >= (self.multi_value_threshold * 100)
        confidence_score = min(percentage / 100, 1.0) if is_multi_value else 0.0
        
        return {
            "is_multi_value": is_multi_value,
            "separator": separator if is_multi_value else None,
            "stats": {
                "percentage": percentage,
                "confidence_score": confidence_score,
                "avg_separators_per_row": avg_separators,
                "total_rows": total_rows,
                "rows_with_separators": rows_with_separator
            }
        }

    def analyze_dataset_multi_values(self, df: pl.DataFrame, 
                                   column_configs: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Analyze dataset for multi-value columns using Polars vectorized operations.
        
        Args:
            df: Polars DataFrame to analyze
            column_configs: Optional column configurations from mapping system
                          Format: {column_name: {"is_multi_value": bool, "separator": str}}
        """
        if df.height == 0:
            return {}
        
        multi_value_analysis = {}
        
        for column_name in df.columns:
            # Check if we have mapping configuration for this column
            if column_configs and column_name in column_configs:
                config = column_configs[column_name]
                force_multi_value = config.get("is_multi_value", False)
                separator = config.get("multi_value_separator", ",")
                
                analysis = self.analyze_column_for_multi_values(
                    df, column_name, force_multi_value=force_multi_value, separator=separator
                )
            else:
                # Auto-detect multi-value patterns
                analysis = self.analyze_column_for_multi_values(df, column_name)
            
            multi_value_analysis[column_name] = analysis
        
        # Log analysis results
        multi_value_columns = [col for col, analysis in multi_value_analysis.items() if analysis["is_multi_value"]]
        if multi_value_columns:
            logger.info(f"Multi-value analysis: {len(multi_value_columns)} columns detected as multi-value: {multi_value_columns}")
        else:
            logger.info(f"Multi-value analysis: all {len(df.columns)} columns treated as single-value")
        
        return multi_value_analysis

    def split_cell_values(self, value: str, separator: str = ",") -> List[str]:
        """
        Split cell values using the specified separator with proper cleaning.
        
        Args:
            value: String value to split
            separator: Separator to use for splitting
            
        Returns:
            List of cleaned values
        """
        if not value or not value.strip():
            return []
        
        if not separator:
            return [value.strip()]
        
        # Split and clean values
        values = [v.strip() for v in value.split(separator) if v.strip()]
        return values

    def analyze_dataset_changes(self, dataset_name: str, df: pl.DataFrame, 
                              base_uri: str, institution: str,
                              timestamp_column: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze what would change if we imported this dataset.
        This is a dry-run analysis without making any changes.
        
        Args:
            dataset_name: Name of the dataset
            df: Polars DataFrame to analyze
            base_uri: Base URI for resource generation
            institution: Institution code
            timestamp_column: Optional timestamp column for temporal analysis
            
        Returns:
            Analysis report with statistics and recommendations
        """
        from arkumu.metadata.models import Resource
        from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
        
        analysis = {
            "total_rows": df.height,
            "new_resources": 0,
            "existing_resources": 0,
            "potential_updates": 0,
            "conflicts": [],
            "recommendations": []
        }
        
        # Get all existing resources for this dataset
        dataset_uri_pattern = mint_uri(base_uri, institution, "datasets", dataset_name, "", "")
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
                # Skip internal columns and None column names
                if column_name == 'row_id' or column_name is None:
                    continue
                    
                if value and str(value).strip():
                    # Ensure row_id is slugified for URI consistency
                    safe_row_id = slugify_uri_part(str(row_id_val))
                    safe_column_name = slugify_uri_part(column_name)
                    cell_uri = mint_uri(base_uri, institution, "datasets", dataset_name, safe_column_name, safe_row_id)
                    
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
                            if timestamp_column and timestamp_column in row_data:
                                new_timestamp_str = str(row_data.get(timestamp_column, '')).strip()
                                new_timestamp = self._parse_timestamp(new_timestamp_str)
                                
                                if new_timestamp:
                                    # Try to get existing timestamp for this row
                                    existing_timestamp = self._get_existing_timestamp_for_analysis(
                                        dataset_name, safe_row_id, existing.get('updated_at'),
                                        base_uri, institution, timestamp_column
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

    def _get_existing_timestamp_for_analysis(self, dataset_name: str, row_id: str, 
                                           fallback_updated_at, base_uri: str, 
                                           institution: str, timestamp_column: str) -> Optional[datetime]:
        """
        Get existing timestamp for analysis purposes.
        """
        from arkumu.metadata.models import Resource
        from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
        
        if not timestamp_column:
            return fallback_updated_at
            
        # Try to find the timestamp cell for this row
        safe_column_name = slugify_uri_part(timestamp_column)
        timestamp_cell_uri = mint_uri(base_uri, institution, "datasets", dataset_name, safe_column_name, row_id)
        
        try:
            timestamp_resource = Resource.objects.get(uri=timestamp_cell_uri)
            if timestamp_resource.value:
                return self._parse_timestamp(timestamp_resource.value)
        except Resource.DoesNotExist:
            pass
            
        return fallback_updated_at

    def validate_data_quality(self, df: pl.DataFrame) -> Dict[str, Any]:
        """
        Validate data quality and identify potential issues.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Quality report with metrics and recommendations
        """
        report = {
            "total_rows": df.height,
            "total_columns": len(df.columns),
            "empty_rows": 0,
            "empty_columns": [],
            "columns_with_nulls": {},
            "potential_issues": [],
            "quality_score": 0.0
        }
        
        if df.height == 0:
            report["quality_score"] = 0.0
            report["potential_issues"].append("Dataset is empty")
            return report
        
        # Check for empty rows (all null values)
        null_counts_per_row = df.select([
            pl.sum_horizontal([pl.col(col).is_null().cast(pl.Int32) for col in df.columns]).alias("null_count")
        ])
        
        empty_rows = null_counts_per_row.filter(pl.col("null_count") == len(df.columns)).height
        report["empty_rows"] = empty_rows
        
        # Check for columns with high null rates
        for column in df.columns:
            null_count = df.select(pl.col(column).is_null().sum()).item()
            null_percentage = (null_count / df.height) * 100
            
            if null_count > 0:
                report["columns_with_nulls"][column] = {
                    "null_count": null_count,
                    "null_percentage": round(null_percentage, 2)
                }
            
            # Flag columns with very high null rates
            if null_percentage > 90:
                report["empty_columns"].append(column)
                report["potential_issues"].append(f"Column '{column}' is {null_percentage:.1f}% empty")
        
        # Calculate overall quality score
        non_empty_cells = df.height * len(df.columns) - sum(
            stats["null_count"] for stats in report["columns_with_nulls"].values()
        )
        total_cells = df.height * len(df.columns)
        
        if total_cells > 0:
            report["quality_score"] = round((non_empty_cells / total_cells) * 100, 2)
        
        # Add recommendations based on quality
        if report["quality_score"] < 50:
            report["potential_issues"].append("Low data quality detected - consider data cleaning")
        
        if len(report["empty_columns"]) > len(df.columns) * 0.3:
            report["potential_issues"].append("Many columns are mostly empty - consider removing them")
        
        return report