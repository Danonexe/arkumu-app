import os
import logging
from typing import Dict, List, Any, Optional

from arkumu.importer.services.importer.bulk_import import import_csv_as_cells
from arkumu.importer.services.importer.placeholder_manager import PlaceholderManager
from arkumu.importer.services.importer.reference_resolver import ReferenceResolver
from arkumu.importer.services.importer.file_handler import FileHandler

logger = logging.getLogger(__name__)

class ImportWorkflowService:
    """
    Main orchestration service for CSV import workflow with placeholder-based reference resolution.
    All CSV files are processed uniformly with automatic foreign key detection.
    """
    
    def __init__(self):
        self.placeholder_manager = PlaceholderManager()
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
            # Count initial placeholders
            initial_placeholders = PlaceholderManager.count_placeholders(institution)
            logger.info(f"📊 Initial placeholders in system: {initial_placeholders}")
            
            # Process as regular table with placeholder handling
            logger.info(f"📋 Processing with automatic reference detection and placeholder handling")
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
            
            # Count final placeholders
            final_placeholders = PlaceholderManager.count_placeholders(institution)
            
            placeholders_created = final_placeholders - initial_placeholders
            logger.info(f"📊 Placeholders created during import: {placeholders_created}")
            logger.info(f"📊 Total placeholders in system: {final_placeholders}")
            
            # Add placeholder stats to results
            stats["placeholders_created"] = placeholders_created
            stats["total_placeholders"] = final_placeholders
            
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
            
        # Count initial placeholders
        initial_placeholders = PlaceholderManager.count_placeholders(institution)
        logger.info(f"📊 Initial placeholders in system: {initial_placeholders}")
        
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
            "relationships_created": 0,
            "files_uploaded": 0,
            "upload_errors": 0,
            "errors": 0,
            "placeholders_created": 0,
            "placeholders_resolved": 0,
            "total_placeholders": 0
        }
        
        # Process each CSV file uniformly
        for i, csv_file in enumerate(csv_files, 1):
            csv_path = os.path.join(directory_path, csv_file)
            dataset_name = os.path.splitext(csv_file)[0]
            
            logger.info(f"📄 Processing file {i}/{len(csv_files)}: {csv_file}")
            
            # Count placeholders before this file
            placeholders_before = PlaceholderManager.count_placeholders(institution)
            
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
                
                # Count placeholders after this file
                placeholders_after = PlaceholderManager.count_placeholders(institution)
                
                placeholders_created_this_file = placeholders_after - placeholders_before
                logger.info(f"📊 File {csv_file} created {placeholders_created_this_file} new placeholders")
                logger.info(f"📊 Total placeholders now: {placeholders_after}")
                
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
                
        # Final placeholder analysis
        final_placeholders = PlaceholderManager.count_placeholders(institution)
        
        total_placeholders_created = final_placeholders - initial_placeholders
        aggregate_stats["total_placeholders"] = final_placeholders
        aggregate_stats["placeholders_created"] = total_placeholders_created
        
        logger.info(f"🎯 Directory import completed!")
        logger.info(f"📊 Total placeholders created: {total_placeholders_created}")
        logger.info(f"📊 Final placeholder count: {final_placeholders}")
        logger.info(f"📊 Final aggregate stats: {aggregate_stats}")
        
        # Log unresolved placeholders summary
        if final_placeholders > 0:
            logger.warning(f"⚠️ {final_placeholders} unresolved placeholders remain")
            
            # Analyze placeholder patterns
            analysis = PlaceholderManager.analyze_placeholder_patterns(institution)
            logger.info(f"📋 Placeholder analysis: {analysis}")
        
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
        
        # Add placeholder tracking
        stats["placeholders_created"] = 0
        stats["placeholders_resolved"] = 0
        
        # Process references and placeholders with debugging
        logger.info(f"🔧 Step 2: Starting reference processing and placeholder handling")
        logger.info(f"   🔍 Analyzing references in {dataset_name}")
        logger.info(f"   🏷️ Creating placeholders for missing references")
        logger.info(f"   🔗 Resolving existing placeholders")
        
        try:
            logger.info(f"DEBUG: About to call _process_references_and_placeholders")
            ImportWorkflowService._process_references_and_placeholders(
                file_path, dataset_name, institution, base_uri, delimiter, has_quoted_fields, stats
            )
            logger.info(f"DEBUG: _process_references_and_placeholders completed successfully")
        except Exception as e:
            logger.error(f"DEBUG: Error in _process_references_and_placeholders: {e}")
            raise
        
        logger.info(f"✅ Step 2 completed: Reference processing finished")
        logger.info(f"   📊 Placeholders created: {stats.get('placeholders_created', 0)}")
        logger.info(f"   📊 Placeholders resolved: {stats.get('placeholders_resolved', 0)}")
        
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
    
    @staticmethod
    def _process_references_and_placeholders(
        file_path: str,
        dataset_name: str,
        institution: str,
        base_uri: str,
        delimiter: str,
        has_quoted_fields: bool,
        stats: Dict[str, Any]
    ):
        """
        Process a CSV file to create placeholders for references and resolve existing ones.
        """
        import csv
        
        logger.info(f"🔧 Starting _process_references_and_placeholders for {file_path}")
        
        try:
            # First pass: collect all entity IDs and create placeholders
            entity_ids = []
            
            logger.info(f"🔧 Opening CSV file: {file_path}")
            with open(file_path, newline='', encoding='utf-8') as f:
                quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
                reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
                
                logger.info(f"🔧 Creating ReferenceResolver")
                reference_resolver = ReferenceResolver()
                
                logger.info(f"🔧 Starting to process rows")
                row_count = 0
                for row in reader:
                    row_count += 1
                    if row_count % 50 == 0:  # Log every 50th row
                        logger.info(f"🔧 Processing row {row_count}")
                    
                    row_id = row.get('id', '')
                    if row_id:
                        entity_ids.append(row_id)
                    
                    # Create placeholders for any references in this row
                    logger.debug(f"🔧 Creating placeholders for row {row_count}")
                    placeholders_created = PlaceholderManager.create_placeholders_for_references(
                        row, dataset_name, row_id, institution, base_uri, reference_resolver
                    )
                    stats["placeholders_created"] += placeholders_created
                
                logger.info(f"🔧 Finished processing {row_count} rows")
            
            # Second pass: batch resolve placeholders for all entity IDs
            # Only do this if we have entity IDs and there are placeholders to resolve
            logger.info(f"🔧 Collected {len(entity_ids)} entity IDs")
            if entity_ids:
                logger.info(f"🔧 Counting total placeholders")
                total_placeholders = PlaceholderManager.count_placeholders(institution)
                logger.info(f"🔧 Total placeholders in system: {total_placeholders}")
                
                if total_placeholders > 0:
                    logger.info(f"🎯 Batch resolving placeholders for {len(entity_ids)} entities")
                    
                    # Use batch resolution to avoid database deadlocks
                    placeholders_resolved = PlaceholderManager.batch_resolve_placeholders_for_table(
                        dataset_name, entity_ids, institution, base_uri
                    )
                    stats["placeholders_resolved"] += placeholders_resolved
                else:
                    logger.info(f"🔧 No placeholders to resolve")
            else:
                logger.info(f"🔧 No entity IDs found")
                        
        except Exception as e:
            logger.error(f"Error processing references and placeholders: {e}")
            stats["errors"] += 1
        
        logger.info(f"🔧 Finished _process_references_and_placeholders")
    
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