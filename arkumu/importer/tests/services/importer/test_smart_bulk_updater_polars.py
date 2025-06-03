import pytest
import polars as pl
from typing import List, Dict, Any
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
from arkumu.importer.services.importer.smart_bulk_updater import UpdateStrategy, BulkUpdateStats
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part

# Standard vocabulary URIs that will be used/checked
HAS_PART_URI = "http://purl.org/dc/terms/hasPart"
RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
DCTERMS_RELATION_URI = "http://purl.org/dc/terms/relation"

BASE_URI = "http://test.arkumu.org/data"
INSTITUTION = "TEST_INST"
NUM_FIXTURE_RESOURCES = 3  # For HAS_PART, RDF_VALUE, DCTERMS_RELATION properties

@pytest.fixture
def initial_data_empty(db):
    """Clear database and create required RDF properties."""
    Resource.objects.all().delete()
    Triple.objects.all().delete()
    Resource.objects.get_or_create(uri=HAS_PART_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "hasPart", "source": INSTITUTION})
    Resource.objects.get_or_create(uri=RDF_VALUE_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "value", "source": INSTITUTION})
    Resource.objects.get_or_create(uri=DCTERMS_RELATION_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "relation", "source": INSTITUTION})
    assert Resource.objects.count() == NUM_FIXTURE_RESOURCES
    return

@pytest.fixture
def updater_polars_default() -> SmartBulkUpdaterPolars:
    """SmartBulkUpdaterPolars with default settings."""
    return SmartBulkUpdaterPolars(
        institution=INSTITUTION, 
        base_uri=BASE_URI, 
        link_row_cells=False,
        multi_value_threshold=0.2  # 20% threshold for multi-value detection
    )

# Test Data with Multi-Value Columns (simple CSV format)
multi_value_csv_data: List[Dict[str, Any]] = [
    {"id": "1", "names": "John, Jane, Bob", "single_field": "alpha", "tags": "red,blue,green"},
    {"id": "2", "names": "Alice, Charlie", "single_field": "beta", "tags": "yellow,purple"},
    {"id": "3", "names": "David, Eve, Frank, Grace", "single_field": "gamma", "tags": "orange,black,white"},
    {"id": "4", "names": "Henry", "single_field": "delta", "tags": "pink"},
    {"id": "5", "names": "Iris, Jack", "single_field": "epsilon", "tags": "brown,gray"}
]

# Real KHM-style data with quoted fields (semicolon-separated, commas inside quotes should NOT be split)
khm_real_csv_data: List[Dict[str, Any]] = [
    {
        "Projekt_ID": "200",
        "Originaltitel": "Project Title Alpha", 
        "Originaltitel_Sprache": "ger",
        "_Beschreibung_verkettet": "Project Alpha ist ein interaktives, digitales Environment, bestehend aus mehreren technischen Komponenten, welche bei Annaehrung der Benutzer zu funktionieren beginnen. Die elektronischen Einheiten des Systems bilden ein strukturiertes System aus Eingaben und Ausgaben einer fiktiven Anwendung: der Test-Anwendung.",
        "Kategorie": "Installation",
        "Unterkategorie": "Installation"
    },
    {
        "Projekt_ID": "302",
        "Originaltitel": "Project Beta System",
        "Originaltitel_Sprache": "lat", 
        "_Beschreibung_verkettet": "Project Beta ist eine Testmethodik, die auf der technischen Mehrfachverarbeitung eines digital aufgeweiteten Datenstrahls und seinen systemdefinierenden Eigenschaften basiert. Der Prozess der Mehrfachverarbeitung konnte durch Konstruktion einer Test-Apparatur vollstaendig automatisiert werden.",
        "Kategorie": "Installation",
        "Unterkategorie": "Installation"
    },
    {
        "Projekt_ID": "528", 
        "Originaltitel": "Test Location Gamma",
        "Originaltitel_Sprache": "ger",
        "_Beschreibung_verkettet": "Test Location Gamma ist eine Beispiel-Einrichtung inmitten des fiktiven Testgebietes, wo es die - nach Auskunft vieler Test-Nutzer - besten Beispiele von Deutschland geben soll. Das Test-System wurde vor einigen Jahren als Prototyp eroeffnet und zieht heute Testnutzer aus verschiedenen Staedten an.",
        "Kategorie": "Film / TV / Video",
        "Unterkategorie": "Dokumentarfilm"
    }
]

