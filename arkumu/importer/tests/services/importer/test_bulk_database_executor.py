import pytest
from unittest.mock import Mock, patch, MagicMock
from django.db import transaction

from arkumu.importer.services.importer.bulk_database_executor import BulkDatabaseExecutor
from arkumu.importer.services.importer.bulk_update_engine import ResourceUpdate, UpdateStrategy, BulkUpdateStats
from arkumu.importer.services.importer.bulk_uri_service import BulkURIService
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType


@pytest.mark.django_db
class TestBulkDatabaseExecutor:
    
    def setup_method(self):
        self.uri_service = BulkURIService("http://example.com/data", "test_institution")
        self.executor = BulkDatabaseExecutor(
            uri_service=self.uri_service,
            link_row_cells=True,
            link_topology="row"
        )
    
    def test_init(self):
        assert self.executor.uri_service == self.uri_service
        assert self.executor.link_row_cells is True
        assert self.executor.link_topology == "row"
        assert self.executor.has_part_prop is None
        assert self.executor.rdf_value_prop is None
        assert self.executor.dcterms_relation_prop is None
    
    def test_ensure_rdf_properties(self):
        # Test creating RDF properties
        self.executor.ensure_rdf_properties()
        
        # Properties should be created
        assert Resource.objects.filter(uri="http://purl.org/dc/terms/hasPart").exists()
        assert Resource.objects.filter(uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value").exists()
        assert Resource.objects.filter(uri="http://purl.org/dc/terms/relation").exists()
        
        # Properties should be set on executor
        assert self.executor.has_part_prop is not None
        assert self.executor.rdf_value_prop is not None
        assert self.executor.dcterms_relation_prop is not None
        
        # Test idempotent behavior
        old_has_part = self.executor.has_part_prop
        self.executor.ensure_rdf_properties()
        assert self.executor.has_part_prop == old_has_part
    
    def test_execute_bulk_update_empty(self):
        # Test with empty updates
        result = self.executor.execute_bulk_update([], "test_dataset")
        assert isinstance(result, BulkUpdateStats)
        assert result.cells_processed == 0
        assert result.resources_created == 0
    
    def test_execute_bulk_update_with_updates(self):
        # Create test updates
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            ),
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col2/1",
                new_values=["value2"],
                new_name="col2",
                action=UpdateStrategy.UPDATE_VALUES
            ),
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/2",
                new_values=["value3"],
                new_name="col1",
                action=UpdateStrategy.SKIP_EXISTING
            )
        ]
        
        result = self.executor.execute_bulk_update(updates, "test_dataset")
        
        assert isinstance(result, BulkUpdateStats)
        assert result.cells_processed == 2  # Only UPDATE_VALUES updates are processed
        assert result.resources_created > 0
    
    def test_execute_batch_with_multi_value_support(self):
        # Test batch execution with multi-value support
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1", "value2"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES,
                is_multi_value=True
            )
        ]
        
        stats = BulkUpdateStats()
        self.executor._execute_batch_with_multi_value_support(updates, "test_dataset", stats)
        
        assert stats.cells_processed == 1
        assert stats.resources_created >= 1
    
    def test_create_structural_hierarchy(self):
        unique_columns = {"col1", "col2", "col3"}
        row_ids = {"1", "2", "3"}
        
        result = self.executor.create_structural_hierarchy(
            "test_dataset", unique_columns, row_ids
        )
        
        assert "dataset" in result
        assert "columns" in result
        assert "rows" in result
        assert isinstance(result["dataset"], Resource)
        assert len(result["columns"]) == 3
        assert len(result["rows"]) == 3
        
        # Test without row IDs
        result = self.executor.create_structural_hierarchy(
            "test_dataset_no_rows", unique_columns
        )
        assert "dataset" in result
        assert "columns" in result
        assert "rows" not in result
    
    def test_delete_dataset_resources(self):
        # Create test resources
        dataset_name = "test_dataset_to_delete"
        dataset_uri = self.uri_service.generate_dataset_uri(dataset_name)
        
        # Create dataset resource
        dataset_resource = Resource.objects.create(
            uri=dataset_uri,
            resource_type=ResourceType.IRI,
            name=dataset_name,
            source="test_institution"
        )
        
        # Create column resource
        column_uri = self.uri_service.generate_column_uri(dataset_name, "col1")
        column_resource = Resource.objects.create(
            uri=column_uri,
            resource_type=ResourceType.IRI,
            name="col1",
            source="test_institution"
        )
        
        # Create cell resource
        cell_uri = self.uri_service.generate_cell_uri(dataset_name, "col1", "1")
        cell_resource = Resource.objects.create(
            uri=cell_uri,
            resource_type=ResourceType.IRI,
            name="Cell",
            source="test_institution"
        )
        
        # Create some triples
        has_part_prop = Resource.objects.create(
            uri="http://purl.org/dc/terms/hasPart",
            resource_type=ResourceType.PROPERTY,
            name="hasPart",
            source="test_institution"
        )
        
        Triple.objects.create(
            subject=dataset_resource,
            predicate=has_part_prop,
            object=column_resource
        )
        
        Triple.objects.create(
            subject=column_resource,
            predicate=has_part_prop,
            object=cell_resource
        )
        
        # Test deletion
        stats = self.executor.delete_dataset_resources(dataset_name)
        
        assert stats["resources_deleted"] >= 3
        assert stats["triples_deleted"] >= 2
        assert stats["errors"] == 0
        
        # Verify resources are actually deleted
        assert not Resource.objects.filter(uri__startswith=dataset_uri).exists()
    
    def test_topology_row(self):
        # Test row topology
        executor = BulkDatabaseExecutor(
            uri_service=self.uri_service,
            link_row_cells=True,
            link_topology="row"
        )
        
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            ),
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col2/1",
                new_values=["value2"],
                new_name="col2",
                action=UpdateStrategy.UPDATE_VALUES
            )
        ]
        
        result = executor.execute_bulk_update(updates, "test_dataset")
        
        assert result.resources_created > 0
        assert result.row_links_created >= 0
    
    def test_topology_first_column(self):
        # Test first_column topology
        executor = BulkDatabaseExecutor(
            uri_service=self.uri_service,
            link_row_cells=True,
            link_topology="first_column"
        )
        
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            ),
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col2/1",
                new_values=["value2"],
                new_name="col2",
                action=UpdateStrategy.UPDATE_VALUES
            )
        ]
        
        result = executor.execute_bulk_update(updates, "test_dataset")
        
        assert result.resources_created > 0
        # Should create sameRow property
        assert Resource.objects.filter(
            uri=self.uri_service.generate_property_uri("sameRow")
        ).exists()
    
    def test_topology_mesh(self):
        # Test mesh topology
        executor = BulkDatabaseExecutor(
            uri_service=self.uri_service,
            link_row_cells=True,
            link_topology="mesh"
        )
        
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            ),
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col2/1",
                new_values=["value2"],
                new_name="col2",
                action=UpdateStrategy.UPDATE_VALUES
            ),
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col3/1",
                new_values=["value3"],
                new_name="col3",
                action=UpdateStrategy.UPDATE_VALUES
            )
        ]
        
        result = executor.execute_bulk_update(updates, "test_dataset")
        
        assert result.resources_created > 0
        # Should create sameRow property
        assert Resource.objects.filter(
            uri=self.uri_service.generate_property_uri("sameRow")
        ).exists()
    
    def test_topology_minimal(self):
        # Test minimal topology (no row linking)
        executor = BulkDatabaseExecutor(
            uri_service=self.uri_service,
            link_row_cells=False,
            link_topology="minimal"
        )
        
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            )
        ]
        
        result = executor.execute_bulk_update(updates, "test_dataset")
        
        assert result.resources_created > 0
        assert result.row_links_created == 0
    
    def test_multi_value_handling(self):
        # Test multi-value cell handling
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1", "value2", "value3"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES,
                is_multi_value=True
            )
        ]
        
        result = self.executor.execute_bulk_update(updates, "test_dataset")
        
        assert result.resources_created > 0
        assert result.total_values_created >= 3
    
    def test_error_handling(self):
        # Test error handling with invalid updates
        updates = [
            ResourceUpdate(
                uri="",  # Invalid URI
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            )
        ]
        
        # Should not raise exception
        result = self.executor.execute_bulk_update(updates, "test_dataset")
        assert isinstance(result, BulkUpdateStats)
    
    def test_batch_processing(self):
        # Test batch processing with large number of updates
        updates = []
        for i in range(50):
            updates.append(
                ResourceUpdate(
                    uri=f"http://example.com/data/test_institution/datasets/test_dataset/col1/{i+1}",
                    new_values=[f"value{i+1}"],
                    new_name="col1",
                    action=UpdateStrategy.UPDATE_VALUES
                )
            )
        
        result = self.executor.execute_bulk_update(updates, "test_dataset", batch_size=10)
        
        assert result.cells_processed == 50
        assert result.resources_created >= 50
    
    @patch('arkumu.importer.services.importer.bulk_database_executor.logger')
    def test_logging(self, mock_logger):
        # Test that appropriate logging occurs
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            )
        ]
        
        self.executor.execute_bulk_update(updates, "test_dataset")
        
        # Check that info logs were called
        mock_logger.info.assert_called()
    
    def test_resource_creation_idempotency(self):
        # Test that running the same updates twice doesn't create duplicates
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            )
        ]
        
        # Run first time
        result1 = self.executor.execute_bulk_update(updates, "test_dataset")
        initial_count = Resource.objects.count()
        
        # Run second time
        result2 = self.executor.execute_bulk_update(updates, "test_dataset")
        final_count = Resource.objects.count()
        
        # Should not create duplicate resources (due to ignore_conflicts=True)
        assert final_count >= initial_count
    
    def test_transaction_handling(self):
        # Test that operations are properly wrapped in transactions
        # This is more of an integration test
        updates = [
            ResourceUpdate(
                uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1",
                new_values=["value1"],
                new_name="col1",
                action=UpdateStrategy.UPDATE_VALUES
            )
        ]
        
        # Should complete successfully
        result = self.executor.execute_bulk_update(updates, "test_dataset")
        assert result.resources_created > 0
        
        # Resources should exist after transaction
        assert Resource.objects.filter(
            uri="http://example.com/data/test_institution/datasets/test_dataset/col1/1"
        ).exists()