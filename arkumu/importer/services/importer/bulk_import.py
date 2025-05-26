import csv
import logging
import re
from typing import List, Dict, Any, Optional, Literal
import os

from django.db import transaction, IntegrityError, DataError
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part

logger = logging.getLogger(__name__)

# Maximum size for values to avoid btree index errors (PostgreSQL limit is 2704)
MAX_INDEXED_VALUE_SIZE = 2500

# Regular expression to detect btree index size errors
BTREE_SIZE_ERROR_PATTERN = re.compile(r"index row size \d+ exceeds btree .* maximum \d+ for index")

def import_csv_as_cells(
    csv_file_path: str,
    dataset_name: str,
    institution: str = "DEFAULT",
    base_uri: str = "http://arkumu.org/data",
    delimiter: str = ';',
    has_quoted_fields: bool = False,
    batch_size: int = 1000,
    max_value_size: int = MAX_INDEXED_VALUE_SIZE,
    create_row_resources: bool = True,
    link_cells_to_rows: bool = True,
    link_topology: str = "row"  # Options: "row", "first_column", "mesh"
) -> Dict[str, Any]:
    """
    Import a CSV file by creating individual resources for each cell.
    This approach treats each cell as a separate entity with:
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
        batch_size: Number of rows to process in each batch
        max_value_size: Maximum size for indexed values to prevent btree index errors
        create_row_resources: Whether to create row resources
        link_cells_to_rows: Whether to link cells to rows
        link_topology: How to link cells within a row:
                      "row" - Link each cell to the row resource (default)
                      "first_column" - Link all cells to the first column cell
                      "mesh" - Link all cells to each other in a mesh topology
        
    Returns:
        Dict with import statistics
    """
    stats = {
        "rows_processed": 0,
        "cells_processed": 0,
        "resources_created": 0,
        "triples_created": 0,
        "row_links_created": 0,
        "errors": 0,
        "truncated_values": 0
    }
    
    # Keep track of truncated values for logging
    truncated_values_log = []
    
    # Create properties for row linking if enabled
    belongs_to_row_property = None
    same_row_property = None
    row_class = None
    if create_row_resources or link_cells_to_rows:
        logger.info(f"Row resources and linking enabled for {dataset_name}")
    
    try:
        logger.info(f"Starting import_csv_as_cells for {dataset_name}")
        # Create or get common resources
        dataset_uri = mint_uri(base_uri, institution, "datasets", dataset_name)
        logger.info(f"Dataset URI: {dataset_uri}")
        
        # Get common properties using Django ORM - but handle potential transaction issues
        logger.info(f"Getting common properties using Django ORM")
        
        # Create common resources once
        try:
            # Force a new transaction to avoid any existing transaction issues
            with transaction.atomic():
                has_part, created = Resource.objects.update_or_create(
                    uri="http://purl.org/dc/terms/hasPart",
                    defaults={
                        "resource_type": ResourceType.PROPERTY,
                        "name": "hasPart",
                        "source": institution,
                        "is_placeholder": False
                    }
                )
                if created:
                    stats["resources_created"] += 1
                
                rdf_value, created = Resource.objects.update_or_create(
                    uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
                    defaults={
                        "resource_type": ResourceType.PROPERTY,
                        "name": "value",
                        "source": institution,
                        "is_placeholder": False
                    }
                )
                if created:
                    stats["resources_created"] += 1
                
                rdf_type, created = Resource.objects.update_or_create(
                    uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                    defaults={
                        "resource_type": ResourceType.PROPERTY,
                        "name": "type",
                        "source": institution,
                        "is_placeholder": False
                    }
                )
                if created:
                    stats["resources_created"] += 1
                
                cell_class, created = Resource.objects.update_or_create(
                    uri=mint_uri(base_uri, institution, "classes", "Cell"),
                    defaults={
                        "resource_type": ResourceType.CLASS,
                        "name": "Cell",
                        "source": institution,
                        "is_placeholder": False
                    }
                )
                if created:
                    stats["resources_created"] += 1

                # Create row-related properties if needed
                if create_row_resources or link_cells_to_rows:
                    belongs_to_row_property, created = Resource.objects.update_or_create(
                        uri=mint_uri(base_uri, institution, "properties", "belongsToRow"),
                        defaults={
                            "resource_type": ResourceType.PROPERTY,
                            "name": "belongsToRow",
                            "source": institution,
                            "is_placeholder": False
                        }
                    )
                    if created:
                        stats["resources_created"] += 1

                    # Create sameRow property for advanced linking topologies
                    if link_topology in ["first_column", "mesh"]:
                        same_row_property, created = Resource.objects.update_or_create(
                            uri=mint_uri(base_uri, institution, "properties", "sameRow"),
                            defaults={
                                "resource_type": ResourceType.PROPERTY,
                                "name": "sameRow",
                                "source": institution,
                                "is_placeholder": False
                            }
                        )
                        if created:
                            stats["resources_created"] += 1

                    row_class, created = Resource.objects.update_or_create(
                        uri=mint_uri(base_uri, institution, "classes", "Row"),
                        defaults={
                            "resource_type": ResourceType.CLASS,
                            "name": "Row",
                            "source": institution,
                            "is_placeholder": False
                        }
                    )
                    if created:
                        stats["resources_created"] += 1

                logger.info(f"Creating main dataset resource")
                # Create the main dataset resource
                dataset, created = Resource.objects.update_or_create(
                    uri=dataset_uri,
                    defaults={
                        "resource_type": ResourceType.IRI,
                        "name": dataset_name,
                        "source": institution,
                        "is_placeholder": False
                    }
                )
                if created:
                    stats["resources_created"] += 1
                
                logger.info(f"Dataset resource ready with ID: {dataset.id}")
                
        except Exception as e:
            logger.error(f"Error creating common properties: {e}")
            raise
        
        # Process the CSV file in batches
        with open(csv_file_path, newline='', encoding='utf-8') as f:
            quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
            reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
            
            # Batch processing variables
            batch_rows = []
            batch_resources_to_create = []
            batch_triples_to_create = []
            batch_row_cell_map = {}  # Maps row_id to list of cell resources for row linking
            
            for row_num, row in enumerate(reader):
                stats["rows_processed"] += 1
                row_id = row.get('id', row.get('ID', str(row_num)))
                
                # Collect row data for batch processing
                row_data = {
                    'row_id': row_id,
                    'row_num': row_num,
                    'cells': []
                }
                
                # Process each cell in the row
                for column_name, value in row.items():
                    if value and value.strip():  # Skip empty values
                        stats["cells_processed"] += 1
                        value = value.strip()
                        
                        # Check if value exceeds the maximum size for indexing
                        original_value = value
                        original_byte_size = len(value.encode('utf-8'))
                        
                        if original_byte_size > max_value_size:
                            # Truncate the value to avoid btree index errors
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
                        
                        # Prepare cell resource for batch creation
                        cell_uri = mint_uri(base_uri, institution, "datasets", dataset_name, column_name, row_id)
                        cell_resource = Resource(
                            uri=cell_uri,
                            resource_type=ResourceType.IRI,
                            source=institution,
                            name=column_name
                        )
                        
                        # Prepare value resource for batch creation
                        value_resource = Resource(
                            resource_type=ResourceType.LITERAL,
                            source=institution,
                            name=column_name,
                            value=value,
                            datatype="http://www.w3.org/2001/XMLSchema#string"
                        )
                        
                        # Add to batch
                        batch_resources_to_create.extend([cell_resource, value_resource])
                        
                        # Store cell data for triple creation after resources are saved
                        row_data['cells'].append({
                            'cell_resource': cell_resource,
                            'value_resource': value_resource,
                            'column_name': column_name
                        })
                
                batch_rows.append(row_data)
                
                # Process batch when it reaches the specified size
                if len(batch_rows) >= batch_size:
                    process_batch(
                        batch_rows, batch_resources_to_create, batch_triples_to_create,
                        batch_row_cell_map, dataset, has_part, rdf_type, rdf_value, cell_class,
                        belongs_to_row_property, same_row_property, row_class, 
                        create_row_resources, link_cells_to_rows, link_topology,
                        dataset_name, base_uri, institution, stats
                    )
                    
                    # Reset batch variables
                    batch_rows = []
                    batch_resources_to_create = []
                    batch_triples_to_create = []
                    batch_row_cell_map = {}
                
                # Log progress every 100 rows
                if row_num % 100 == 0:
                    logger.info(f"Processed {row_num} rows...")
            
            # Process remaining rows in the final batch
            if batch_rows:
                process_batch(
                    batch_rows, batch_resources_to_create, batch_triples_to_create,
                    batch_row_cell_map, dataset, has_part, rdf_type, rdf_value, cell_class,
                    belongs_to_row_property, same_row_property, row_class,
                    create_row_resources, link_cells_to_rows, link_topology,
                    dataset_name, base_uri, institution, stats
                )
        
        # Log final statistics
        logger.info(f"Import completed: {stats['rows_processed']} rows, {stats['cells_processed']} cells, "
                    f"{stats['resources_created']} resources, {stats['triples_created']} triples, "
                    f"{stats['row_links_created']} row links, "
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
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        stats["errors"] += 1
        return stats


def process_batch(
    batch_rows, batch_resources_to_create, batch_triples_to_create,
    batch_row_cell_map, dataset, has_part, rdf_type, rdf_value, cell_class,
    belongs_to_row_property, same_row_property, row_class, 
    create_row_resources, link_cells_to_rows, link_topology,
    dataset_name, base_uri, institution, stats
):
    """
    Process a batch of rows by bulk creating resources and triples.
    """
    try:
        with transaction.atomic():
            # Step 1: Bulk create all resources
            if batch_resources_to_create:
                created_resources = Resource.objects.bulk_create(
                    batch_resources_to_create, 
                    ignore_conflicts=True,
                    batch_size=1000
                )
                stats["resources_created"] += len(created_resources)
                logger.debug(f"Bulk created {len(created_resources)} resources")
            
            # Step 2: Prepare triples for bulk creation
            # We need to get the actual saved resources with their IDs
            cell_resources_map = {}  # Maps URI to actual resource object
            value_resources_list = []
            
            # Get saved cell resources by URI
            cell_uris = [r.uri for r in batch_resources_to_create if r.resource_type == ResourceType.IRI]
            saved_cell_resources = Resource.objects.filter(uri__in=cell_uris)
            for resource in saved_cell_resources:
                cell_resources_map[resource.uri] = resource
            
            # Get saved value resources (literals) - this is trickier since they don't have URIs
            # We'll match them by source, name, and value
            value_specs = [(r.source, r.name, r.value) for r in batch_resources_to_create if r.resource_type == ResourceType.LITERAL]
            if value_specs:
                # Build a complex query to find matching literal resources
                from django.db.models import Q
                query = Q()
                for source, name, value in value_specs:
                    query |= Q(source=source, name=name, value=value, resource_type=ResourceType.LITERAL)
                
                saved_value_resources = Resource.objects.filter(query)
                # Create a lookup map for value resources
                value_resources_map = {}
                for resource in saved_value_resources:
                    key = (resource.source, resource.name, resource.value)
                    value_resources_map[key] = resource
            
            # Step 3: Create triples for each row
            for row_data in batch_rows:
                row_cell_resources = []
                
                for cell_data in row_data['cells']:
                    cell_uri = cell_data['cell_resource'].uri
                    cell_resource = cell_resources_map.get(cell_uri)
                    
                    if cell_resource:
                        row_cell_resources.append(cell_resource)
                        
                        # Find the corresponding value resource
                        value_key = (
                            cell_data['value_resource'].source,
                            cell_data['value_resource'].name,
                            cell_data['value_resource'].value
                        )
                        value_resource = value_resources_map.get(value_key)
                        
                        if value_resource:
                            # Prepare triples for this cell
                            batch_triples_to_create.extend([
                                Triple(subject=dataset, predicate=has_part, object=cell_resource),
                                Triple(subject=cell_resource, predicate=rdf_type, object=cell_class),
                                Triple(subject=cell_resource, predicate=rdf_value, object=value_resource)
                            ])
                
                # Store row cell resources for row linking
                if row_cell_resources:
                    batch_row_cell_map[row_data['row_id']] = row_cell_resources
            
            # Step 4: Bulk create triples
            if batch_triples_to_create:
                created_triples = Triple.objects.bulk_create(
                    batch_triples_to_create,
                    ignore_conflicts=True,
                    batch_size=1000
                )
                stats["triples_created"] += len(created_triples)
                logger.debug(f"Bulk created {len(created_triples)} triples")
            
            # Step 5: Handle row linking
            if batch_row_cell_map and (create_row_resources or link_cells_to_rows):
                row_resources_created = []
                row_triples_to_create = []
                
                for row_id, cell_resources in batch_row_cell_map.items():
                    if cell_resources:
                        # Create row resource if enabled
                        row_resource = None
                        if create_row_resources:
                            row_uri = mint_uri(base_uri, institution, "datasets", dataset_name, "rows", row_id)
                            row_resource = Resource(
                                uri=row_uri,
                                resource_type=ResourceType.IRI,
                                name=f"Row {row_id}",
                                source=institution,
                                is_placeholder=False
                            )
                            row_resources_created.append(row_resource)
                        
                        # Handle different linking topologies
                        if link_cells_to_rows:
                            if link_topology == "row" and create_row_resources:
                                # Standard approach: Link all cells to the row resource
                                for cell_resource in cell_resources:
                                    row_triples_to_create.append(
                                        Triple(
                                            subject=cell_resource,
                                            predicate=belongs_to_row_property,
                                            object=row_resource
                                        )
                                    )
                                    stats["row_links_created"] += 1
                                
                                # Type the row resource
                                if row_class:
                                    row_triples_to_create.append(
                                        Triple(
                                            subject=row_resource,
                                            predicate=rdf_type,
                                            object=row_class
                                        )
                                    )
                            
                            elif link_topology == "first_column" and len(cell_resources) > 1 and same_row_property:
                                # Star topology: Link all cells to the first column
                                anchor_cell = cell_resources[0]
                                
                                for i in range(1, len(cell_resources)):
                                    row_triples_to_create.append(
                                        Triple(
                                            subject=anchor_cell,
                                            predicate=same_row_property,
                                            object=cell_resources[i]
                                        )
                                    )
                                    stats["row_links_created"] += 1
                            
                            elif link_topology == "mesh" and len(cell_resources) > 1 and same_row_property:
                                # Mesh topology: Link all cells to each other
                                for i in range(len(cell_resources)):
                                    for j in range(i+1, len(cell_resources)):
                                        row_triples_to_create.append(
                                            Triple(
                                                subject=cell_resources[i],
                                                predicate=same_row_property,
                                                object=cell_resources[j]
                                            )
                                        )
                                        stats["row_links_created"] += 1
                
                # Bulk create row resources if any were created
                if row_resources_created:
                    created_row_resources = Resource.objects.bulk_create(
                        row_resources_created,
                        ignore_conflicts=True,
                        batch_size=1000
                    )
                    stats["resources_created"] += len(created_row_resources)
                    logger.debug(f"Bulk created {len(created_row_resources)} row resources")
                    
                    # If we're using row topology, we need to update the row_triples_to_create
                    # to use the actual row resources with IDs
                    if link_topology == "row" and link_cells_to_rows:
                        # Get the created row resources by URI
                        row_uris = [r.uri for r in row_resources_created]
                        saved_row_resources = Resource.objects.filter(uri__in=row_uris)
                        row_resources_map = {r.uri: r for r in saved_row_resources}
                        
                        # Update row triples with actual row resources
                        updated_row_triples = []
                        for triple in row_triples_to_create:
                            if isinstance(triple.object, Resource) and not triple.object.id:
                                # This is a row resource that needs to be updated with the saved version
                                saved_row = row_resources_map.get(triple.object.uri)
                                if saved_row:
                                    triple.object = saved_row
                            updated_row_triples.append(triple)
                        row_triples_to_create = updated_row_triples
                
                # Bulk create row triples if any were created
                if row_triples_to_create:
                    created_row_triples = Triple.objects.bulk_create(
                        row_triples_to_create,
                        ignore_conflicts=True,
                        batch_size=1000
                    )
                    stats["triples_created"] += len(created_row_triples)
                    logger.debug(f"Bulk created {len(created_row_triples)} row linking triples")
                        
    except Exception as e:
        logger.error(f"Error processing batch: {e}")
        stats["errors"] += 1


def import_relationship_csv(
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
                                    target_uri = mint_uri(base_uri, institution, "datasets", target_table, target_col, value)
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
                                            target_uri = mint_uri(base_uri, institution, "datasets", target_table, target_col, value)
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