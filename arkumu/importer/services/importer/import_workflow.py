import os
import logging
from typing import Dict, List, Any, Optional

from arkumu.importer.services.importer.bulk_import import import_csv_as_cells
# PlaceholderManager no longer used - relationships handled in post-processing
from arkumu.importer.services.importer.reference_resolver import ReferenceResolver
from arkumu.importer.services.importer.file_handler import FileHandler

logger = logging.getLogger(__name__)

class ImportWorkflowService:
    """
    Main orchestration service for CSV import workflow with placeholder-based reference resolution.
    All CSV files are processed uniformly with automatic foreign key detection.
    """
    
    def __init__(self):
        # No longer using placeholder manager
        self.reference_resolver = ReferenceResolver()
        self.file_handler = FileHandler()
    
    @staticmethod
    def import_csv(
        csv_path: str,
        dataset_name: Optional[str] = None,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        file_columns: Optional[List[str]] = None,
        files_base_directory: Optional[str] = None,
        upload_service = None
    ) -> Dict[str, Any]:
        """
        Import a single CSV file with automatic placeholder-based reference resolution.
        """
        logger.info(f"🚀 Starting import of CSV file: {csv_path}")
        logger.info(f"   Dataset: {dataset_name}")
        logger.info(f"   Institution: {institution}")
        
        if not dataset_name:
            dataset_name = os.path.splitext(os.path.basename(csv_path))[0]
            logger.info(f"   Auto-detected dataset name: {dataset_name}")
        
        try:
            # No longer tracking placeholders - all data imported as literals
            logger.info(f"📋 Processing with simplified import (no placeholder handling)")
            stats = ImportWorkflowService._import_csv_with_placeholder_handling(
                csv_path,
                dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                file_columns=file_columns,
                files_base_directory=files_base_directory,
                upload_service=upload_service
            )
            
            # No longer tracking placeholders - all data imported as literals
            logger.info(f"📊 All data imported as literals - no placeholders created")
            
            logger.info(f"✅ Successfully imported {csv_path}")
            logger.info(f"📊 Final stats: {stats}")
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error importing {csv_path}: {e}")
            raise
    
    @staticmethod
    def import_csv_directory(
        directory_path: str,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        relationship_config_path: Optional[str] = None,
        file_columns: Optional[Dict[str, List[str]]] = None,
        files_base_directory: Optional[str] = None,
        upload_service=None
    ) -> Dict[str, Any]:
        """
        Import all CSV files in a directory with automatic placeholder-based reference resolution.
        Regular tables are processed with automatic foreign key detection.
        Relationship tables (if configured) are processed to create explicit relationships.
        """
        logger.info(f"�� Starting directory import from: {directory_path}")
        logger.info(f"   Institution: {institution}")
        logger.info(f"   Base URI: {base_uri}")
        # Load relationship configuration if provided
        relationship_config = {}
        if relationship_config_path and os.path.exists(relationship_config_path):
            try:
                import json
                with open(relationship_config_path, 'r') as f:
                    relationship_config = json.load(f)
                logger.info(f"📋 Loaded relationship configuration: {list(relationship_config.keys())}")
            except Exception as e:
                logger.warning(f"⚠️ Error loading relationship config: {e}")
        
        logger.info(f"   Using automatic reference detection for regular tables")
        if relationship_config:
            logger.info(f"   Using explicit relationship handling for: {list(relationship_config.keys())}")
        
        if not os.path.isdir(directory_path):
            error_msg = f"Directory not found: {directory_path}"
            logger.error(f"❌ {error_msg}")
            return {"error": error_msg}
            
        # No longer tracking placeholders - all data imported as literals
        
        # Get all CSV files
        csv_files = [f for f in os.listdir(directory_path) if f.endswith('.csv')]
        if not csv_files:
            error_msg = f"No CSV files found in directory: {directory_path}"
            logger.error(f"❌ {error_msg}")
            return {"error": error_msg}
        
        logger.info(f"📁 Found {len(csv_files)} CSV files: {csv_files}")
        
        # Use directory as files_base_directory if not provided
        if not files_base_directory:
            files_base_directory = directory_path
        
        # Initialize aggregate statistics
        aggregate_stats = {
            "files_processed": 0,
            "resources_created": 0,
            "triples_created": 0,
            "files_uploaded": 0,
            "upload_errors": 0,
            "errors": 0
        }
        
        # Process each CSV file uniformly
        for i, csv_file in enumerate(csv_files, 1):
            csv_path = os.path.join(directory_path, csv_file)
            dataset_name = os.path.splitext(csv_file)[0]
            
            logger.info(f"📄 Processing file {i}/{len(csv_files)}: {csv_file}")
            
            # No longer tracking placeholders
            
            try:
                # Get file columns for this dataset
                dataset_file_columns = file_columns.get(dataset_name, []) if file_columns else []
                
                # Check if this is a relationship table
                if dataset_name in relationship_config:
                    logger.info(f"📋 Processing {csv_file} as relationship table")
                    file_stats = ImportWorkflowService._import_relationship_csv(
                        csv_path=csv_path,
                        dataset_name=dataset_name,
                        relationship_config=relationship_config[dataset_name],
                        institution=institution,
                        base_uri=base_uri,
                        delimiter=delimiter,
                        has_quoted_fields=has_quoted_fields
                    )
                else:
                    logger.info(f"📋 Processing {csv_file} with automatic reference detection")
                    
                    if dataset_file_columns:
                        logger.info(f"📎 File columns configured: {dataset_file_columns}")
                    
                    # Import as regular table with placeholder handling
                    file_stats = ImportWorkflowService.import_csv(
                        csv_path=csv_path,
                        dataset_name=dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                        file_columns=dataset_file_columns,
                files_base_directory=files_base_directory,
                        upload_service=upload_service
                    )
                
                # No longer tracking placeholders - all data imported as literals
                logger.info(f"📊 File {csv_file} imported successfully")
                
                # Aggregate statistics
                for key, value in file_stats.items():
                    if key in aggregate_stats and isinstance(value, (int, float)):
                        aggregate_stats[key] += value
                
                aggregate_stats["files_processed"] += 1
                
                logger.info(f"✅ Successfully processed {csv_file}")
                logger.info(f"📊 File stats: {file_stats}")
                
            except Exception as e:
                logger.error(f"❌ Error processing {csv_file}: {e}")
                aggregate_stats["errors"] += 1
                continue
                
        logger.info(f"🎯 Directory import completed!")
        logger.info(f"📊 Final aggregate stats: {aggregate_stats}")
        logger.info(f"📊 All data imported as literals - relationships can be processed in post-processing")
        
        return aggregate_stats
    
    @staticmethod
    def _import_csv_with_placeholder_handling(
        file_path: str,
        dataset_name: str,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        file_columns: List[str] = None,
        files_base_directory: str = None,
        upload_service = None
    ) -> Dict[str, Any]:
        """
        Import a CSV file with placeholder handling for references.
        """
        logger.info(f"🔧 Starting _import_csv_with_placeholder_handling for {file_path}")
        
        # First, perform regular CSV import
        logger.info(f"🔧 Step 1: Calling import_csv_as_cells for {dataset_name}")
        logger.info(f"   📁 File path: {file_path}")
        logger.info(f"   🏛️ Institution: {institution}")
        logger.info(f"   🌐 Base URI: {base_uri}")
        logger.info(f"   📊 Delimiter: '{delimiter}'")
        logger.info(f"   📝 Has quoted fields: {has_quoted_fields}")
        
        stats = import_csv_as_cells(
            file_path,
            dataset_name,
            institution=institution,
            base_uri=base_uri,
            delimiter=delimiter,
            has_quoted_fields=has_quoted_fields
        )
        
        logger.info(f"✅ Step 1 completed: import_csv_as_cells finished")
        logger.info(f"   📊 Rows processed: {stats.get('rows_processed', 0)}")
        logger.info(f"   📊 Cells processed: {stats.get('cells_processed', 0)}")
        logger.info(f"   📊 Resources created: {stats.get('resources_created', 0)}")
        logger.info(f"   📊 Triples created: {stats.get('triples_created', 0)}")
        logger.info(f"   📊 Errors: {stats.get('errors', 0)}")
        logger.info(f"   📊 Truncated values: {stats.get('truncated_values', 0)}")
        
        # No longer tracking placeholders - all data imported as literals
        
        # Skip reference processing - we'll handle relationships in a separate phase
        logger.info(f"🔧 Step 2: Skipping reference processing (will be handled in post-processing)")
        logger.info(f"   ⏭️ All values imported as literals, relationships will be created later")
        
        logger.info(f"✅ Step 2 completed: Reference processing skipped")
        logger.info(f"   📊 All data imported as literals - relationships will be processed later")
        
        # Handle file uploads if configured
        if file_columns and upload_service and files_base_directory:
            logger.info(f"🔧 Step 3: Starting file upload processing")
            logger.info(f"   📎 File columns configured: {file_columns}")
            logger.info(f"   📁 Files base directory: {files_base_directory}")
            logger.info(f"   ☁️ Upload service: {type(upload_service).__name__}")
            
            uploaded_files = {}
            FileHandler.handle_file_uploads(
                file_path, dataset_name, institution, base_uri, delimiter, has_quoted_fields,
                file_columns, files_base_directory, upload_service, uploaded_files, stats
            )
            
            logger.info(f"✅ Step 3 completed: File upload processing finished")
            logger.info(f"   📊 Files uploaded: {stats.get('files_uploaded', 0)}")
            logger.info(f"   📊 Upload errors: {stats.get('upload_errors', 0)}")
        else:
            logger.info(f"⏭️ Step 3: Skipping file uploads (not configured)")
            missing_components = []
            if not file_columns:
                missing_components.append("file_columns")
            if not upload_service:
                missing_components.append("upload_service")
            if not files_base_directory:
                missing_components.append("files_base_directory")
            logger.info(f"   ❌ Missing: {', '.join(missing_components)}")
        
        logger.info(f"🔧 _import_csv_with_placeholder_handling completed for {file_path}")
        return stats
    
    # _process_references_and_placeholders method removed - no longer using placeholders
    
    @staticmethod
    def _import_relationship_csv(
        csv_path: str,
        dataset_name: str,
        relationship_config: List[Dict[str, str]],
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False
    ) -> Dict[str, Any]:
        """
        Import a relationship CSV file using the import_relationship_csv function.
        """
        from arkumu.importer.services.importer.bulk_import import import_relationship_csv
        
        logger.info(f"🔗 Starting relationship CSV import for {dataset_name}")
        logger.info(f"   📁 File path: {csv_path}")
        logger.info(f"   🏛️ Institution: {institution}")
        logger.info(f"   🌐 Base URI: {base_uri}")
        logger.info(f"   📊 Delimiter: '{delimiter}'")
        logger.info(f"   📝 Has quoted fields: {has_quoted_fields}")
        
        # Convert relationship config to the format expected by import_relationship_csv
        fk_columns = []
        for rel_config in relationship_config:
            fk_columns.append({
                "column": rel_config["column"],
                "target_table": rel_config["target_table"],
                "target_column": "id"  # Assume 'id' column for target
            })
        
        logger.info(f"🔗 Configured FK columns: {len(fk_columns)} columns")
        for i, fk_col in enumerate(fk_columns, 1):
            logger.info(f"   {i}. Column '{fk_col['column']}' → {fk_col['target_table']}.{fk_col['target_column']}")
        
        stats = import_relationship_csv(
            csv_file_path=csv_path,
            dataset_name=dataset_name,
            fk_columns=fk_columns,
            institution=institution,
            base_uri=base_uri,
            delimiter=delimiter,
            has_quoted_fields=has_quoted_fields
        )
        
        logger.info(f"✅ Relationship CSV import completed for {dataset_name}")
        logger.info(f"   📊 Rows processed: {stats.get('rows_processed', 0)}")
        logger.info(f"   📊 Relationships created: {stats.get('relationships_created', 0)}")
        logger.info(f"   📊 Resources created: {stats.get('resources_created', 0)}")
        logger.info(f"   📊 Triples created: {stats.get('triples_created', 0)}")
        logger.info(f"   📊 Errors: {stats.get('errors', 0)}")
        logger.info(f"   📊 Truncated values: {stats.get('truncated_values', 0)}")
        
        # Ensure all expected stats are present
        if "placeholders_created" not in stats:
            stats["placeholders_created"] = 0
        if "placeholders_resolved" not in stats:
            stats["placeholders_resolved"] = 0
        if "files_uploaded" not in stats:
            stats["files_uploaded"] = 0
        if "upload_errors" not in stats:
            stats["upload_errors"] = 0
        
        return stats