# Real Folkwang-style data with true comma-separated values (no quotes, commas ARE multi-value separators)
folkwang_real_csv_data: List[Dict[str, Any]] = [
    {
        "Projekt-ID": "3",
        "Bevorzugter Titel": "Test Project Alpha", 
        "Beschreibung": "3,4",
        "Schlagwort": "Q161439,Q1129653,Q160402,Q33767,Q328835",
        "Projektkategorie": "9,13",
        "Deutscher Kommentar": "Lehrgebiet: Test Fachbereich Grundlagen"
    },
    {
        "Projekt-ID": "25",
        "Bevorzugter Titel": "Sample Project Beta",
        "Beschreibung": "34", 
        "Schlagwort": "Q7860,Q107425,Q11461,Q160402,Q179448,Q1200957",
        "Projektkategorie": "9,14,17",
        "Deutscher Kommentar": "Lehrgebiet: Test Beispiel Informationsdesign"
    },
    {
        "Projekt-ID": "60",
        "Bevorzugter Titel": "Demo Project Gamma",
        "Beschreibung": "73",
        "Schlagwort": "Q756,Q22676,Q177998,Q61700915,Q219416", 
        "Projektkategorie": "9,16",
        "Deutscher Kommentar": "Lehrgebiet: Test Interaction Design, Beispiel Innovation"
    }
]

# Test data as Polars DataFrame
multi_value_polars_df = pl.DataFrame(multi_value_csv_data)


class TestPolarsOptimizations:
    """Test Polars-specific optimizations and performance improvements."""
    
    @pytest.mark.django_db
    def test_polars_dataframe_input(self, updater_polars_default):
        """Test that Polars DataFrames can be used as input."""
        df = pl.DataFrame(multi_value_csv_data)
        
        # Should be able to analyze the DataFrame directly
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(df)
        
        assert "names" in analysis
        assert "tags" in analysis
        # Multi-value detection is disabled, so all should be single-value
        assert analysis["names"]["is_multi_value"] is False
        assert analysis["tags"]["is_multi_value"] is False
        assert analysis["single_field"]["is_multi_value"] is False
    
    @pytest.mark.django_db
    def test_polars_column_analysis(self, updater_polars_default):
        """Test column analysis using Polars operations."""
        df = pl.DataFrame(multi_value_csv_data)
        
        # Test formerly multi-value column (now treated as single-value)
        names_analysis = updater_polars_default.analyze_column_for_multi_values_polars(df, "names")
        assert names_analysis["is_multi_value"] is False
        assert names_analysis["separator"] is None
        assert names_analysis["stats"]["percentage"] == 0.0  # No multi-value detection
        assert names_analysis["stats"]["confidence_score"] == 0.0
        
        # Test single-value column
        single_analysis = updater_polars_default.analyze_column_for_multi_values_polars(df, "single_field")
        assert single_analysis["is_multi_value"] is False
        assert single_analysis["stats"]["percentage"] == 0.0
    
    @pytest.mark.django_db
    def test_polars_prepare_update_data(self, updater_polars_default):
        """Test data preparation using Polars operations."""
        df = pl.DataFrame(multi_value_csv_data)
        
        updates, stats = updater_polars_default.prepare_update_data_polars(df, "test_dataset")
        
        # Should have updates for all non-empty cells
        assert len(updates) > 0
        assert stats.multi_value_cells_detected == 0  # Multi-value detection disabled
        # With no splitting, total_values_created should equal non-empty cells
        assert stats.total_values_created == len(updates)  # 1:1 ratio since no splitting
        
        # Check that NO multi-value fields exist (all treated as single-value)
        multi_value_updates = [u for u in updates if u.is_multi_value]
        assert len(multi_value_updates) == 0  # No multi-value updates since splitting is disabled


