import pytest
import os
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
import polars as pl

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.importer.bulk_update_engine import UpdateStrategy


@pytest.mark.django_db
class TestImportWorkflowService:
    
    def setup_method(self):
        self.workflow = ImportWorkflowService()
        
        # Create temporary CSV file for testing
        self.temp_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        self.temp_csv.write("id;name;value\n1;Item1;10\n2;Item2;20\n3;Item3;30\n")
        self.temp_csv.close()
        
        # Create temporary directory with CSV files
        self.temp_dir = tempfile.mkdtemp()
        
        # Create test CSV files in the directory
        with open(os.path.join(self.temp_dir, 'test1.csv'), 'w') as f:
            f.write("id;name;description\n1;Test1;Description1\n2;Test2;Description2\n")
        
        with open(os.path.join(self.temp_dir, 'test2.csv'), 'w') as f:
            f.write("id;category;status\n1;Cat1;Active\n2;Cat2;Inactive\n")
    
    def teardown_method(self):
        # Clean up temp files
        if os.path.exists(self.temp_csv.name):
            os.unlink(self.temp_csv.name)
        
        # Clean up temp directory
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_init(self):
        assert self.workflow.file_handler is not None
        assert self.workflow.data_analyzer is not None
        assert self.workflow.uri_service is None  # Initialized per import
        assert self.workflow.update_engine is not None
        assert self.workflow.database_executor is None  # Initialized per import with uri_service
        assert self.workflow.relationship_processor is None  # Initialized per import with uri_service
    
    @patch('arkumu.importer.services.importer.import_workflow.ServiceFactory')
    def test_import_csv_with_table_services(self, mock_service_factory):
        # Mock the service factory and its services
        mock_factory = Mock()
        mock_service_factory.return_value = mock_factory
        
        mock_table_analysis = Mock()
        mock_mapping_config = Mock()
        mock_processing_pipeline = Mock()
        
        mock_factory.get_table_analysis_service.return_value = mock_table_analysis
        mock_factory.get_mapping_configuration_service.return_value = mock_mapping_config
        mock_factory.get_processing_pipeline_service.return_value = mock_processing_pipeline
        
        # Mock analysis results
        mock_analysis = Mock()
        mock_analysis.row_count = 3
        mock_analysis.column_count = 3
        mock_analysis.quality_score = 0.95
        mock_analysis.suggested_mappings = [
            {'column_name': 'name', 'semantic_hint': 'label', 'target_type': 'rdfs:label'}
        ]
        mock_analysis.institutional_prefixes = []
        mock_analysis.discovered_patterns = {'naming_conventions': []}
        mock_analysis.foreign_key_candidates = []
        
        mock_table_analysis.analyze_csv.return_value = mock_analysis
        
        # Mock mapping configuration
        mock_pattern_rule = Mock()
        mock_mapping_rule = Mock()
        mock_mapping_config.create_pattern_rule.return_value = mock_pattern_rule
        mock_mapping_config.create_mapping_rule.return_value = mock_mapping_rule
        
        # Mock pipeline execution
        mock_processing_pipeline.execute_csv_transformation.return_value = {
            'status': 'success',
            'resources_created': 10,
            'triples_created': 25
        }
        
        result = ImportWorkflowService.import_csv_with_table_services(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset",
            institution="test_institution",
            auto_mapping=True
        )
        
        assert result["dataset_name"] == "test_dataset"
        assert result["import_approach"] == "table_based_services"
        assert result["analysis"]["row_count"] == 3
        assert result["analysis"]["column_count"] == 3
        assert result["analysis"]["quality_score"] == 0.95
        assert result["intelligent_mappings"] == 1
        assert "pipeline_execution" in result
    
    @patch('arkumu.importer.services.importer.import_workflow.ServiceFactory')
    def test_import_csv_with_table_services_fallback(self, mock_service_factory):
        # Mock ImportError to trigger fallback
        mock_service_factory.side_effect = ImportError("Service not available")
        
        with patch.object(ImportWorkflowService, 'import_csv') as mock_import_csv:
            mock_import_csv.return_value = {"status": "success"}
            
            result = ImportWorkflowService.import_csv_with_table_services(
                csv_path=self.temp_csv.name,
                dataset_name="test_dataset"
            )
            
            mock_import_csv.assert_called_once()
            assert result == {"status": "success"}
    
    def test_import_csv_basic(self):
        result = ImportWorkflowService.import_csv(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset",
            institution="test_institution",
            use_smart_updater=False
        )
        
        assert isinstance(result, dict)
        assert "rows_processed" in result
        assert "cells_processed" in result
        assert "resources_created" in result
        assert "triples_created" in result
    
    def test_import_csv_with_smart_updater(self):
        result = ImportWorkflowService.import_csv(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset",
            institution="test_institution",
            use_smart_updater=True,
            update_strategy=UpdateStrategy.UPDATE_VALUES
        )
        
        assert isinstance(result, dict)
        assert "dataset_name" in result
        assert "strategy_used" in result
        assert result["strategy_used"] == "update_values"
    
    def test_import_csv_with_table_services_flag(self):
        with patch.object(ImportWorkflowService, 'import_csv_with_table_services') as mock_table_services:
            mock_table_services.return_value = {"status": "success"}
            
            result = ImportWorkflowService.import_csv(
                csv_path=self.temp_csv.name,
                dataset_name="test_dataset",
                use_table_services=True
            )
            
            mock_table_services.assert_called_once()
            assert result == {"status": "success"}
    
    def test_import_csv_directory(self):
        result = ImportWorkflowService.import_csv_directory(
            directory_path=self.temp_dir,
            institution="test_institution",
            use_smart_updater=False
        )
        
        assert isinstance(result, dict)
        assert result["files_processed"] == 2
        assert "resources_created" in result
        assert "triples_created" in result
        assert result["errors"] == 0
    
    def test_import_csv_directory_with_relationship_config(self):
        # Create relationship config file
        relationship_config = {
            "test1": [
                {
                    "column": "category_id",
                    "target_table": "categories"
                }
            ]
        }
        
        config_file = os.path.join(self.temp_dir, "relationships.json")
        with open(config_file, 'w') as f:
            json.dump(relationship_config, f)
        
        result = ImportWorkflowService.import_csv_directory(
            directory_path=self.temp_dir,
            relationship_config_path=config_file,
            institution="test_institution"
        )
        
        assert isinstance(result, dict)
        assert result["files_processed"] == 2
    
    def test_import_csv_directory_nonexistent(self):
        result = ImportWorkflowService.import_csv_directory(
            directory_path="/nonexistent/path"
        )
        
        assert "error" in result
        assert "Directory not found" in result["error"]
    
    def test_import_csv_directory_no_csv_files(self):
        empty_dir = tempfile.mkdtemp()
        try:
            result = ImportWorkflowService.import_csv_directory(
                directory_path=empty_dir
            )
            
            assert "error" in result
            assert "No CSV files found" in result["error"]
        finally:
            os.rmdir(empty_dir)
    
    def test_import_csv_with_smart_updates(self):
        result = ImportWorkflowService.import_csv_with_smart_updates(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset",
            institution="test_institution",
            update_strategy=UpdateStrategy.UPDATE_VALUES,
            analyze_first=True
        )
        
        assert isinstance(result, dict)
        assert result["dataset_name"] == "test_dataset"
        assert result["strategy_used"] == "update_values"
        assert "rows_in_csv" in result
        assert "stats" in result
        assert result["rows_in_csv"] == 3
    
    def test_import_csv_with_smart_updates_no_analysis(self):
        result = ImportWorkflowService.import_csv_with_smart_updates(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset",
            institution="test_institution",
            analyze_first=False
        )
        
        assert isinstance(result, dict)
        assert "analysis" not in result
        assert "stats" in result
    
    def test_process_csv_import(self):
        result = ImportWorkflowService._process_csv_import(
            file_path=self.temp_csv.name,
            dataset_name="test_dataset",
            institution="test_institution"
        )
        
        assert isinstance(result, dict)
        assert "rows_processed" in result
        assert "cells_processed" in result
        assert "resources_created" in result
        assert "triples_created" in result
    
    def test_import_relationship_csv(self):
        # Create a relationship CSV
        relationship_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        relationship_csv.write("id;author_id;publisher_id\n1;101;201\n2;102;202\n")
        relationship_csv.close()
        
        try:
            relationship_config = [
                {"column": "author_id", "target_table": "authors"},
                {"column": "publisher_id", "target_table": "publishers"}
            ]
            
            result = ImportWorkflowService._import_relationship_csv(
                csv_path=relationship_csv.name,
                dataset_name="books",
                relationship_config=relationship_config,
                institution="test_institution"
            )
            
            assert isinstance(result, dict)
            assert "relationships_created" in result
            assert "resources_created" in result
            assert "triples_created" in result
            
        finally:
            os.unlink(relationship_csv.name)
    
    def test_dataset_name_auto_detection(self):
        # Test auto-detection of dataset name from file path
        result = ImportWorkflowService.import_csv(
            csv_path=self.temp_csv.name,
            dataset_name=None,  # Should auto-detect
            institution="test_institution",
            use_smart_updater=False
        )
        
        # The dataset name should be derived from the temp file name
        assert isinstance(result, dict)
    
    def test_import_with_file_columns(self):
        result = ImportWorkflowService.import_csv(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset",
            institution="test_institution",
            file_columns=["attachment"],
            files_base_directory=self.temp_dir,
            upload_service=Mock(),
            use_smart_updater=False
        )
        
        assert isinstance(result, dict)
        assert "files_uploaded" in result or "upload_errors" in result
    
    def test_import_with_link_options(self):
        # Test different link options
        result1 = ImportWorkflowService.import_csv(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset1",
            institution="test_institution",
            link_row_cells=True,
            link_to_first_column=False,
            use_smart_updater=False
        )
        
        result2 = ImportWorkflowService.import_csv(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset2",
            institution="test_institution",
            link_row_cells=True,
            link_to_first_column=True,
            use_smart_updater=False
        )
        
        assert isinstance(result1, dict)
        assert isinstance(result2, dict)
    
    def test_error_handling_invalid_csv(self):
        # Create invalid CSV file
        invalid_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        invalid_csv.write("invalid csv content\nwith\ninconsistent\ncolumns")
        invalid_csv.close()
        
        try:
            with pytest.raises(Exception):
                ImportWorkflowService.import_csv(
                    csv_path=invalid_csv.name,
                    dataset_name="test_dataset",
                    institution="test_institution"
                )
        finally:
            os.unlink(invalid_csv.name)
    
    def test_error_handling_nonexistent_file(self):
        with pytest.raises(Exception):
            ImportWorkflowService.import_csv(
                csv_path="/nonexistent/file.csv",
                dataset_name="test_dataset",
                institution="test_institution"
            )
    
    def test_various_delimiters(self):
        # Test with comma delimiter
        comma_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        comma_csv.write("id,name,value\n1,Item1,10\n2,Item2,20\n")
        comma_csv.close()
        
        try:
            result = ImportWorkflowService.import_csv(
                csv_path=comma_csv.name,
                dataset_name="test_dataset",
                institution="test_institution",
                delimiter=',',
                use_smart_updater=False
            )
            
            assert isinstance(result, dict)
            
        finally:
            os.unlink(comma_csv.name)
    
    def test_quoted_fields(self):
        # Test with quoted fields
        quoted_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        quoted_csv.write('"id";"name";"description"\n"1";"Item 1";"A description with; semicolons"\n')
        quoted_csv.close()
        
        try:
            result = ImportWorkflowService.import_csv(
                csv_path=quoted_csv.name,
                dataset_name="test_dataset",
                institution="test_institution",
                has_quoted_fields=True,
                use_smart_updater=False
            )
            
            assert isinstance(result, dict)
            
        finally:
            os.unlink(quoted_csv.name)
    
    @patch('arkumu.importer.services.importer.import_workflow.logger')
    def test_logging(self, mock_logger):
        ImportWorkflowService.import_csv(
            csv_path=self.temp_csv.name,
            dataset_name="test_dataset",
            institution="test_institution",
            use_smart_updater=False
        )
        
        # Check that info logs were called
        mock_logger.info.assert_called()
    
    def test_update_strategy_conversion(self):
        # Test different update strategies
        strategies = [
            UpdateStrategy.SKIP_EXISTING,
            UpdateStrategy.UPDATE_VALUES,
            UpdateStrategy.MERGE_TRIPLES,
            UpdateStrategy.REPLACE_ALL,
            UpdateStrategy.TIMESTAMP_BASED
        ]
        
        for strategy in strategies:
            result = ImportWorkflowService.import_csv_with_smart_updates(
                csv_path=self.temp_csv.name,
                dataset_name=f"test_dataset_{strategy.value}",
                institution="test_institution",
                update_strategy=strategy,
                analyze_first=False
            )
            
            assert isinstance(result, dict)
            assert result["strategy_used"] == strategy.value
    
    def test_workflow_service_initialization(self):
        # Test that workflow service initializes all required components
        workflow = ImportWorkflowService()
        
        assert workflow.file_handler is not None
        assert workflow.data_analyzer is not None
        assert workflow.update_engine is not None
        assert workflow.database_executor is None  # Initialized per import
        assert workflow.relationship_processor is None  # Initialized per import
    
    def test_large_csv_handling(self):
        # Create a larger CSV file for testing
        large_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        large_csv.write("id;name;value;description\n")
        
        for i in range(100):
            large_csv.write(f"{i};Item{i};{i*10};Description for item {i}\n")
        
        large_csv.close()
        
        try:
            result = ImportWorkflowService.import_csv(
                csv_path=large_csv.name,
                dataset_name="large_dataset",
                institution="test_institution",
                use_smart_updater=False
            )
            
            assert isinstance(result, dict)
            assert result.get("rows_processed", 0) == 100
            
        finally:
            os.unlink(large_csv.name)
    
    def test_empty_csv_handling(self):
        # Test with empty CSV
        empty_csv = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        empty_csv.write("id;name;value\n")  # Headers only
        empty_csv.close()
        
        try:
            result = ImportWorkflowService.import_csv(
                csv_path=empty_csv.name,
                dataset_name="empty_dataset",
                institution="test_institution",
                use_smart_updater=False
            )
            
            assert isinstance(result, dict)
            
        finally:
            os.unlink(empty_csv.name)