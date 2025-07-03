import os
import logging
from typing import Dict, List, Any, Optional

import csv
from arkumu.importer.services.importer.file_handler import FileHandler
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars as SmartBulkUpdater, UpdateStrategy, FKRelationship

logger = logging.getLogger(__name__)

class ImportWorkflowService:
    """
    Main orchestration service for CSV import workflow.
    Supports both fast bulk import (default) and smart bulk updates (for existing data).
    """
    
    def __init__(self):
        self.file_handler = FileHandler()
        self.smart_updater = SmartBulkUpdater()
    
    @staticmethod
    def import_csv_with_table_services(
        csv_path: str,
        dataset_name: Optional[str] = None,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        auto_mapping: bool = True,
        session_dict: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Import a CSV file using the table-based service architecture.
        This is the modern approach that works well with the bulk editor services.
        
        Args:
            csv_path: Path to the CSV file
            dataset_name: Name for the dataset
            institution: Institution code
            base_uri: Base URI for generated resources
            delimiter: CSV column delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            auto_mapping: Whether to automatically apply intelligent mappings
            session_dict: Session dictionary for service state (can be empty dict)
            
        Returns:
            Dict with import statistics and analysis
        """
        logger.info(f"🚀 Starting table-based service import of CSV file: {csv_path}")
        logger.info(f"   Dataset: {dataset_name}")
        logger.info(f"   Institution: {institution}")
        logger.info(f"   Auto-mapping: {auto_mapping}")
        
        if not dataset_name:
            dataset_name = os.path.splitext(os.path.basename(csv_path))[0]
            logger.info(f"   Auto-detected dataset name: {dataset_name}")
        
        if session_dict is None:
            session_dict = {}
        
        try:
            # Import the service factory
            from arkumu.metadata.services.metadata_models_mapping import ServiceFactory
            
            # Get the enhanced services
            service_factory = ServiceFactory()
            table_analysis_service = service_factory.get_table_analysis_service()
            mapping_config_service = service_factory.get_mapping_configuration_service(session_dict)
            processing_pipeline = service_factory.get_processing_pipeline_service(session_dict)
            
            logger.info(f"🔍 Step 1: Analyzing CSV structure...")
            
            # Analyze the CSV file structure
            analysis = table_analysis_service.analyze_csv(csv_path)
            
            logger.info(f"   📊 Analysis complete: {analysis.row_count} rows, {analysis.column_count} columns")
            logger.info(f"   🎯 Found {len(analysis.suggested_mappings)} mapping suggestions")
            logger.info(f"   📈 Quality score: {analysis.quality_score}")
            
            result = {
                "dataset_name": dataset_name,
                "import_approach": "table_based_services",
                "analysis": {
                    "row_count": analysis.row_count,
                    "column_count": analysis.column_count,
                    "quality_score": analysis.quality_score,
                    "suggested_mappings": len(analysis.suggested_mappings),
                    "institutional_prefixes": analysis.institutional_prefixes,
                    "discovered_patterns": len(analysis.discovered_patterns.get('naming_conventions', [])),
                    "foreign_key_candidates": len(analysis.foreign_key_candidates)
                }
            }
            
            # Apply intelligent mappings if requested
            if auto_mapping and analysis.suggested_mappings:
                logger.info(f"⚙️ Step 2: Applying intelligent mappings...")
                
                # Create mapping rules from analysis
                mapping_rules = []
                for mapping in analysis.suggested_mappings:
                    try:
                        # Create pattern rule
                        pattern_rule = mapping_config_service.create_pattern_rule(
                            name=f"Auto-{mapping['semantic_hint']}",
                            pattern_type=mapping.get('pattern_type', 'prefix'),
                            pattern_value=mapping.get('pattern_value', ''),
                            target_fields=['uri', 'name'],
                            description=f"Auto-generated from column '{mapping['column_name']}'"
                        )
                        
                        # Create mapping rule
                        mapping_rule = mapping_config_service.create_mapping_rule(
                            name=f"{mapping['column_name']} → {mapping['target_type']}",
                            pattern_rule=pattern_rule,
                            mapping_type='type_assignment',
                            target_semantic_type=mapping['target_type'],
                            priority=int(mapping.get('confidence', 50))
                        )
                        
                        mapping_rules.append(mapping_rule)
                        
                    except Exception as e:
                        logger.warning(f"Could not create mapping for {mapping}: {e}")
                
                logger.info(f"   ✅ Created {len(mapping_rules)} intelligent mapping rules")
                result["intelligent_mappings"] = len(mapping_rules)
            else:
                logger.info(f"⏭️ Step 2: Skipping intelligent mappings (auto_mapping={auto_mapping})")
                result["intelligent_mappings"] = 0
            
            logger.info(f"🚀 Step 3: Executing table-based transformation...")
            
            # Use ProcessingPipelineService for coordinated execution
            pipeline_result = processing_pipeline.execute_csv_transformation(
                csv_path=csv_path,
                dataset_name=dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields
            )
            
            result["pipeline_execution"] = pipeline_result
            
            logger.info(f"✅ Table-based service import completed successfully!")
            logger.info(f"📊 Results: analysis quality {analysis.quality_score:.2f}, "
                       f"{result.get('intelligent_mappings', 0)} auto-mappings applied")
            
            return result
            
        except ImportError as e:
            logger.error(f"Service architecture not available: {e}")
            logger.info(f"🔄 Falling back to traditional cell-based import...")
            
            # Fallback to the traditional approach
            return ImportWorkflowService.import_csv(
                csv_path=csv_path,
                dataset_name=dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                use_smart_updater=False
            )
            
        except Exception as e:
            logger.error(f"❌ Error in table-based import {csv_path}: {e}")
            raise
    
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
        upload_service = None,
        link_row_cells: bool = True,
        link_to_first_column: bool = False,
        use_smart_updater: bool = False,
        use_polars: bool = False,
        update_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
        timestamp_column: Optional[str] = None,
        use_table_services: bool = False
    ) -> Dict[str, Any]:
        """
        Import a single CSV file.
        
        Args:
            csv_path: Path to the CSV file
            dataset_name: Name for the dataset
            institution: Institution code
            base_uri: Base URI for generated resources
            delimiter: CSV column delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            file_columns: List of file column names
            files_base_directory: Base directory for file uploads
            upload_service: Service for uploading files
            link_row_cells: Whether to create links between cells in the same row
            link_to_first_column: If True, use the first column as the anchor for row links
            use_smart_updater: If True, use smart bulk updater (slower but handles existing data)
            use_polars: If True, use Polars version for processing
            update_strategy: Strategy for handling existing data (only used if use_smart_updater=True)
            timestamp_column: Column name for timestamp-based updates (only used if use_smart_updater=True)
            use_table_services: If True, use the modern table-based service architecture
            
        Returns:
            Dict with import statistics
        """
        logger.info(f"🚀 Starting import of CSV file: {csv_path}")
        logger.info(f"   Dataset: {dataset_name}")
        logger.info(f"   Institution: {institution}")
        logger.info(f"   Link row cells: {link_row_cells}")
        logger.info(f"   Link to first column: {link_to_first_column}")
        logger.info(f"   Use smart updater: {use_smart_updater}")
        logger.info(f"   Use table services: {use_table_services}")
        
        if not dataset_name:
            dataset_name = os.path.splitext(os.path.basename(csv_path))[0]
            logger.info(f"   Auto-detected dataset name: {dataset_name}")
        
        try:
            # Route to table-based services if requested
            if use_table_services:
                logger.info(f"📋 Using modern table-based service architecture")
                return ImportWorkflowService.import_csv_with_table_services(
                    csv_path=csv_path,
                    dataset_name=dataset_name,
                    institution=institution,
                    base_uri=base_uri,
                    delimiter=delimiter,
                    has_quoted_fields=has_quoted_fields,
                    auto_mapping=True
                )
            
            # Route to appropriate importer based on flags  
            elif use_smart_updater:
                logger.info(f"📋 Using smart bulk updater for existing data handling")
                return ImportWorkflowService.import_csv_with_smart_updates(
                    csv_path=csv_path,
                    dataset_name=dataset_name,
                    institution=institution,
                    base_uri=base_uri,
                    delimiter=delimiter,
                    has_quoted_fields=has_quoted_fields,
                    update_strategy=update_strategy,
                    timestamp_column=timestamp_column,
                    analyze_first=True,
                    use_polars=use_polars
                )
            else:
                # Default: Use fast bulk import (cell-based - legacy)
                logger.info(f"📋 Using legacy cell-based bulk import")
                stats = ImportWorkflowService._process_csv_import(
                    csv_path,
                    dataset_name,
                    institution=institution,
                    base_uri=base_uri,
                    delimiter=delimiter,
                    has_quoted_fields=has_quoted_fields,
                    file_columns=file_columns,
                    files_base_directory=files_base_directory,
                    upload_service=upload_service,
                    link_row_cells=link_row_cells,
                    link_to_first_column=link_to_first_column
                )
                
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
        upload_service=None,
        link_row_cells: bool = True,
        link_to_first_column: bool = False,
        use_smart_updater: bool = False,
        use_polars: bool = False,
        update_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
        timestamp_column: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Import all CSV files in a directory.
        Regular tables are processed with bulk import.
        Relationship tables (if configured) are processed to create explicit relationships.
        
        Args:
            directory_path: Path to directory containing CSV files
            institution: Institution code
            base_uri: Base URI for generated resources
            delimiter: CSV column delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            relationship_config_path: Path to JSON file with relationship configurations
            file_columns: Dict mapping dataset names to file column lists
            files_base_directory: Base directory for file uploads
            upload_service: Service for uploading files
            link_row_cells: Whether to create links between cells in the same row
            link_to_first_column: If True, use the first column as the anchor for row links
            use_smart_updater: If True, use smart bulk updater for all files
            use_polars: If True, use Polars version for processing
            update_strategy: Strategy for handling existing data (only used if use_smart_updater=True)
            timestamp_column: Column name for timestamp-based updates (only used if use_smart_updater=True)
            
        Returns:
            Dict with aggregate import statistics
        """
        logger.info(f" Starting directory import from: {directory_path}")
        logger.info(f"   Institution: {institution}")
        logger.info(f"   Base URI: {base_uri}")
        logger.info(f"   Link row cells: {link_row_cells}")
        logger.info(f"   Link to first column: {link_to_first_column}")
        logger.info(f"   Use smart updater: {use_smart_updater}")
        if use_smart_updater:
            logger.info(f"   Update strategy: {update_strategy.value}")
            if timestamp_column:
                logger.info(f"   Timestamp column: {timestamp_column}")
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
            "row_links_created": 0,
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
                    
                    # Import as regular table
                    file_stats = ImportWorkflowService.import_csv(
                        csv_path=csv_path,
                        dataset_name=dataset_name,
                        institution=institution,
                        base_uri=base_uri,
                        delimiter=delimiter,
                        has_quoted_fields=has_quoted_fields,
                        file_columns=dataset_file_columns,
                        files_base_directory=files_base_directory,
                        upload_service=upload_service,
                        link_row_cells=link_row_cells,
                        link_to_first_column=link_to_first_column,
                        use_smart_updater=use_smart_updater,
                        use_polars=use_polars,
                        update_strategy=update_strategy,
                        timestamp_column=timestamp_column
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
        if not use_smart_updater:
            logger.info(f"📊 Used fast bulk import - relationships can be processed in post-processing")
        else:
            logger.info(f"📊 Used smart bulk updater with {update_strategy.value} strategy")
        
        return aggregate_stats
    
    @staticmethod
    def import_csv_with_smart_updates(
        csv_path: str,
        dataset_name: Optional[str] = None,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        update_strategy: UpdateStrategy = UpdateStrategy.SKIP_EXISTING,
        timestamp_column: Optional[str] = None,
        analyze_first: bool = True,
        use_polars: bool = False
    ) -> Dict[str, Any]:
        """
        Import a CSV file with intelligent update handling.
        This method provides a more sophisticated approach to handling existing data.
        
        Args:
            csv_path: Path to the CSV file
            dataset_name: Name for the dataset
            institution: Institution code
            base_uri: Base URI for generated resources
            delimiter: CSV column delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            update_strategy: Strategy for handling existing data
            timestamp_column: Column name for timestamp-based updates
            analyze_first: Whether to perform analysis before import
            use_polars: If True, use Polars version for processing
            
        Returns:
            Dict with import statistics and analysis
        """
        logger.info(f"🚀 Starting smart import of CSV file: {csv_path}")
        logger.info(f"   Dataset: {dataset_name}")
        logger.info(f"   Institution: {institution}")
        logger.info(f"   Update strategy: {update_strategy.value}")
        
        if not dataset_name:
            dataset_name = os.path.splitext(os.path.basename(csv_path))[0]
            logger.info(f"   Auto-detected dataset name: {dataset_name}")
        
        try:
            # Initialize smart updater
            if use_polars:
                logger.info(f"🚀 Using Polars-optimized SmartBulkUpdaterPolars")
                smart_updater = SmartBulkUpdaterPolars(
                    default_strategy=update_strategy,
                    timestamp_column=timestamp_column,
                    institution=institution,
                    base_uri=base_uri
                )
            else:
                logger.info(f"🚀 Using original SmartBulkUpdater")
                smart_updater = SmartBulkUpdater(
                    default_strategy=update_strategy,
                    timestamp_column=timestamp_column,
                    institution=institution,
                    base_uri=base_uri
                )
            
            # Read CSV data
            import csv
            csv_data = []
            with open(csv_path, newline='', encoding='utf-8') as f:
                quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
                reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
                csv_data = list(reader)
            
            logger.info(f"📊 Loaded {len(csv_data)} rows from CSV")
            
            result = {
                "dataset_name": dataset_name,
                "rows_in_csv": len(csv_data),
                "strategy_used": update_strategy.value
            }
            
            # Perform analysis if requested
            if analyze_first:
                logger.info(f"🔍 Analyzing dataset changes...")
                analysis = smart_updater.analyze_dataset_changes(dataset_name, csv_data)
                result["analysis"] = analysis
                
                logger.info(f"📋 Analysis results:")
                logger.info(f"   Total rows: {analysis['total_rows']}")
                logger.info(f"   New resources: {analysis['new_resources']}")
                logger.info(f"   Existing resources: {analysis['existing_resources']}")
                logger.info(f"   Potential updates: {analysis['potential_updates']}")
                
                if analysis["recommendations"]:
                    logger.info(f"💡 Recommendations:")
                    for rec in analysis["recommendations"]:
                        logger.info(f"   - {rec}")
                
                # Auto-adjust strategy based on analysis
                if (update_strategy == UpdateStrategy.SKIP_EXISTING and 
                    analysis["potential_updates"] > 0):
                    logger.warning(f"⚠️ Found {analysis['potential_updates']} potential updates, "
                                 f"but strategy is SKIP_EXISTING. Consider using UPDATE_VALUES.")
            
            # Execute the import
            logger.info(f"🔧 Executing smart bulk import...")
            stats = smart_updater.import_csv_with_smart_updates(
                csv_data, dataset_name, update_strategy
            )
            
            # Convert stats to dict for consistent return format
            result["stats"] = {
                "rows_processed": stats.rows_processed,
                "cells_processed": stats.cells_processed,
                "resources_created": stats.resources_created,
                "resources_updated": stats.resources_updated,
                "resources_skipped": stats.resources_skipped,
                "triples_created": stats.triples_created,
                "triples_updated": stats.triples_updated,
                "triples_skipped": stats.triples_skipped,
                "errors": stats.errors
            }
            
            logger.info(f"✅ Smart import completed successfully!")
            logger.info(f"📊 Results: {stats.resources_created} created, "
                       f"{stats.resources_updated} updated, {stats.resources_skipped} skipped")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in smart import {csv_path}: {e}")
            raise
    
    @staticmethod
    def _process_csv_import(
        file_path: str,
        dataset_name: str,
        institution: str = "DEFAULT",
        base_uri: str = "http://arkumu.org/data",
        delimiter: str = ';',
        has_quoted_fields: bool = False,
        file_columns: List[str] = None,
        files_base_directory: str = None,
        upload_service = None,
        link_row_cells: bool = True,
        link_to_first_column: bool = False
    ) -> Dict[str, Any]:
        """
        Process a CSV file import with cell creation and row linking.
        """
        logger.info(f"🔧 Starting CSV import processing for {file_path}")
        
        # First, perform regular CSV import
        logger.info(f"🔧 Step 1: Calling import_csv_as_cells for {dataset_name}")
        logger.info(f"   📁 File path: {file_path}")
        logger.info(f"   🏛️ Institution: {institution}")
        logger.info(f"   🌐 Base URI: {base_uri}")
        logger.info(f"   📊 Delimiter: '{delimiter}'")
        logger.info(f"   📝 Has quoted fields: {has_quoted_fields}")
        logger.info(f"   🔗 Link row cells: {link_row_cells}")
        logger.info(f"   🔗 Link to first column: {link_to_first_column}")
        
        # Use SmartBulkUpdaterPolars instead of import_csv_as_cells
        updater = SmartBulkUpdater(
            default_strategy=UpdateStrategy.UPDATE_VALUES,
            institution=institution,
            base_uri=base_uri,
            link_row_cells=link_row_cells,
            link_topology="first_column" if link_to_first_column else "row"
        )
        
        # Read CSV data
        csv_data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
            reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
            csv_data = list(reader)
        
        # Process with SmartBulkUpdaterPolars
        bulk_stats = updater.import_csv_with_smart_updates(csv_data, dataset_name)
        
        # Convert BulkUpdateStats to dict format expected by import_workflow
        stats = {
            "rows_processed": bulk_stats.rows_processed,
            "cells_processed": bulk_stats.cells_processed,
            "resources_created": bulk_stats.resources_created,
            "triples_created": bulk_stats.triples_created,
            "row_links_created": bulk_stats.row_links_created,
            "errors": bulk_stats.errors,
            "truncated_values": bulk_stats.truncated_values
        }
        
        logger.info(f"✅ Step 1 completed: import_csv_as_cells finished")
        logger.info(f"   📊 Rows processed: {stats.get('rows_processed', 0)}")
        logger.info(f"   📊 Cells processed: {stats.get('cells_processed', 0)}")
        logger.info(f"   📊 Resources created: {stats.get('resources_created', 0)}")
        logger.info(f"   📊 Triples created: {stats.get('triples_created', 0)}")
        logger.info(f"   📊 Row links created: {stats.get('row_links_created', 0)}")
        logger.info(f"   📊 Errors: {stats.get('errors', 0)}")
        logger.info(f"   📊 Truncated values: {stats.get('truncated_values', 0)}")
        
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
        
        logger.info(f"🔧 CSV import processing completed for {file_path}")
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
        Import a relationship CSV file using SmartBulkUpdaterPolars FK processing.
        """
        logger.info(f"🔗 Starting relationship CSV import for {dataset_name}")
        logger.info(f"   📁 File path: {csv_path}")
        logger.info(f"   🏛️ Institution: {institution}")
        logger.info(f"   🌐 Base URI: {base_uri}")
        logger.info(f"   📊 Delimiter: '{delimiter}'")
        logger.info(f"   📝 Has quoted fields: {has_quoted_fields}")
        
        # Convert relationship config to FKRelationship objects
        fk_relationships = []
        for rel_config in relationship_config:
            fk_relationships.append(FKRelationship(
                source_column=rel_config["column"],
                source_dataset=dataset_name,
                target_column="id",  # Assume 'id' column for target
                target_dataset=rel_config["target_table"],
                relationship_type="relation"
            ))
        
        logger.info(f"🔗 Configured FK relationships: {len(fk_relationships)} relationships")
        for i, fk_rel in enumerate(fk_relationships, 1):
            logger.info(f"   {i}. Column '{fk_rel.source_column}' → {fk_rel.target_dataset}.{fk_rel.target_column}")
        
        # Use SmartBulkUpdaterPolars for relationship processing
        updater = SmartBulkUpdater(
            default_strategy=UpdateStrategy.UPDATE_VALUES,
            institution=institution,
            base_uri=base_uri,
            fk_relationships=fk_relationships
        )
        
        # Read CSV data
        csv_data = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
            reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
            csv_data = list(reader)
        
        # Process the relationship CSV with regular import first
        bulk_stats = updater.import_csv_with_smart_updates(csv_data, dataset_name)
        
        # Process FK relationships
        datasets = {dataset_name: csv_data}
        fk_stats = updater.process_fk_relationships(datasets)
        
        # Convert to expected dict format
        stats = {
            "rows_processed": bulk_stats.rows_processed,
            "cells_processed": bulk_stats.cells_processed,
            "resources_created": bulk_stats.resources_created + fk_stats.resources_created,
            "triples_created": bulk_stats.triples_created + fk_stats.triples_created,
            "relationships_created": fk_stats.relationships_created,
            "errors": bulk_stats.errors + fk_stats.errors,
            "truncated_values": bulk_stats.truncated_values + fk_stats.truncated_values,
            "row_links_created": bulk_stats.row_links_created
        }
        
        logger.info(f"✅ Relationship CSV import completed for {dataset_name}")
        logger.info(f"   📊 Rows processed: {stats.get('rows_processed', 0)}")
        logger.info(f"   📊 Relationships created: {stats.get('relationships_created', 0)}")
        logger.info(f"   📊 Resources created: {stats.get('resources_created', 0)}")
        logger.info(f"   📊 Triples created: {stats.get('triples_created', 0)}")
        logger.info(f"   📊 Errors: {stats.get('errors', 0)}")
        logger.info(f"   📊 Truncated values: {stats.get('truncated_values', 0)}")
        
        # Ensure all expected stats are present for backward compatibility
        if "placeholders_created" not in stats:
            stats["placeholders_created"] = 0
        if "placeholders_resolved" not in stats:
            stats["placeholders_resolved"] = 0
        if "files_uploaded" not in stats:
            stats["files_uploaded"] = 0
        if "upload_errors" not in stats:
            stats["upload_errors"] = 0
        
        return stats