class TestRealWorldCSVFormats:
    """Test handling of real-world CSV formats like KHM and Folkwang data."""
    
    @pytest.mark.django_db 
    def test_khm_style_data_analysis(self, updater_polars_default):
        """Test analysis of KHM-style data with German text and complex descriptions."""
        df = pl.DataFrame(khm_real_csv_data)
        
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(df)
        
        # ALL fields should be detected as single-value (multi-value detection disabled)
        assert analysis["Projekt_ID"]["is_multi_value"] is False
        assert analysis["Originaltitel"]["is_multi_value"] is False
        assert analysis["Originaltitel_Sprache"]["is_multi_value"] is False
        assert analysis["_Beschreibung_verkettet"]["is_multi_value"] is False
        assert analysis["Kategorie"]["is_multi_value"] is False
        
        # Check that all analysis provides the disabled statistics
        for field_name, field_analysis in analysis.items():
            assert field_analysis["is_multi_value"] is False
            assert field_analysis["separator"] is None
            assert field_analysis["stats"]["percentage"] == 0.0
    
    @pytest.mark.django_db
    def test_folkwang_style_comma_separated_values(self, updater_polars_default):
        """Test analysis of Folkwang-style data (now treated as single-value despite commas)."""
        df = pl.DataFrame(folkwang_real_csv_data)
        
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(df)
        
        # ALL fields should be single-value (multi-value detection disabled)
        assert analysis["Schlagwort"]["is_multi_value"] is False
        assert analysis["Projekt-ID"]["is_multi_value"] is False
        assert analysis["Bevorzugter Titel"]["is_multi_value"] is False
        assert analysis["Projektkategorie"]["is_multi_value"] is False
        
        # Check statistics are consistent
        for field_name, field_analysis in analysis.items():
            stats = field_analysis["stats"]
            assert stats["percentage"] == 0.0
            assert stats["confidence_score"] == 0.0
    
    @pytest.mark.django_db
    def test_mixed_separator_handling(self, updater_polars_default):
        """Test handling data with various comma usage patterns (all treated as single-value)."""
        mixed_data = [
            {"id": "1", "codes": "A001,B002,C003", "names": "Schmidt, Mueller", "text": "This is a sentence, with commas."},
            {"id": "2", "codes": "D004,E005", "names": "Weber, Fischer", "text": "Another sentence, also with commas."},  
            {"id": "3", "codes": "F006,G007,H008", "names": "Wagner", "text": "Text without much punctuation"},
            {"id": "4", "codes": "I009", "names": "Becker, Schulz", "text": "Some text, here and there."},
        ]
        
        df = pl.DataFrame(mixed_data)
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(df)
        
        # ALL fields should be single-value (multi-value detection disabled)
        assert analysis["codes"]["is_multi_value"] is False
        assert analysis["names"]["is_multi_value"] is False
        assert analysis["text"]["is_multi_value"] is False
        assert analysis["id"]["is_multi_value"] is False
        
        # Verify all have consistent disabled statistics
        for field_name, field_analysis in analysis.items():
            assert field_analysis["separator"] is None
            assert field_analysis["stats"]["percentage"] == 0.0
    
    @pytest.mark.django_db
    def test_german_text_with_quotes(self, updater_polars_default):
        """Test handling of German text with quotes and special characters."""
        german_data = [
            {"id": "1", "titel": "Sample Project Alpha", "beschreibung": "Ein interaktives Test-Environment mit mehreren Einheiten", "tags": "kunst,digital,interaktiv"},
            {"id": "2", "titel": "Demo Project Beta", "beschreibung": "Beispiel-Verarbeitung eines Test-Datenstrahls", "tags": "fotografie,laser"},
            {"id": "3", "titel": "Test Location Gamma", "beschreibung": "Eine Beispiel-Einrichtung im fiktiven Testgebiet", "tags": "dokumentation,gastronomie,film"}
        ]
        
        df = pl.DataFrame(german_data)
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(df)
        
        # ALL fields should be single-value (multi-value detection disabled)
        assert analysis["tags"]["is_multi_value"] is False
        assert analysis["titel"]["is_multi_value"] is False
        assert analysis["beschreibung"]["is_multi_value"] is False
        assert analysis["id"]["is_multi_value"] is False
    
    @pytest.mark.django_db
    def test_import_real_world_data(self, initial_data_empty, updater_polars_default):
        """Test complete import workflow with real-world style data."""
        df = pl.DataFrame(folkwang_real_csv_data)
        dataset_name = "folkwangTest"
        
        stats = updater_polars_default.import_csv_with_smart_updates(df, dataset_name)
        
        # Verify import worked
        assert stats.resources_created > 0
        
        # No multi-value detection should occur
        assert stats.multi_value_cells_detected == 0
        # With no splitting, total_values_created should be approximately equal to non-empty cells
        assert stats.total_values_created > 0


