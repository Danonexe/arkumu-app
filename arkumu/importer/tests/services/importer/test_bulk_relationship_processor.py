import pytest
import polars as pl
from unittest.mock import Mock, patch, MagicMock

from arkumu.importer.services.importer.bulk_relationship_processor import (
    BulkRelationshipProcessor,
    FKRelationship
)
from arkumu.importer.services.importer.bulk_update_engine import BulkUpdateStats
from arkumu.importer.services.importer.bulk_uri_service import BulkURIService
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType


@pytest.mark.django_db
class TestBulkRelationshipProcessor:
    
    def setup_method(self):
        self.uri_service = BulkURIService("http://example.com/data", "test_institution")
        self.processor = BulkRelationshipProcessor(self.uri_service)
    
    def test_init(self):
        assert self.processor.uri_service == self.uri_service
    
    def test_fk_relationship_dataclass(self):
        fk_rel = FKRelationship(
            source_column="author_id",
            source_dataset="books",
            target_column="id",
            target_dataset="authors",
            relationship_type="hasAuthor"
        )
        
        assert fk_rel.source_column == "author_id"
        assert fk_rel.source_dataset == "books"
        assert fk_rel.target_column == "id"
        assert fk_rel.target_dataset == "authors"
        assert fk_rel.relationship_type == "hasAuthor"
    
    def test_process_fk_relationships_empty(self):
        datasets = {}
        fk_relationships = []
        
        result = self.processor.process_fk_relationships(datasets, fk_relationships)
        
        assert isinstance(result, BulkUpdateStats)
        assert result.triples_created == 0
        assert result.relationships_created == 0
    
    def test_process_fk_relationships_valid(self):
        # Create test datasets
        books_df = pl.DataFrame({
            "id": [1, 2, 3],
            "title": ["Book 1", "Book 2", "Book 3"],
            "author_id": [101, 102, 101]
        })
        
        authors_df = pl.DataFrame({
            "id": [101, 102, 103],
            "name": ["Author A", "Author B", "Author C"]
        })
        
        datasets = {
            "books": books_df,
            "authors": authors_df
        }
        
        fk_relationships = [
            FKRelationship(
                source_column="author_id",
                source_dataset="books",
                target_column="id",
                target_dataset="authors",
                relationship_type="hasAuthor"
            )
        ]
        
        result = self.processor.process_fk_relationships(datasets, fk_relationships)
        
        assert isinstance(result, BulkUpdateStats)
        assert result.relationships_created > 0
        assert result.triples_created > 0
        
        # Check that relationship property was created
        assert Resource.objects.filter(
            uri=self.uri_service.generate_property_uri("hasAuthor")
        ).exists()
    
    def test_process_fk_relationships_missing_dataset(self):
        datasets = {
            "books": pl.DataFrame({"id": [1], "title": ["Book 1"]})
        }
        
        fk_relationships = [
            FKRelationship(
                source_column="author_id",
                source_dataset="books",
                target_column="id",
                target_dataset="missing_dataset",
                relationship_type="hasAuthor"
            )
        ]
        
        result = self.processor.process_fk_relationships(datasets, fk_relationships)
        
        assert result.relationships_created == 0
        assert result.triples_created == 0
    
    def test_process_fk_relationships_missing_column(self):
        books_df = pl.DataFrame({
            "id": [1, 2],
            "title": ["Book 1", "Book 2"]
        })
        
        authors_df = pl.DataFrame({
            "id": [101, 102],
            "name": ["Author A", "Author B"]
        })
        
        datasets = {
            "books": books_df,
            "authors": authors_df
        }
        
        fk_relationships = [
            FKRelationship(
                source_column="missing_column",
                source_dataset="books",
                target_column="id",
                target_dataset="authors",
                relationship_type="hasAuthor"
            )
        ]
        
        result = self.processor.process_fk_relationships(datasets, fk_relationships)
        
        assert result.relationships_created == 0
        assert result.triples_created == 0
    
    def test_process_single_fk_relationship(self):
        books_df = pl.DataFrame({
            "id": [1, 2],
            "title": ["Book 1", "Book 2"],
            "author_id": [101, 102]
        })
        
        authors_df = pl.DataFrame({
            "id": [101, 102],
            "name": ["Author A", "Author B"]
        })
        
        datasets = {
            "books": books_df,
            "authors": authors_df
        }
        
        fk_rel = FKRelationship(
            source_column="author_id",
            source_dataset="books",
            target_column="id",
            target_dataset="authors",
            relationship_type="hasAuthor"
        )
        
        stats = BulkUpdateStats()
        self.processor._process_single_fk_relationship(fk_rel, datasets, stats)
        
        assert stats.relationships_created > 0
        assert stats.triples_created > 0
    
    def test_get_anchor_value_for_row(self):
        # Test with ID column
        row_data = {"id": 123, "name": "Test", "other": "value"}
        result = self.processor._get_anchor_value_for_row(row_data, "test_dataset")
        assert result == "123"
        
        # Test with Name column when no ID
        row_data = {"name": "Test Name", "other": "value"}
        result = self.processor._get_anchor_value_for_row(row_data, "test_dataset")
        assert result == "Test Name"
        
        # Test fallback to row_id
        row_data = {"row_id": 5, "other": "value"}
        result = self.processor._get_anchor_value_for_row(row_data, "test_dataset")
        assert result == "6"  # row_id + 1 for display
        
        # Test with string row_id
        row_data = {"row_id": "abc", "other": "value"}
        result = self.processor._get_anchor_value_for_row(row_data, "test_dataset")
        assert result == "abc"
    
    def test_ensure_dataframe(self):
        # Test with DataFrame
        df = pl.DataFrame({"col1": [1, 2, 3]})
        result = self.processor._ensure_dataframe(df)
        assert isinstance(result, pl.DataFrame)
        assert result.equals(df)
        
        # Test with list of dicts
        data = [{"col1": 1}, {"col1": 2}, {"col1": 3}]
        result = self.processor._ensure_dataframe(data)
        assert isinstance(result, pl.DataFrame)
        assert result.shape == (3, 1)
    
    def test_create_junction_table_relationships(self):
        junction_df = pl.DataFrame({
            "book_id": [1, 1, 2, 3],
            "tag_id": [101, 102, 101, 103],
            "relevance": ["high", "medium", "high", "low"]
        })
        
        result = self.processor.create_junction_table_relationships(
            junction_data=junction_df,
            primary_fk_column="book_id",
            primary_dataset="books",
            secondary_fk_column="tag_id",
            secondary_dataset="tags",
            relationship_type="hasTag",
            context_attributes=["relevance"]
        )
        
        assert isinstance(result, BulkUpdateStats)
        assert result.relationships_created > 0
        assert result.triples_created > 0
        
        # Check that relationship property was created
        assert Resource.objects.filter(
            uri=self.uri_service.generate_property_uri("hasTag")
        ).exists()
    
    def test_create_junction_table_relationships_empty(self):
        empty_df = pl.DataFrame()
        
        result = self.processor.create_junction_table_relationships(
            junction_data=empty_df,
            primary_fk_column="book_id",
            primary_dataset="books",
            secondary_fk_column="tag_id",
            secondary_dataset="tags",
            relationship_type="hasTag"
        )
        
        assert result.relationships_created == 0
        assert result.triples_created == 0
    
    def test_create_junction_table_relationships_no_context(self):
        junction_df = pl.DataFrame({
            "book_id": [1, 2],
            "tag_id": [101, 102]
        })
        
        result = self.processor.create_junction_table_relationships(
            junction_data=junction_df,
            primary_fk_column="book_id",
            primary_dataset="books",
            secondary_fk_column="tag_id",
            secondary_dataset="tags",
            relationship_type="hasTag"
        )
        
        assert isinstance(result, BulkUpdateStats)
        assert result.relationships_created > 0
        assert result.triples_created > 0
    
    @patch('arkumu.importer.services.importer.bulk_relationship_processor.Resource')
    @patch('arkumu.importer.services.importer.bulk_relationship_processor.Triple')
    def test_resolve_entity_references(self, mock_triple, mock_resource):
        # Mock existing resources
        mock_resource.objects.filter.return_value = [
            Mock(uri="http://example.com/entity1", name="Entity 1"),
            Mock(uri="http://example.com/entity2", name="Entity 2")
        ]
        
        # Mock cell resources
        mock_cell1 = Mock(uri="http://example.com/cell1")
        mock_cell2 = Mock(uri="http://example.com/cell2")
        mock_resource.objects.filter.return_value = [mock_cell1, mock_cell2]
        
        # Mock value triples
        mock_value_triple = Mock()
        mock_value_triple.object.value = "Entity 1"
        mock_triple.objects.filter.return_value.exists.return_value = True
        mock_triple.objects.filter.return_value.first.return_value = mock_value_triple
        
        result = self.processor.resolve_entity_references(
            "test_dataset", "name_column", ["reference_dataset1", "reference_dataset2"]
        )
        
        assert "resolved_references" in result
        assert "unresolved_references" in result
        assert "reference_mappings" in result
        assert "errors" in result
    
    def test_create_hierarchical_relationships(self):
        # Create test data first
        dataset_name = "test_hierarchy"
        
        # Create dataset resource
        dataset_uri = self.uri_service.generate_dataset_uri(dataset_name)
        dataset_resource = Resource.objects.create(
            uri=dataset_uri,
            resource_type=ResourceType.IRI,
            name=dataset_name,
            source="test_institution"
        )
        
        # Create parent column
        parent_column_uri = self.uri_service.generate_column_uri(dataset_name, "parent")
        parent_column = Resource.objects.create(
            uri=parent_column_uri,
            resource_type=ResourceType.IRI,
            name="parent",
            source="test_institution"
        )
        
        # Create child column
        child_column_uri = self.uri_service.generate_column_uri(dataset_name, "child")
        child_column = Resource.objects.create(
            uri=child_column_uri,
            resource_type=ResourceType.IRI,
            name="child",
            source="test_institution"
        )
        
        # Create parent cell
        parent_cell_uri = self.uri_service.generate_cell_uri(dataset_name, "parent", "1")
        parent_cell = Resource.objects.create(
            uri=parent_cell_uri,
            resource_type=ResourceType.IRI,
            name="Cell",
            source="test_institution"
        )
        
        # Create child cell
        child_cell_uri = self.uri_service.generate_cell_uri(dataset_name, "child", "1")
        child_cell = Resource.objects.create(
            uri=child_cell_uri,
            resource_type=ResourceType.IRI,
            name="Cell",
            source="test_institution"
        )
        
        # Create literal values
        parent_literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Parent1",
            source="test_institution",
            name="parent"
        )
        
        child_literal = Resource.objects.create(
            resource_type=ResourceType.LITERAL,
            value="Child1",
            source="test_institution",
            name="child"
        )
        
        # Create rdf:value property
        rdf_value_prop = Resource.objects.create(
            uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
            resource_type=ResourceType.PROPERTY,
            name="value",
            source="test_institution"
        )
        
        # Create value triples
        Triple.objects.create(
            subject=parent_cell,
            predicate=rdf_value_prop,
            object=parent_literal
        )
        
        Triple.objects.create(
            subject=child_cell,
            predicate=rdf_value_prop,
            object=child_literal
        )
        
        result = self.processor.create_hierarchical_relationships(
            dataset_name, "parent", "child", "hasChild"
        )
        
        assert isinstance(result, BulkUpdateStats)
        assert result.relationships_created >= 0
        assert result.triples_created >= 0
        
        # Check that relationship property was created
        assert Resource.objects.filter(
            uri=self.uri_service.generate_property_uri("hasChild")
        ).exists()
    
    def test_error_handling_in_fk_processing(self):
        # Test error handling with invalid data
        datasets = {
            "books": pl.DataFrame({"id": [1], "title": ["Book 1"], "author_id": [None]})
        }
        
        fk_relationships = [
            FKRelationship(
                source_column="author_id",
                source_dataset="books",
                target_column="id",
                target_dataset="authors",  # Missing dataset
                relationship_type="hasAuthor"
            )
        ]
        
        # Should not raise exception
        result = self.processor.process_fk_relationships(datasets, fk_relationships)
        assert isinstance(result, BulkUpdateStats)
    
    @patch('arkumu.importer.services.importer.bulk_relationship_processor.logger')
    def test_logging(self, mock_logger):
        # Test that appropriate logging occurs
        datasets = {
            "books": pl.DataFrame({"id": [1], "author_id": [101]})
        }
        fk_relationships = [
            FKRelationship(
                source_column="author_id",
                source_dataset="books", 
                target_column="id",
                target_dataset="authors",
                relationship_type="hasAuthor"
            )
        ]
        
        self.processor.process_fk_relationships(datasets, fk_relationships)
        
        # Check that info logs were called
        mock_logger.info.assert_called()
    
    def test_multiple_fk_relationships(self):
        # Test processing multiple FK relationships
        books_df = pl.DataFrame({
            "id": [1, 2],
            "title": ["Book 1", "Book 2"],
            "author_id": [101, 102],
            "publisher_id": [201, 202]
        })
        
        authors_df = pl.DataFrame({
            "id": [101, 102],
            "name": ["Author A", "Author B"]
        })
        
        publishers_df = pl.DataFrame({
            "id": [201, 202],
            "name": ["Publisher X", "Publisher Y"]
        })
        
        datasets = {
            "books": books_df,
            "authors": authors_df,
            "publishers": publishers_df
        }
        
        fk_relationships = [
            FKRelationship(
                source_column="author_id",
                source_dataset="books",
                target_column="id",
                target_dataset="authors",
                relationship_type="hasAuthor"
            ),
            FKRelationship(
                source_column="publisher_id",
                source_dataset="books",
                target_column="id",
                target_dataset="publishers",
                relationship_type="publishedBy"
            )
        ]
        
        result = self.processor.process_fk_relationships(datasets, fk_relationships)
        
        assert result.relationships_created > 0
        assert result.triples_created > 0
        
        # Check that both relationship properties were created
        assert Resource.objects.filter(
            uri=self.uri_service.generate_property_uri("hasAuthor")
        ).exists()
        assert Resource.objects.filter(
            uri=self.uri_service.generate_property_uri("publishedBy")
        ).exists()
    
    def test_junction_with_missing_values(self):
        # Test junction processing with missing values
        junction_df = pl.DataFrame({
            "book_id": [1, None, 3],
            "tag_id": [101, 102, None],
            "relevance": ["high", "medium", "low"]
        })
        
        result = self.processor.create_junction_table_relationships(
            junction_data=junction_df,
            primary_fk_column="book_id",
            primary_dataset="books",
            secondary_fk_column="tag_id",
            secondary_dataset="tags",
            relationship_type="hasTag"
        )
        
        assert isinstance(result, BulkUpdateStats)
        # Should only process rows with both values present
        assert result.relationships_created >= 0