import os
import logging
from typing import Dict, List, Any, Optional, Set, Union

from arkumu.importer.services.relationship_config import RelationshipConfigService
from arkumu.importer.services.importer.bulk_import import (
    brute_force_import_csv,
    brute_force_import_relationship_csv
)
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.utils.rdf_helpers import add_semantic_triple

logger = logging.getLogger(__name__)

class ImportWorkflowService:
    """
    Service for managing the complete CSV import workflow.
    """
    
    @staticmethod
    def import_csv(
        csv_path: str,
        dataset_name: Optional[str] = None,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        is_relationship_table: bool = False,
        fk_columns: Optional[List[Dict[str, str]]] = None,
        file_columns: Optional[List[str]] = None,
        files_base_directory: Optional[str] = None,
        upload_service = None
    ) -> Dict[str, Any]:
        """
        Import a single CSV file with optional file path handling.
        
        Args:
            csv_path: Path to the CSV file
            dataset_name: Name for the dataset (defaults to CSV filename without extension)
            institution: Institution code
            base_uri: Base URI for generated resources
            delimiter: CSV column delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            is_relationship_table: Whether this CSV represents a relationship table
            fk_columns: List of foreign key column configurations (required if is_relationship_table=True)
            file_columns: List of column names containing file paths
            files_base_directory: Base directory for resolving relative file paths
            upload_service: Service for uploading files (must have upload_file method)
            
        Returns:
            Dict with import statistics
        """
        if not os.path.isfile(csv_path):
            logger.error(f"CSV file not found: {csv_path}")
            return {"error": f"CSV file not found: {csv_path}"}
        
        # Use filename as dataset_name if not provided
        if not dataset_name:
            dataset_name = os.path.splitext(os.path.basename(csv_path))[0]
        
        # Use CSV directory as files_base_directory if not provided
        if not files_base_directory:
            files_base_directory = os.path.dirname(csv_path)
        
        # Initialize empty dict to track uploaded files
        uploaded_files = {}
        
        # Import based on whether it's a relationship table or not
        if is_relationship_table:
            if not fk_columns:
                logger.error("fk_columns is required for relationship tables")
                return {"error": "fk_columns is required for relationship tables"}
                
            return ImportWorkflowService._import_relationship_csv_with_file_handling(
                file_path=csv_path,
                dataset_name=dataset_name,
                fk_columns=fk_columns,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                file_columns=file_columns,
                files_base_directory=files_base_directory,
                upload_service=upload_service,
                uploaded_files=uploaded_files
            )
        else:
            return ImportWorkflowService._import_csv_with_file_handling(
                file_path=csv_path,
                dataset_name=dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                file_columns=file_columns,
                files_base_directory=files_base_directory,
                upload_service=upload_service,
                uploaded_files=uploaded_files
            )
    
    @staticmethod
    def import_csv_directory(
        directory_path: str,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        field_delimiter: str = ',',
        has_quoted_fields: bool = False,
        relationship_config_path: Optional[str] = None,
        file_columns: Optional[Dict[str, List[str]]] = None,
        files_base_directory: Optional[str] = None,
        upload_service=None
    ) -> Dict[str, Any]:
        """
        Import all CSV files in a directory, automatically detecting relationship tables.
        
        Args:
            directory_path: Path to directory containing CSV files
            institution: Institution code
            base_uri: Base URI for generated resources
            delimiter: CSV column delimiter
            field_delimiter: Multi-value field delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            relationship_config_path: Optional path to a relationship configuration file
            file_columns: Dict mapping table names to lists of column names containing file paths
            files_base_directory: Base directory for resolving relative file paths
            upload_service: Service for uploading files (must have upload_file method)
            
        Returns:
            Dict with import statistics
        """
        if not os.path.isdir(directory_path):
            logger.error(f"Directory not found: {directory_path}")
            return {"error": f"Directory not found: {directory_path}"}
            
        csv_files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) if f.endswith('.csv')]
        
        if not csv_files:
            logger.warning(f"No CSV files found in {directory_path}")
            return {"error": f"No CSV files found in {directory_path}"}
        
        # Set default file columns if not provided
        file_columns = file_columns or {}
        
        # Use directory_path as files_base_directory if not provided
        files_base_directory = files_base_directory or directory_path
        
        # Step 1: Detect or load relationship configuration
        if relationship_config_path and os.path.exists(relationship_config_path):
            # Load existing configuration
            relationship_config = RelationshipConfigService.load_relationship_config(relationship_config_path)
            logger.info(f"Loaded relationship configuration from {relationship_config_path}")
        else:
            # Auto-detect relationships
            temp_config_path = os.path.join(directory_path, "auto_relationship_config.json")
            relationship_config = RelationshipConfigService.analyze_csv_directory(
                directory_path,
                output_path=temp_config_path,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields
            )
            logger.info(f"Auto-detected relationship configuration with {len(relationship_config)} tables")
        
        # Step 2: Import CSV files
        total_stats = {
            "files_processed": 0,
            "rows_processed": 0,
            "cells_processed": 0,
            "resources_created": 0,
            "triples_created": 0,
            "relationships_created": 0,
            "files_uploaded": 0,
            "upload_errors": 0,
            "errors": 0
        }
        
        # Track uploaded files to avoid duplicates
        uploaded_files = {}
        
        # First import non-relationship tables
        for file_path in csv_files:
            file_name = os.path.basename(file_path)
            dataset_name = os.path.splitext(file_name)[0]
            
            # Skip relationship tables in the first pass
            if dataset_name in relationship_config:
                continue
                
            logger.info(f"Importing regular table: {file_name}")
            
            # Check if this table has file columns
            table_file_columns = file_columns.get(dataset_name, [])
            
            # Import the table
            stats = ImportWorkflowService._import_csv_with_file_handling(
                file_path,
                dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                file_columns=table_file_columns,
                files_base_directory=files_base_directory,
                upload_service=upload_service,
                uploaded_files=uploaded_files
            )
            
            # Update total stats
            total_stats["files_processed"] += 1
            for key in stats:
                if key in total_stats:
                    total_stats[key] += stats[key]
        
        # Then import relationship tables
        for table_name, fk_config in relationship_config.items():
            file_path = None
            for f in csv_files:
                if os.path.splitext(os.path.basename(f))[0] == table_name:
                    file_path = f
                    break
            
            if not file_path:
                logger.warning(f"Relationship table file not found: {table_name}")
                continue
                
            logger.info(f"Importing relationship table: {table_name}")
            
            # Check if this relationship table has file columns
            table_file_columns = file_columns.get(table_name, [])
            
            # Import the relationship table
            stats = ImportWorkflowService._import_relationship_csv_with_file_handling(
                file_path,
                table_name,
                fk_config,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                file_columns=table_file_columns,
                files_base_directory=files_base_directory,
                upload_service=upload_service,
                uploaded_files=uploaded_files
            )
            
            # Update total stats
            total_stats["files_processed"] += 1
            for key in stats:
                if key in total_stats:
                    total_stats[key] += stats[key]
        
        return total_stats
    
    @staticmethod
    def _import_csv_with_file_handling(
        file_path: str,
        dataset_name: str,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        file_columns: List[str] = None,
        files_base_directory: str = None,
        upload_service = None,
        uploaded_files: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Import a CSV file with handling for file path columns.
        
        Args:
            file_path: Path to the CSV file
            dataset_name: Name for the dataset
            institution: Institution code
            base_uri: Base URI for generated resources
            delimiter: CSV column delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            file_columns: List of column names containing file paths
            files_base_directory: Base directory for resolving relative file paths
            upload_service: Service for uploading files
            uploaded_files: Dict to track already uploaded files
            
        Returns:
            Dict with import statistics
        """
        import csv
        
        file_columns = file_columns or []
        uploaded_files = uploaded_files or {}
        
        # First, perform regular import
        stats = brute_force_import_csv(
            file_path,
            dataset_name,
            institution=institution,
            base_uri=base_uri,
            delimiter=delimiter,
            has_quoted_fields=has_quoted_fields
        )
        
        # If no file columns or no upload service, return stats
        if not file_columns or not upload_service or not files_base_directory:
            return stats
        
        # Add stats for file uploads
        stats["files_uploaded"] = 0
        stats["upload_errors"] = 0
        
        # Process file columns
        try:
            # Get dataset resource
            dataset_uri = f"{base_uri}/datasets/{dataset_name}"
            dataset = Resource.objects.get(uri=dataset_uri)
            
            # Read CSV to get file paths
            with open(file_path, newline='', encoding='utf-8') as f:
                quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
                reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
                
                # Process each row
                for row_num, row in enumerate(reader):
                    # Process each file column
                    for col_name in file_columns:
                        if col_name not in row:
                            continue
                            
                        file_path_value = row.get(col_name)
                        if not file_path_value or file_path_value.strip() == '':
                            continue
                            
                        # Find the cell resource for this value
                        cell_uri = f"{dataset_uri}/{col_name}/{row.get('id', str(row_num))}"
                        try:
                            cell = Resource.objects.get(uri=cell_uri)
                            
                            # Resolve and upload the file
                            full_file_path = ImportWorkflowService._resolve_file_path(
                                files_base_directory,
                                file_path_value
                            )
                            
                            # Check if already uploaded
                            if full_file_path in uploaded_files:
                                file_url = uploaded_files[full_file_path]
                            else:
                                # Upload the file
                                success, result = upload_service.upload_file(full_file_path)
                                
                                if success:
                                    file_url = result
                                    uploaded_files[full_file_path] = file_url
                                    stats["files_uploaded"] += 1
                                else:
                                    logger.error(f"Error uploading file: {result}")
                                    stats["upload_errors"] += 1
                                    continue
                            
                            # Add file URL as a property of the cell
                            has_file_url = Resource.objects.get_or_create(
                                uri="http://purl.org/dc/terms/hasFormat",
                                defaults={
                                    "resource_type": ResourceType.PROPERTY,
                                    "name": "hasFormat",
                                    "source": institution
                                }
                            )[0]
                            
                            # Add the triple
                            add_semantic_triple(
                                subject_uri=cell_uri,
                                predicate_uri="http://purl.org/dc/terms/hasFormat",
                                object_uri_or_value=file_url,
                                source=institution
                            )
                            stats["triples_created"] += 1
                            
                        except Resource.DoesNotExist:
                            logger.error(f"Cell resource not found: {cell_uri}")
                            continue
        except Exception as e:
            logger.error(f"Error processing file columns: {e}")
            stats["errors"] += 1
        
        return stats
    
    @staticmethod
    def _import_relationship_csv_with_file_handling(
        file_path: str,
        dataset_name: str,
        fk_columns: List[Dict[str, str]],
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        file_columns: List[str] = None,
        files_base_directory: str = None,
        upload_service = None,
        uploaded_files: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Import a relationship CSV file with handling for file path columns.
        
        Args:
            file_path: Path to the CSV file
            dataset_name: Name for the dataset
            fk_columns: List of dicts with foreign key column info
            institution: Institution code
            base_uri: Base URI for generated resources
            delimiter: CSV column delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            file_columns: List of column names containing file paths
            files_base_directory: Base directory for resolving relative file paths
            upload_service: Service for uploading files
            uploaded_files: Dict to track already uploaded files
            
        Returns:
            Dict with import statistics
        """
        # First, perform regular relationship import
        stats = brute_force_import_relationship_csv(
            file_path,
            dataset_name,
            fk_columns,
            institution=institution,
            base_uri=base_uri,
            delimiter=delimiter,
            has_quoted_fields=has_quoted_fields
        )
        
        # If no file columns or no upload service, return stats
        if not file_columns or not upload_service or not files_base_directory:
            return stats
        
        import csv
        
        # Add stats for file uploads
        stats["files_uploaded"] = 0
        stats["upload_errors"] = 0
        
        file_columns = file_columns or []
        uploaded_files = uploaded_files or {}
        
        # Process file columns
        try:
            # Get dataset resource
            dataset_uri = f"{base_uri}/datasets/{dataset_name}"
            dataset = Resource.objects.get(uri=dataset_uri)
            
            # Read CSV to get file paths
            with open(file_path, newline='', encoding='utf-8') as f:
                quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
                reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
                
                # Process each row
                for row_num, row in enumerate(reader):
                    # Process each file column
                    for col_name in file_columns:
                        if col_name not in row:
                            continue
                            
                        file_path_value = row.get(col_name)
                        if not file_path_value or file_path_value.strip() == '':
                            continue
                            
                        # For relationship tables, we need to handle the cell URI differently
                        # since it's part of a relationship table
                        cell_uri = f"{dataset_uri}/{col_name}/{row.get('id', str(row_num))}"
                        try:
                            cell = Resource.objects.get(uri=cell_uri)
                            
                            # Resolve and upload the file
                            full_file_path = ImportWorkflowService._resolve_file_path(
                                files_base_directory,
                                file_path_value
                            )
                            
                            # Check if already uploaded
                            if full_file_path in uploaded_files:
                                file_url = uploaded_files[full_file_path]
                            else:
                                # Upload the file
                                success, result = upload_service.upload_file(full_file_path)
                                
                                if success:
                                    file_url = result
                                    uploaded_files[full_file_path] = file_url
                                    stats["files_uploaded"] += 1
                                else:
                                    logger.error(f"Error uploading file: {result}")
                                    stats["upload_errors"] += 1
                                    continue
                            
                            # Add file URL as a property of the cell
                            has_file_url = Resource.objects.get_or_create(
                                uri="http://purl.org/dc/terms/hasFormat",
                                defaults={
                                    "resource_type": ResourceType.PROPERTY,
                                    "name": "hasFormat",
                                    "source": institution
                                }
                            )[0]
                            
                            # Add the triple
                            add_semantic_triple(
                                subject_uri=cell_uri,
                                predicate_uri="http://purl.org/dc/terms/hasFormat",
                                object_uri_or_value=file_url,
                                source=institution
                            )
                            stats["triples_created"] += 1
                            
                        except Resource.DoesNotExist:
                            logger.error(f"Cell resource not found: {cell_uri}")
                            continue
        except Exception as e:
            logger.error(f"Error processing file columns: {e}")
            stats["errors"] += 1
        
        return stats
    
    @staticmethod
    def _resolve_file_path(base_directory: str, relative_path: str) -> str:
        """
        Resolve a relative file path against a base directory.
        
        Args:
            base_directory: Base directory
            relative_path: Relative path from the CSV
            
        Returns:
            Absolute path to the file
        """
        # Handle different path formats
        clean_path = relative_path.strip().replace('\\', '/').lstrip('/')
        
        # Try different combinations to find the file
        candidates = [
            os.path.join(base_directory, clean_path),
            os.path.join(base_directory, 'files', clean_path),
            os.path.join(base_directory, '..', 'files', clean_path)
        ]
        
        for path in candidates:
            if os.path.exists(path):
                return path
        
        # If file not found, return the first candidate
        return candidates[0] 