class TestCompatibilityWithOriginal:
    """Test that Polars version produces same results as original implementation."""
    
    @pytest.mark.django_db
    def test_compatibility_multi_value_detection(self, updater_polars_default):
        """Test that multi-value detection produces disabled results."""
        # Test using compatibility methods that should delegate to Polars
        analysis = updater_polars_default.analyze_dataset_multi_values(multi_value_csv_data)
        
        # Should detect NO multi-value patterns (disabled)
        assert analysis["names"]["is_multi_value"] is False
        assert analysis["tags"]["is_multi_value"] is False
        assert analysis["single_field"]["is_multi_value"] is False
        assert analysis["id"]["is_multi_value"] is False
    
    @pytest.mark.django_db
    def test_compatibility_import_with_dataframe(self, initial_data_empty, updater_polars_default):
        """Test that import works with Polars DataFrame input."""
        df = pl.DataFrame(multi_value_csv_data)
        dataset_name = "polarsCompatibilityTest"
        
        stats = updater_polars_default.import_csv_with_smart_updates(df, dataset_name)
        
        # Verify basic import worked
        assert stats.resources_created > 0
        assert stats.multi_value_cells_detected == 0  # No multi-value detection
        # With no splitting, values should be roughly equal to non-empty cells
        assert stats.total_values_created > 0
        
        # Find all cell resources for the dataset (using the same approach as other tests)
        dataset_resources = Resource.objects.filter(
            uri__contains="polarscompatibilitytest"
        )
        assert dataset_resources.count() > 0, "Should have created dataset resources"
        
        # Check that values from the input data were created (as complete strings)
        john_resources = Resource.objects.filter(
            value__contains="John"  # May be "John, Jane, Bob" as single value
        )
        alpha_resources = Resource.objects.filter(
            value="alpha"
        )
        
        # Since we're not splitting, "John" might be part of "John, Jane, Bob"
        assert john_resources.exists() or Resource.objects.filter(value="John, Jane, Bob").exists(), "Should find John or the complete names string"
        assert alpha_resources.exists(), "Should find alpha as a value"
    
    @pytest.mark.django_db 
    def test_compatibility_import_with_list_dict(self, initial_data_empty, updater_polars_default):
        """Test that import still works with traditional List[Dict] input."""
        dataset_name = "polarsListDictTest"
        
        stats = updater_polars_default.import_csv_with_smart_updates(multi_value_csv_data, dataset_name)
        
        # Should work identically to DataFrame input
        assert stats.resources_created > 0
        assert stats.multi_value_cells_detected == 0  # No multi-value detection
        assert stats.total_values_created > 0


