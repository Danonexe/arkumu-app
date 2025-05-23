import csv
import logging
import re
from typing import List, Dict, Any, Optional
import os

from django.db import transaction, IntegrityError, DataError
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)

# Maximum size for values to avoid btree index errors (PostgreSQL limit is 2704)
MAX_INDEXED_VALUE_SIZE = 2500

# Regular expression to detect btree index size errors
BTREE_SIZE_ERROR_PATTERN = re.compile(r"index row size \d+ exceeds btree .* maximum \d+ for index")

def brute_force_import_csv(
    csv_file_path: str,
    dataset_name: str,
    institution: str = "DEFAULT",
    base_uri: str = "http://arkumu.org/data",
    delimiter: str = ';',
    has_quoted_fields: bool = False,
    batch_size: int = 1000,
    max_value_size: int = MAX_INDEXED_VALUE_SIZE
) -> Dict[str, Any]:
    """
    Import a CSV file using a brute force approach that creates:
    1. One resource for the dataset
    2. One resource for each cell
    3. One literal resource for each cell value
    4. Triples connecting them
    
    Args:
        csv_file_path: Path to the CSV file
        dataset_name: Name for the dataset (used in URI)
        institution: Institution code
        base_uri: Base URI for generated resources
        delimiter: CSV column delimiter
        has_quoted_fields: Whether fields in the CSV are quoted
        batch_size: Number of objects to create in each database transaction
        max_value_size: Maximum size for indexed values to prevent btree index errors
        
    Returns:
        Dict with import statistics
    """
    stats = {
        "rows_processed": 0,
        "cells_processed": 0,
        "resources_created": 0,
        "triples_created": 0,
        "errors": 0,
        "truncated_values": 0
    }
    
    # Keep track of truncated values for logging
    truncated_values_log = []
    
    try:
        # Create or get common resources
        dataset_uri = f"{base_uri}/datasets/{dataset_name}"
        
        with transaction.atomic():
            # Create the main dataset resource
            dataset = Resource.objects.create(
                uri=dataset_uri,
                resource_type=ResourceType.IRI,
                source=institution,
                name=dataset_name
            )
            stats["resources_created"] += 1
            
            # Get or create common properties
            has_part = Resource.objects.get_or_create(
                uri="http://purl.org/dc/terms/hasPart",
                resource_type=ResourceType.PROPERTY,
                name="hasPart",
                source=institution
            )[0]
            if has_part.pk is None:
                stats["resources_created"] += 1
                
            rdf_value = Resource.objects.get_or_create(
                uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
                resource_type=ResourceType.PROPERTY,
                name="value",
                source=institution
            )[0]
            if rdf_value.pk is None:
                stats["resources_created"] += 1
                
            rdf_type = Resource.objects.get_or_create(
                uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                resource_type=ResourceType.PROPERTY,
                name="type",
                source=institution
            )[0]
            if rdf_type.pk is None:
                stats["resources_created"] += 1
                
            # Create a class for cells
            cell_class = Resource.objects.get_or_create(
                uri=f"{base_uri}/classes/Cell",
                resource_type=ResourceType.CLASS,
                name="Cell",
                source=institution
            )[0]
            if cell_class.pk is None:
                stats["resources_created"] += 1
        
        # Process the CSV file
        with open(csv_file_path, newline='', encoding='utf-8') as f:
            quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
            reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
            
            # Process in batches
            batch_resources = []
            batch_triples = []
            
            for row_num, row in enumerate(reader):
                stats["rows_processed"] += 1
                row_id = row.get('id', row.get('ID', str(row_num)))
                
                for column_name, value in row.items():
                    if value and value.strip():  # Skip empty values
                        stats["cells_processed"] += 1
                        value = value.strip()
                        
                        try:
                            with transaction.atomic():
                                # Create a unique resource for each cell
                                cell_resource = Resource.objects.create(
                                    uri=f"{dataset_uri}/{column_name}/{row_id}",
                                    resource_type=ResourceType.IRI,
                                    source=institution,
                                    name=column_name
                                )
                                stats["resources_created"] += 1
                                
                                # Link cell to dataset
                                Triple.objects.create(
                                    subject=dataset,
                                    predicate=has_part,
                                    object=cell_resource
                                )
                                stats["triples_created"] += 1
                                
                                # Set cell type
                                Triple.objects.create(
                                    subject=cell_resource,
                                    predicate=rdf_type,
                                    object=cell_class
                                )
                                stats["triples_created"] += 1
                                
                                # Check if value exceeds the maximum size for indexing
                                original_value = value
                                original_byte_size = len(value.encode('utf-8'))
                                
                                if original_byte_size > max_value_size:
                                    # Truncate the value to avoid btree index errors
                                    # We need to truncate by bytes, not characters
                                    while len(value.encode('utf-8')) > max_value_size:
                                        value = value[:-1]
                                    
                                    truncated_byte_size = len(value.encode('utf-8'))
                                    value += "..."  # Add ellipsis to indicate truncation
                                    stats["truncated_values"] += 1
                                    
                                    # Log detailed information about truncation
                                    truncation_info = {
                                        "table": dataset_name,
                                        "column": column_name,
                                        "row_id": row_id,
                                        "original_length_chars": len(original_value),
                                        "truncated_length_chars": len(value),
                                        "original_size_bytes": original_byte_size,
                                        "truncated_size_bytes": truncated_byte_size,
                                        "truncation_percentage": round((1 - truncated_byte_size/original_byte_size) * 100, 2)
                                    }
                                    
                                    truncated_values_log.append(truncation_info)
                                    
                                    logger.warning(
                                        f"Value truncated: {dataset_name}.{column_name}[{row_id}] - "
                                        f"Original: {len(original_value)} chars ({original_byte_size} bytes), "
                                        f"Truncated: {len(value)} chars ({truncated_byte_size} bytes), "
                                        f"Reduced by: {truncation_info['truncation_percentage']}%"
                                    )
                                
                                # Create literal for the value
                                value_resource = Resource.objects.create(
                                    resource_type=ResourceType.LITERAL,
                                    source=institution,
                                    name=column_name,
                                    value=value,
                                    datatype="http://www.w3.org/2001/XMLSchema#string"
                                )
                                stats["resources_created"] += 1
                                
                                # Link cell to its value
                                Triple.objects.create(
                                    subject=cell_resource,
                                    predicate=rdf_value,
                                    object=value_resource
                                )
                                stats["triples_created"] += 1
                                
                        except (IntegrityError, DataError) as e:
                            error_str = str(e)
                            # Check if this is a btree index size error
                            if BTREE_SIZE_ERROR_PATTERN.search(error_str):
                                logger.warning(f"Btree index size error for {column_name} in row {row_id}. Error: {error_str}")
                                logger.warning(f"Retrying with more aggressive truncation for {dataset_name}.{column_name}[{row_id}]")
                                
                                try:
                                    # Try again with a more aggressively truncated value
                                    with transaction.atomic():
                                        # Create cell resource
                                        cell_resource = Resource.objects.create(
                                            uri=f"{dataset_uri}/{column_name}/{row_id}",
                                            resource_type=ResourceType.IRI,
                                            source=institution,
                                            name=column_name
                                        )
                                        stats["resources_created"] += 1
                                        
                                        # Link cell to dataset
                                        Triple.objects.create(
                                            subject=dataset,
                                            predicate=has_part,
                                            object=cell_resource
                                        )
                                        stats["triples_created"] += 1
                                        
                                        # Set cell type
                                        Triple.objects.create(
                                            subject=cell_resource,
                                            predicate=rdf_type,
                                            object=cell_class
                                        )
                                        stats["triples_created"] += 1
                                        
                                        # Truncate value more aggressively
                                        original_byte_size = len(value.encode('utf-8'))
                                        truncated_value = value[:max_value_size // 4].encode('utf-8')[:max_value_size // 2].decode('utf-8', errors='ignore')
                                        truncated_byte_size = len(truncated_value.encode('utf-8'))
                                        truncated_value += f"... (truncated from {len(value)} chars, {original_byte_size} bytes)"
                                        
                                        # Create literal for the truncated value
                                        value_resource = Resource.objects.create(
                                            resource_type=ResourceType.LITERAL,
                                            source=institution,
                                            name=column_name,
                                            value=truncated_value,
                                            datatype="http://www.w3.org/2001/XMLSchema#string"
                                        )
                                        stats["resources_created"] += 1
                                        stats["truncated_values"] += 1
                                        
                                        # Link cell to its value
                                        Triple.objects.create(
                                            subject=cell_resource,
                                            predicate=rdf_value,
                                            object=value_resource
                                        )
                                        stats["triples_created"] += 1
                                        
                                        # Add to truncation log with special flag for aggressive truncation
                                        truncation_info = {
                                            "table": dataset_name,
                                            "column": column_name,
                                            "row_id": row_id,
                                            "original_length_chars": len(value),
                                            "truncated_length_chars": len(truncated_value),
                                            "original_size_bytes": original_byte_size,
                                            "truncated_size_bytes": truncated_byte_size,
                                            "truncation_percentage": round((1 - truncated_byte_size/original_byte_size) * 100, 2),
                                            "aggressive_truncation": True,
                                            "error": error_str
                                        }
                                        truncated_values_log.append(truncation_info)
                                        
                                        logger.info(
                                            f"Successfully imported with aggressive truncation: {dataset_name}.{column_name}[{row_id}] - "
                                            f"Original: {len(value)} chars ({original_byte_size} bytes), "
                                            f"Truncated: {len(truncated_value)} chars ({truncated_byte_size} bytes), "
                                            f"Reduced by: {truncation_info['truncation_percentage']}%"
                                        )
                                except Exception as e2:
                                    logger.error(f"Error on second attempt for {column_name} in row {row_id}: {e2}")
                                    stats["errors"] += 1
                            else:
                                logger.error(f"Database error processing cell {column_name} in row {row_id}: {e}")
                                stats["errors"] += 1
                        except Exception as e:
                            logger.error(f"Error processing cell {column_name} in row {row_id}: {e}")
                            stats["errors"] += 1
                            
                # Log progress every 100 rows
                if row_num % 100 == 0:
                    logger.info(f"Processed {row_num} rows...")
        
        # Log final statistics
        logger.info(f"Import completed: {stats['rows_processed']} rows, {stats['cells_processed']} cells, "
                    f"{stats['resources_created']} resources, {stats['triples_created']} triples, "
                    f"{stats['truncated_values']} truncated values, {stats['errors']} errors")
        
        # If there were truncated values, log a summary
        if truncated_values_log:
            logger.warning(f"Value truncation summary: {len(truncated_values_log)} values were truncated")
            
            # Group by column to see which columns have the most truncations
            column_counts = {}
            for trunc in truncated_values_log:
                column_key = f"{trunc['table']}.{trunc['column']}"
                if column_key not in column_counts:
                    column_counts[column_key] = 0
                column_counts[column_key] += 1
            
            # Log columns with truncations
            logger.warning("Columns with truncated values:")
            for column, count in sorted(column_counts.items(), key=lambda x: x[1], reverse=True):
                logger.warning(f"  {column}: {count} truncations")
            
            # Log some examples of the most severe truncations
            severe_truncations = sorted(truncated_values_log, key=lambda x: x['truncation_percentage'], reverse=True)[:5]
            if severe_truncations:
                logger.warning("Most severe truncations:")
                for i, trunc in enumerate(severe_truncations):
                    logger.warning(
                        f"  {i+1}. {trunc['table']}.{trunc['column']}[{trunc['row_id']}]: "
                        f"Original {trunc['original_size_bytes']} bytes → {trunc['truncated_size_bytes']} bytes "
                        f"({trunc['truncation_percentage']}% reduction)"
                    )
        
        # Add truncation log to stats for potential further analysis
        stats["truncated_values_details"] = truncated_values_log
        
        return stats
    
    except Exception as e:
        logger.error(f"Error importing CSV {csv_file_path}: {e}")
        stats["errors"] += 1
        return stats


def brute_force_import_relationship_csv(
    csv_file_path: str,
    dataset_name: str,
    fk_columns: List[Dict[str, str]],
    institution: str = "DEFAULT",
    base_uri: str = "http://arkumu.org/data",
    delimiter: str = ';',
    has_quoted_fields: bool = False,
    max_value_size: int = MAX_INDEXED_VALUE_SIZE
) -> Dict[str, Any]:
    """
    Import a relationship CSV file that connects entities from other tables.
    
    Args:
        csv_file_path: Path to the CSV file
        dataset_name: Name for the dataset (used in URI)
        fk_columns: List of dicts with foreign key column info, e.g.:
                   [
                     {"column": "Proj_ID_fk", "target_table": "00_Projekte", "target_column": "Projekt_ID"},
                     {"column": "Equipment_ID_fk", "target_table": "19_Equipment_und_Software", "target_column": "Equipment_ID"}
                   ]
        institution: Institution code
        base_uri: Base URI for generated resources
        delimiter: CSV column delimiter
        has_quoted_fields: Whether fields in the CSV are quoted
        max_value_size: Maximum size for indexed values to prevent btree index errors
        
    Returns:
        Dict with import statistics
    """
    stats = {
        "rows_processed": 0,
        "relationships_created": 0,
        "resources_created": 0,
        "triples_created": 0,
        "errors": 0,
        "truncated_values": 0
    }
    
    try:
        # Create or get common resources
        with transaction.atomic():
            # Create the relationship property
            relates = Resource.objects.get_or_create(
                uri="http://purl.org/dc/terms/relation",
                resource_type=ResourceType.PROPERTY,
                name="relation",
                source=institution
            )[0]
            if relates.pk is None:
                stats["resources_created"] += 1
        
        # Process the CSV file
        with open(csv_file_path, newline='', encoding='utf-8') as f:
            quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
            reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
            
            for row_num, row in enumerate(reader):
                stats["rows_processed"] += 1
                
                # Get values from foreign key columns
                fk_values = {}
                for fk_info in fk_columns:
                    col = fk_info["column"]
                    if col in row and row[col].strip():
                        value = row[col].strip()
                        
                        # Check if value exceeds the maximum size for indexing
                        if len(value.encode('utf-8')) > max_value_size:
                            # Truncate the value to avoid btree index errors
                            original_value = value
                            while len(value.encode('utf-8')) > max_value_size:
                                value = value[:-1]
                            value += "..."  # Add ellipsis to indicate truncation
                            stats["truncated_values"] += 1
                            logger.warning(f"Truncated value for {col} in row {row_num} from {len(original_value)} chars to {len(value)} chars")
                        
                        fk_values[col] = value
                
                # Need at least two FK values to create a relationship
                if len(fk_values) >= 2:
                    try:
                        with transaction.atomic():
                            # Create resources for each FK target
                            fk_resources = {}
                            for fk_info in fk_columns:
                                col = fk_info["column"]
                                if col in fk_values:
                                    target_table = fk_info["target_table"]
                                    target_col = fk_info["target_column"]
                                    value = fk_values[col]
                                    
                                    # Create or get resource for target entity
                                    target_uri = f"{base_uri}/datasets/{target_table}/{target_col}/{value}"
                                    target_resource, created = Resource.objects.get_or_create(
                                        uri=target_uri,
                                        defaults={
                                            "resource_type": ResourceType.IRI,
                                            "source": institution,
                                            "name": f"{target_table}.{target_col}",
                                            "is_placeholder": True  # Mark as placeholder until fully imported
                                        }
                                    )
                                    if created:
                                        stats["resources_created"] += 1
                                    
                                    fk_resources[col] = target_resource
                            
                            # Create relationships between all pairs of FK resources
                            fk_cols = list(fk_resources.keys())
                            for i in range(len(fk_cols)):
                                for j in range(i+1, len(fk_cols)):
                                    col1 = fk_cols[i]
                                    col2 = fk_cols[j]
                                    
                                    # Create triple in both directions
                                    Triple.objects.create(
                                        subject=fk_resources[col1],
                                        predicate=relates,
                                        object=fk_resources[col2]
                                    )
                                    stats["triples_created"] += 1
                                    
                                    Triple.objects.create(
                                        subject=fk_resources[col2],
                                        predicate=relates,
                                        object=fk_resources[col1]
                                    )
                                    stats["triples_created"] += 1
                                    
                                    stats["relationships_created"] += 1
                    
                    except (IntegrityError, DataError) as e:
                        error_str = str(e)
                        # Check if this is a btree index size error
                        if BTREE_SIZE_ERROR_PATTERN.search(error_str):
                            logger.warning(f"Btree index size error in relationship row {row_num}. Retrying with more aggressive truncation.")
                            try:
                                # Try again with more aggressively truncated values
                                with transaction.atomic():
                                    # Create resources for each FK target with more aggressive truncation
                                    fk_resources = {}
                                    for fk_info in fk_columns:
                                        col = fk_info["column"]
                                        if col in row and row[col].strip():
                                            target_table = fk_info["target_table"]
                                            target_col = fk_info["target_column"]
                                            
                                            # Get original value and truncate aggressively
                                            original_value = row[col].strip()
                                            value = original_value
                                            if len(value.encode('utf-8')) > max_value_size // 2:
                                                value = value[:max_value_size // 4].encode('utf-8')[:max_value_size // 2].decode('utf-8', errors='ignore')
                                                value += "..."
                                                stats["truncated_values"] += 1
                                            
                                            # Create or get resource for target entity
                                            target_uri = f"{base_uri}/datasets/{target_table}/{target_col}/{value}"
                                            target_resource, created = Resource.objects.get_or_create(
                                                uri=target_uri,
                                                defaults={
                                                    "resource_type": ResourceType.IRI,
                                                    "source": institution,
                                                    "name": f"{target_table}.{target_col}",
                                                    "is_placeholder": True
                                                }
                                            )
                                            if created:
                                                stats["resources_created"] += 1
                                            
                                            fk_resources[col] = target_resource
                                    
                                    # Create relationships between all pairs of FK resources
                                    fk_cols = list(fk_resources.keys())
                                    for i in range(len(fk_cols)):
                                        for j in range(i+1, len(fk_cols)):
                                            col1 = fk_cols[i]
                                            col2 = fk_cols[j]
                                            
                                            # Create triple in both directions
                                            Triple.objects.create(
                                                subject=fk_resources[col1],
                                                predicate=relates,
                                                object=fk_resources[col2]
                                            )
                                            stats["triples_created"] += 1
                                            
                                            Triple.objects.create(
                                                subject=fk_resources[col2],
                                                predicate=relates,
                                                object=fk_resources[col1]
                                            )
                                            stats["triples_created"] += 1
                                            
                                            stats["relationships_created"] += 1
                                            
                                    logger.info(f"Successfully imported relationship in row {row_num} with truncated values")
                            except Exception as e2:
                                logger.error(f"Error on second attempt for relationship in row {row_num}: {e2}")
                                stats["errors"] += 1
                        else:
                            logger.error(f"Database error processing relationship in row {row_num}: {e}")
                            stats["errors"] += 1
                    except Exception as e:
                        logger.error(f"Error processing relationship in row {row_num}: {e}")
                        stats["errors"] += 1
                
                # Log progress every 100 rows
                if row_num % 100 == 0:
                    logger.info(f"Processed {row_num} rows...")
        
        # Log final statistics
        logger.info(f"Import completed: {stats['rows_processed']} rows, "
                    f"{stats['relationships_created']} relationships, "
                    f"{stats['resources_created']} resources, {stats['triples_created']} triples, "
                    f"{stats['truncated_values']} truncated values, {stats['errors']} errors")
        
        return stats
    
    except Exception as e:
        logger.error(f"Error importing relationship CSV {csv_file_path}: {e}")
        stats["errors"] += 1
        return stats 