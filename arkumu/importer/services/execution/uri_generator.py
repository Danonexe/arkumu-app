"""
Unified URI generation for entity-based processing.
"""

import hashlib
import logging
from typing import Dict, List, Optional

import polars as pl

from arkumu.common.uri_utils import mint_uri, slugify_uri_part

logger = logging.getLogger(__name__)


class UnifiedURIGenerator:
    """Unified URI generation for entity-based processing."""
    
    def __init__(self, base_uri: str, institution: str):
        """
        Initialize the URI generator.
        
        Args:
            base_uri: Base URI for resource generation
            institution: Institution code for URI generation
        """
        self.base_uri = base_uri
        self.institution = slugify_uri_part(str(institution)) if institution else "default"
    
    def resolve_anchor_columns(self, dataset_config: Optional[Dict], csv_headers: List[str]) -> List[str]:
        """
        Determine anchor columns for entity URI generation.
        
        Priority order:
        1. Use explicitly marked anchor columns if any exist
        2. Otherwise use first column as default anchor
        3. Never use system columns (row_id, _id, etc.)
        
        Args:
            dataset_config: Optional mapping configuration with column settings
            csv_headers: List of column names from the CSV
            
        Returns:
            List of column names to use as anchors for entity URI generation
        """
        logger.debug(f"Resolving anchor columns for dataset with headers: {csv_headers}")
        
        # System columns to exclude from being anchors
        system_columns = {"row_id", "_id", "id", "index"}
        
        # Filter out system columns from consideration
        eligible_columns = [col for col in csv_headers if col.lower() not in system_columns]
        
        if not eligible_columns:
            logger.warning("No eligible columns found for anchor generation, falling back to row numbers")
            return []
        
        # Check for explicitly marked anchor columns
        if dataset_config and "columns" in dataset_config:
            explicit_anchors = []
            for col_name, col_config in dataset_config["columns"].items():
                if col_config.get("is_anchor", False) and col_name in eligible_columns:
                    explicit_anchors.append(col_name)
            
            if explicit_anchors:
                logger.debug(f"Found explicit anchor columns: {explicit_anchors}")
                return explicit_anchors
        
        # Alternative: check for anchor_columns list in config (from plan specs)
        if dataset_config and "anchor_columns" in dataset_config:
            anchor_columns = dataset_config["anchor_columns"]
            valid_anchors = [col for col in anchor_columns if col in eligible_columns]
            if valid_anchors:
                logger.debug(f"Found configured anchor columns: {valid_anchors}")
                return valid_anchors
        
        # Default: use first eligible column
        default_anchor = eligible_columns[0]
        logger.debug(f"Using default anchor column: {default_anchor}")
        return [default_anchor]
    
    def generate_entity_uri(self, dataset_name: str, row_data: Dict, anchor_columns: List[str]) -> str:
        """
        Generate stable entity URI using anchor columns.
        
        Args:
            dataset_name: Name of the dataset
            row_data: Dictionary containing row data
            anchor_columns: List of column names to use as anchors
            
        Returns:
            Generated entity URI
        """
        if not anchor_columns:
            # Fallback to row_id if available, or generate from row hash
            row_id = row_data.get("row_id")
            if row_id is not None:
                entity_id = f"row_{row_id}"
            else:
                # Generate hash-based ID from all available data
                data_str = "_".join(str(v) for v in row_data.values() if v is not None)
                entity_id = f"entity_{hashlib.md5(data_str.encode()).hexdigest()[:8]}"
        else:
            # Generate entity ID from anchor column values
            anchor_values = []
            for col in anchor_columns:
                value = row_data.get(col)
                if value is not None and str(value).strip():
                    anchor_values.append(str(value).strip())
            
            if not anchor_values:
                # Fallback if anchor columns are empty
                row_id = row_data.get("row_id", 0)
                entity_id = f"row_{row_id}"
            else:
                # Create composite ID from anchor values
                if len(anchor_values) == 1:
                    entity_id = slugify_uri_part(anchor_values[0])
                else:
                    # Use hash for multiple anchor values to keep URIs manageable
                    composite_value = "_".join(anchor_values)
                    hash_suffix = hashlib.md5(composite_value.encode()).hexdigest()[:8]
                    entity_id = f"composite_{hash_suffix}"
        
        safe_dataset_name = slugify_uri_part(dataset_name)
        safe_entity_id = slugify_uri_part(entity_id)
        
        return mint_uri(self.base_uri, self.institution, "entities", safe_dataset_name, safe_entity_id)
    
    def generate_entity_uris_bulk(self, df: pl.DataFrame, dataset_name: str, anchor_columns: List[str]) -> pl.Series:
        """
        Vectorized entity URI generation for bulk processing.
        
        Args:
            df: Polars DataFrame with row data
            dataset_name: Name of the dataset
            anchor_columns: List of column names to use as anchors
            
        Returns:
            Polars Series with generated entity URIs
        """
        logger.debug(f"Generating bulk entity URIs for {df.height} rows with anchors: {anchor_columns}")
        
        try:
            if not anchor_columns:
                # Fallback to row_id or row numbers
                if "row_id" in df.columns:
                    entity_ids = df.select(
                        pl.concat_str([
                            pl.lit("row_"),
                            pl.col("row_id").cast(pl.Utf8)
                        ]).alias("entity_id")
                    )["entity_id"]
                else:
                    # Use row numbers as fallback
                    entity_ids = pl.Series("entity_id", [f"row_{i}" for i in range(df.height)])
            else:
                if len(anchor_columns) == 1:
                    # Single anchor column - use value directly (with slug conversion)
                    col = anchor_columns[0]
                    if col in df.columns:
                        # Handle None/null values by converting to row numbers
                        entity_ids = df.select(
                            pl.when(pl.col(col).is_null() | (pl.col(col).cast(pl.Utf8).str.len_chars() == 0))
                            .then(pl.concat_str([pl.lit("row_"), pl.int_range(pl.len()).cast(pl.Utf8)]))
                            .otherwise(pl.col(col).cast(pl.Utf8))
                            .alias("entity_id")
                        )["entity_id"]
                    else:
                        logger.warning(f"Anchor column '{col}' not found in DataFrame, using row numbers")
                        entity_ids = pl.Series("entity_id", [f"row_{i}" for i in range(df.height)])
                else:
                    # Multiple anchor columns - create composite hash
                    available_anchors = [col for col in anchor_columns if col in df.columns]
                    
                    if not available_anchors:
                        logger.warning("No anchor columns found in DataFrame, using row numbers")
                        entity_ids = pl.Series("entity_id", [f"row_{i}" for i in range(df.height)])
                    else:
                        # Create composite string and hash
                        composite_expr = pl.concat_str([
                            pl.col(col).cast(pl.Utf8).fill_null("") for col in available_anchors
                        ], separator="_")
                        
                        # Convert to Python to calculate hash (polars doesn't have md5)
                        composite_values = df.select(composite_expr.alias("composite"))["composite"].to_list()
                        hashed_ids = [
                            f"composite_{hashlib.md5(val.encode()).hexdigest()[:8]}" 
                            for val in composite_values
                        ]
                        entity_ids = pl.Series("entity_id", hashed_ids)
            
            # Generate full URIs
            safe_dataset_name = slugify_uri_part(dataset_name)
            base_path = f"{self.base_uri}/{self.institution}/entities/{safe_dataset_name}"
            
            # Apply slugify to entity IDs and build full URIs
            entity_ids_slugified = entity_ids.map_elements(
                lambda x: slugify_uri_part(str(x)), 
                return_dtype=pl.Utf8
            )
            
            uris = entity_ids_slugified.map_elements(
                lambda x: f"{base_path}/{x}",
                return_dtype=pl.Utf8
            )
            
            logger.debug(f"Generated {len(uris)} entity URIs")
            return uris
            
        except Exception as e:
            logger.error(f"Error in bulk URI generation: {e}", exc_info=True)
            # Fallback to row-based URIs
            fallback_uris = pl.Series("uri", [
                f"{self.base_uri}/{self.institution}/entities/{slugify_uri_part(dataset_name)}/row_{i}"
                for i in range(df.height)
            ])
            return fallback_uris