class TestPolarsPerformanceFeatures:
    """Test features that specifically leverage Polars for better performance."""
    
    @pytest.mark.django_db
    def test_large_dataset_handling(self, updater_polars_default):
        """Test handling of larger datasets (simulated)."""
        # Create a larger dataset
        large_data = []
        for i in range(100):  # 100 rows
            large_data.append({
                "id": str(i),
                "multi_field": f"value{i}, value{i+1}, value{i+2}",
                "single_field": f"single{i}",
                "numeric_field": str(i * 10)
            })
        
        df = pl.DataFrame(large_data)
        
        # Analysis should be fast with Polars (but all single-value)
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(df)
        
        assert analysis["multi_field"]["is_multi_value"] is False
        assert analysis["single_field"]["is_multi_value"] is False
        assert analysis["numeric_field"]["is_multi_value"] is False
        
        # Preparing update data should handle the larger dataset efficiently
        updates, stats = updater_polars_default.prepare_update_data_polars(df, "large_test")
        
        assert len(updates) == 100 * 4  # 100 rows * 4 columns
        assert stats.multi_value_cells_detected == 0  # No multi-value detection
    
    @pytest.mark.django_db
    def test_empty_dataframe_handling(self, updater_polars_default):
        """Test handling of empty DataFrames."""
        empty_df = pl.DataFrame()
        
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(empty_df)
        assert analysis == {}
        
        updates, stats = updater_polars_default.prepare_update_data_polars(empty_df, "empty_test")
        assert len(updates) == 0
        assert stats.multi_value_cells_detected == 0
    
    @pytest.mark.django_db
    def test_mixed_data_types(self, updater_polars_default):
        """Test handling of mixed data types in Polars DataFrame."""
        mixed_data = [
            {"id": 1, "text": "value1, value2", "number": 42, "float_val": 3.14},
            {"id": 2, "text": "value3, value4", "number": 84, "float_val": 2.71},
        ]
        
        df = pl.DataFrame(mixed_data)
        
        # Should handle mixed types correctly (all single-value)
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(df)
        
        assert analysis["text"]["is_multi_value"] is False
        assert analysis["number"]["is_multi_value"] is False
        assert analysis["float_val"]["is_multi_value"] is False
    
    @pytest.mark.django_db
    def test_unicode_and_special_characters(self, updater_polars_default):
        """Test handling of Unicode characters and special symbols."""
        unicode_data = [
            {"id": "1", "künstler": "Müller, Schäfer, Weiß", "themen": "Ästhetik,Künstleridentität", "emoji": "🎨,🖼️,🎭"},
            {"id": "2", "künstler": "García, López", "themen": "Modernität,Tradition", "emoji": "🌟,✨"},
            {"id": "3", "künstler": "Ørsted", "themen": "Minimalismus", "emoji": "⚪"}
        ]
        
        df = pl.DataFrame(unicode_data)
        analysis = updater_polars_default.analyze_dataset_multi_values_polars(df)
        
        # Should correctly handle Unicode but detect no multi-value patterns
        assert analysis["künstler"]["is_multi_value"] is False
        assert analysis["themen"]["is_multi_value"] is False
        assert analysis["emoji"]["is_multi_value"] is False


