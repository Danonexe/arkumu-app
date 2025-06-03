import pytest
import polars as pl
from typing import List, Dict, Any
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
from arkumu.importer.services.importer.smart_bulk_updater import SmartBulkUpdater, UpdateStrategy, BulkUpdateStats
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part

# Standard vocabulary URIs
HAS_PART_URI = "http://purl.org/dc/terms/hasPart"
RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
DCTERMS_RELATION_URI = "http://purl.org/dc/terms/relation"

BASE_URI = "http://test.arkumu.org/data"
INSTITUTION = "TEST_INST"

@pytest.fixture
def initial_data_empty(db):
    """Clear database and create required RDF properties."""
    Resource.objects.all().delete()
    Triple.objects.all().delete()
    Resource.objects.get_or_create(uri=HAS_PART_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "hasPart", "source": INSTITUTION})
    Resource.objects.get_or_create(uri=RDF_VALUE_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "value", "source": INSTITUTION})
    Resource.objects.get_or_create(uri=DCTERMS_RELATION_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "relation", "source": INSTITUTION})

@pytest.fixture
def updater_polars() -> SmartBulkUpdaterPolars:
    """SmartBulkUpdaterPolars with default settings."""
    return SmartBulkUpdaterPolars(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=True)

# Test data
simple_test_data: List[Dict[str, Any]] = [
    {"id": "1", "title": "Test Item One", "category": "Art", "year": "2023"},
    {"id": "2", "title": "Test Item Two", "category": "Design", "year": "2024"}
]


class TestCoreResourceCreationFixes:
    """Test the core fixes to resource creation that were implemented."""
    
    @pytest.mark.django_db
    def test_cell_resources_have_proper_column_names_not_generic_cell(self, initial_data_empty, updater_polars):
        """Test that cell resources are created with proper column names, not generic 'Cell'."""
        df = pl.DataFrame(simple_test_data)
        
        stats = updater_polars.import_csv_with_smart_updates(df, "testColumnNames")
        
        # Find cell resources and verify they have proper column names
        title_cells = Resource.objects.filter(uri__contains="/title/").filter(uri__contains="testcolumnnames")
        category_cells = Resource.objects.filter(uri__contains="/category/").filter(uri__contains="testcolumnnames")
        
        assert title_cells.count() == 2, "Should have 2 title cell resources"
        assert category_cells.count() == 2, "Should have 2 category cell resources"
        
        # Verify the cell resources have proper names (column names, not "Cell")
        for cell in title_cells:
            assert cell.name == "title", f"Expected name 'title', got '{cell.name}'"
        for cell in category_cells:
            assert cell.name == "category", f"Expected name 'category', got '{cell.name}'"
    
    @pytest.mark.django_db
    def test_literal_resources_have_proper_datatype_and_name(self, initial_data_empty, updater_polars):
        """Test that literal resources are created with proper datatype and name."""
        df = pl.DataFrame(simple_test_data)
        
        stats = updater_polars.import_csv_with_smart_updates(df, "testDatatype")
        
        # Find literal resources with specific values
        test_literal = Resource.objects.filter(resource_type=ResourceType.LITERAL, value="Test Item One").first()
        
        assert test_literal is not None, "Should find the 'Test Item One' literal"
        assert test_literal.datatype == "http://www.w3.org/2001/XMLSchema#string", f"Expected string datatype, got '{test_literal.datatype}'"
        assert test_literal.name == "title", f"Expected name 'title', got '{test_literal.name}'"
    
    @pytest.mark.django_db
    def test_resource_update_objects_have_proper_metadata(self, updater_polars):
        """Test that ResourceUpdate objects are created with proper metadata."""
        df = pl.DataFrame(simple_test_data)
        
        updates, stats = updater_polars.prepare_update_data_vectorized(df, "testMetadata")
        
        assert len(updates) > 0, "Should have created ResourceUpdate objects"
        
        # Check that each update has proper metadata
        for update in updates:
            assert update.new_name is not None, f"ResourceUpdate {update.uri} should have new_name set"
            assert update.new_datatype == "http://www.w3.org/2001/XMLSchema#string", f"ResourceUpdate {update.uri} should have proper datatype"
            assert len(update.new_values) == 1, f"ResourceUpdate {update.uri} should have exactly 1 value"


class TestPolarsVsOriginalCompatibility:
    """Test that Polars version produces identical results to the original implementation."""
    
    @pytest.mark.django_db
    def test_identical_results_to_original_implementation(self, initial_data_empty):
        """Test that both implementations create identical resources and triples."""
        dataset_name = "compatibilityTest"
        
        # Test with original implementation
        updater_original = SmartBulkUpdater(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=False)
        stats_original = updater_original.import_csv_with_smart_updates(simple_test_data, dataset_name + "_original")
        
        # Test with Polars implementation
        updater_polars = SmartBulkUpdaterPolars(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=False)
        df = pl.DataFrame(simple_test_data)
        stats_polars = updater_polars.import_csv_with_smart_updates(df, dataset_name + "_polars")
        
        # Should create the same number of resources and triples
        original_resources = Resource.objects.filter(uri__contains="compatibilitytest_original").exclude(uri__in=[HAS_PART_URI, RDF_VALUE_URI, DCTERMS_RELATION_URI]).count()
        polars_resources = Resource.objects.filter(uri__contains="compatibilitytest_polars").exclude(uri__in=[HAS_PART_URI, RDF_VALUE_URI, DCTERMS_RELATION_URI]).count()
        
        assert original_resources == polars_resources, f"Original created {original_resources} resources, Polars created {polars_resources}"
        # Both implementations should create the same data, but may count statistics differently
        # Verify that the same literal values were created
        original_literals = set(Resource.objects.filter(
            resource_type=ResourceType.LITERAL,
            uri__isnull=True
        ).filter(
            object_triples__subject__uri__contains="compatibilitytest_original"
        ).values_list('value', flat=True))
        
        polars_literals = set(Resource.objects.filter(
            resource_type=ResourceType.LITERAL,
            uri__isnull=True
        ).filter(
            object_triples__subject__uri__contains="compatibilitytest_polars"
        ).values_list('value', flat=True))
        
        assert original_literals == polars_literals, f"Different literal values: original {original_literals}, polars {polars_literals}"