class TestMultiValueTripleCreation:
    """Test that single-value cells create single triples correctly (multi-value disabled)."""
    
    @pytest.mark.django_db
    def test_multi_value_cell_creates_single_triple(self, initial_data_empty, updater_polars_default):
        """Test that a cell with comma-separated content creates ONE triple (no splitting)."""
        # Simple test data with comma-separated content (treated as single value)
        test_data = [
            {"id": "1", "tags": "red,blue,green", "title": "Test Item"}
        ]
        
        df = pl.DataFrame(test_data)
        dataset_name = "singleValueTripleTest"
        
        # Import the data
        stats = updater_polars_default.import_csv_with_smart_updates(df, dataset_name)
        
        # Verify basic import worked
        assert stats.resources_created > 0
        assert stats.triples_created > 0
        
        # Find the tags cell resource
        tags_resources = Resource.objects.filter(
            uri__contains="/tags/",
        ).filter(
            uri__contains="singlevaluetripletest"
        )
        
        assert tags_resources.count() >= 1, "Should have created at least one tags cell resource"
        tags_resource = tags_resources.first()
        
        # Find all triples for this cell (should be 1: "red,blue,green" as single value)
        tags_triples = Triple.objects.filter(
            subject=tags_resource,
            predicate__uri=RDF_VALUE_URI
        )
        
        assert tags_triples.count() == 1, f"Should have created 1 triple for tags cell, found {tags_triples.count()}"
        
        # Verify the actual value (complete comma-separated string)
        triple_value = tags_triples.first().object.value
        assert triple_value == "red,blue,green", f"Expected 'red,blue,green', got '{triple_value}'"
    
    @pytest.mark.django_db
    def test_single_value_cell_creates_one_triple(self, initial_data_empty, updater_polars_default):
        """Test that a single-value cell creates exactly one triple."""
        test_data = [
            {"id": "1", "title": "Single Value Item", "count": "42"}
        ]
        
        df = pl.DataFrame(test_data)
        dataset_name = "singleValueTripleTest"
        
        # Import the data
        stats = updater_polars_default.import_csv_with_smart_updates(df, dataset_name)
        
        # Find the title cell resource
        title_resources = Resource.objects.filter(
            uri__contains="/title/",
        ).filter(
            uri__contains="singlevaluetripletest"
        )
        
        assert title_resources.count() >= 1, "Should have created at least one title cell resource"
        title_resource = title_resources.first()
        
        # Find triples for this cell (should be 1)
        title_triples = Triple.objects.filter(
            subject=title_resource,
            predicate__uri=RDF_VALUE_URI
        )
        
        assert title_triples.count() == 1, f"Should have created 1 triple for title cell, found {title_triples.count()}"
        assert title_triples.first().object.value == "Single Value Item"
    
    @pytest.mark.django_db
    def test_mixed_single_and_comma_value_columns(self, initial_data_empty, updater_polars_default):
        """Test dataset with both simple and comma-containing columns (all treated as single-value)."""
        test_data = [
            {"id": "1", "title": "Item One", "tags": "art,digital,interactive"},
            {"id": "2", "title": "Item Two", "tags": "photo,print"},
            {"id": "3", "title": "Item Three", "tags": "sculpture"}
        ]
        
        df = pl.DataFrame(test_data)
        dataset_name = "mixedValueTest"
        
        # Import the data
        stats = updater_polars_default.import_csv_with_smart_updates(df, dataset_name)
        
        # Find all tags resources
        tags_resources = Resource.objects.filter(
            uri__contains="/tags/",
        ).filter(
            uri__contains="mixedvaluetest"
        ).order_by('uri')
        
        assert tags_resources.count() == 3, f"Should have created 3 tags resources, found {tags_resources.count()}"
        
        # Check each tags resource (all should have exactly 1 triple)
        for tags_resource in tags_resources:
            triples = Triple.objects.filter(
                subject=tags_resource,
                predicate__uri=RDF_VALUE_URI
            )
            assert triples.count() == 1, f"Each tags resource should have 1 triple, found {triples.count()}"
        
        # Check that all title resources have exactly 1 triple each
        title_resources = Resource.objects.filter(
            uri__contains="/title/",
        ).filter(
            uri__contains="mixedvaluetest"
        )
        
        assert title_resources.count() == 3, "Should have 3 title resources"
        
        for title_resource in title_resources:
            title_triples = Triple.objects.filter(
                subject=title_resource,
                predicate__uri=RDF_VALUE_URI
            )
            assert title_triples.count() == 1, f"Each title should have 1 triple"
    
    @pytest.mark.django_db
    def test_empty_and_null_values_handling(self, initial_data_empty, updater_polars_default):
        """Test that empty and null values don't create unnecessary triples."""
        test_data = [
            {"id": "1", "tags": "valid,value", "empty": "", "null_field": None},
            {"id": "2", "tags": "", "empty": "not_empty", "null_field": "not_null"}
        ]
        
        df = pl.DataFrame(test_data)
        dataset_name = "emptyNullTest"
        
        # Import the data
        stats = updater_polars_default.import_csv_with_smart_updates(df, dataset_name)
        
        # Find tags resources that should have values
        tags_with_values = Resource.objects.filter(
            uri__contains="/tags/",
        ).filter(
            uri__contains="emptynulltest"
        )
        
        # Should have at least one tags resource with triple
        valid_tags_found = False
        for tags_resource in tags_with_values:
            triples = Triple.objects.filter(
                subject=tags_resource,
                predicate__uri=RDF_VALUE_URI
            )
            if triples.count() == 1:  # "valid,value" as single value
                valid_tags_found = True
                value = triples.first().object.value
                assert value == "valid,value", f"Expected 'valid,value', got '{value}'"
        
        assert valid_tags_found, "Should find tags resource with 1 value"
    
    @pytest.mark.django_db
    def test_statistics_reflect_actual_triples_created(self, initial_data_empty, updater_polars_default):
        """Test that statistics accurately reflect the number of triples created."""
        test_data = [
            {"id": "1", "multi": "a,b,c", "single": "x"},
            {"id": "2", "multi": "d,e", "single": "y"}
        ]
        
        df = pl.DataFrame(test_data)
        dataset_name = "statisticsTest"
        
        # Import the data
        stats = updater_polars_default.import_csv_with_smart_updates(df, dataset_name)
        
        # Verify statistics match actual database
        actual_triples = Triple.objects.filter(
            predicate__uri=RDF_VALUE_URI
        ).count()
        
        assert stats.triples_created == actual_triples, \
            f"Statistics show {stats.triples_created} triples, but database has {actual_triples}"
        
        # Should have created exactly 6 triples (1 per cell: id="1", multi="a,b,c", single="x", id="2", multi="d,e", single="y")
        assert actual_triples == 6, f"Should have exactly 6 triples (3 columns x 2 rows), got {actual_triples}" 