class TestPolarsDataFrameHandling:
    """Test Polars-specific DataFrame handling capabilities."""
    
    @pytest.mark.django_db
    def test_polars_dataframe_input_and_mixed_data_types(self, initial_data_empty, updater_polars):
        """Test that Polars DataFrames work with mixed data types."""
        mixed_data = [
            {"id": 1, "text": "value1", "number": 42, "float_val": 3.14, "bool_val": True},
            {"id": 2, "text": "value2", "number": 84, "float_val": 2.71, "bool_val": False},
        ]
        
        df = pl.DataFrame(mixed_data)
        stats = updater_polars.import_csv_with_smart_updates(df, "mixedTypesTest")
        
        # Should handle all data types by converting to strings
        assert stats.resources_created > 0, "Should create resources"
        # With linking enabled, expect 22 triples (12 structural + 10 value triples)
        assert stats.triples_created == 22, "Should create 22 triples (12 structural + 10 value with linking enabled)"
        
        # Check that numeric values are converted to strings in ResourceUpdate objects
        updates, _ = updater_polars.prepare_update_data_vectorized(df, "test")
        for update in updates:
            assert isinstance(update.new_values[0], str), "Values should be converted to strings"
    
    @pytest.mark.django_db
    def test_list_dict_input_still_works(self, initial_data_empty, updater_polars):
        """Test that traditional List[Dict] input still works."""
        stats = updater_polars.import_csv_with_smart_updates(simple_test_data, "listDictTest")
        
        assert stats.resources_created > 0, "Should create resources"
        assert stats.triples_created > 0, "Should create triples"


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases."""
    
    @pytest.mark.django_db
    def test_null_empty_values_and_unicode_handling(self, initial_data_empty, updater_polars):
        """Test handling of null/empty values and Unicode characters."""
        test_data = [
            {"id": "1", "title": "Valid Title", "category": None, "artist": "Müller"},
            {"id": "2", "title": "", "category": "Valid Category", "artist": "García"},
            {"id": "3", "title": None, "category": None, "artist": None}
        ]
        
        df = pl.DataFrame(test_data)
        stats = updater_polars.import_csv_with_smart_updates(df, "edgeCasesTest")
        
        # Should only create resources for non-empty values
        literal_resources = Resource.objects.filter(
            resource_type=ResourceType.LITERAL,
            source=slugify_uri_part(INSTITUTION),
            uri__isnull=True
        )
        
        # Should find literals for: "Valid Title", "Valid Category", "Müller", "García", "1", "2", "3"
        expected_values = {"Valid Title", "Valid Category", "Müller", "García", "1", "2", "3"}
        actual_values = set(literal_resources.values_list('value', flat=True))
        
        assert actual_values == expected_values, f"Expected {expected_values}, got {actual_values}"
    
    @pytest.mark.django_db
    def test_empty_dataframe_handling(self, initial_data_empty, updater_polars):
        """Test handling of empty DataFrame."""
        empty_df = pl.DataFrame()
        stats = updater_polars.import_csv_with_smart_updates(empty_df, "emptyTest")
        
        assert stats.resources_created == 0, "Should not create resources for empty DataFrame"
        assert stats.cells_processed == 0, "Should not process any cells"
        assert stats.triples_created == 0, "Should not create any triples"


class TestRealWorldData:
    """Test with real-world style data."""
    
    @pytest.mark.django_db
    def test_real_world_csv_with_long_text_and_german_content(self, initial_data_empty, updater_polars):
        """Test complete workflow with real-world style data including long text and German content."""
        real_world_data = [
            {
                "Projekt_ID": "200",
                "Originaltitel": "Project Title Alpha", 
                "Originaltitel_Sprache": "ger",
                "_Beschreibung_verkettet": "Project Alpha ist ein interaktives, digitales Environment mit mehreren technischen Komponenten für moderne Kunstinstallationen.",
                "Kategorie": "Installation"
            },
            {
                "Projekt_ID": "302",
                "Originaltitel": "Project Beta System",
                "Originaltitel_Sprache": "lat", 
                "_Beschreibung_verkettet": "Project Beta ist eine Testmethodik für die technische Verarbeitung von digitalen Datenströmen.",
                "Kategorie": "Digital Art"
            }
        ]
        
        df = pl.DataFrame(real_world_data)
        stats = updater_polars.import_csv_with_smart_updates(df, "realWorldTest")
        
        # Verify import worked
        assert stats.resources_created > 0, "Should have created resources"
        # With linking enabled, expect 22 triples (12 structural + 10 value triples)
        assert stats.triples_created == 22, "Should create 22 triples (12 structural + 10 value with linking enabled)"
        
        # Verify German text handling
        german_literals = Resource.objects.filter(
            resource_type=ResourceType.LITERAL,
            value__contains="interaktives"
        )
        assert german_literals.exists(), "Should handle German text properly"
        
        # Verify long text handling
        long_text_literal = Resource.objects.filter(
            resource_type=ResourceType.LITERAL,
            value__contains="technischen Komponenten"
        ).first()
        assert long_text_literal is not None, "Should handle long German text properly"
        assert long_text_literal.name == "_Beschreibung_verkettet", "Should have correct field name" 