import pytest
import polars as pl
from typing import List, Dict, Any
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
from arkumu.importer.services.importer.smart_bulk_updater_polars import UpdateStrategy, BulkUpdateStats
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
    return SmartBulkUpdaterPolars(institution=INSTITUTION, base_uri=BASE_URI)

@pytest.fixture
def updater_polars_row_topology() -> SmartBulkUpdaterPolars:
    """SmartBulkUpdaterPolars with row topology."""
    return SmartBulkUpdaterPolars(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=True, link_topology="row")

@pytest.fixture
def updater_polars_first_column_topology() -> SmartBulkUpdaterPolars:
    """SmartBulkUpdaterPolars with first_column topology."""
    return SmartBulkUpdaterPolars(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=False, link_topology="first_column")

@pytest.fixture
def updater_polars_mesh_topology() -> SmartBulkUpdaterPolars:
    """SmartBulkUpdaterPolars with mesh topology."""
    return SmartBulkUpdaterPolars(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=False, link_topology="mesh")

@pytest.fixture
def updater_polars_column_only() -> SmartBulkUpdaterPolars:
    """SmartBulkUpdaterPolars with column-only hierarchy."""
    return SmartBulkUpdaterPolars(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=False)

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
        # With column-only topology: 5 dataset→column + 10 column→cell + 10 cell→value = 25 triples expected
        assert stats.triples_created == 25, f"Should create exactly 25 triples with column-only topology, got {stats.triples_created}"
        
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
        # With column-only topology and multi-value detection: 5 dataset→column + 11 column→cell + 11 cell→value = 27 triples expected
        # (The _Beschreibung_verkettet column is detected as multi-value for row 1, creating an extra cell and value triple)
        assert stats.triples_created == 27, f"Should create exactly 27 triples with column-only topology and multi-value detection, got {stats.triples_created}"
        
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


class TestTopologyImplementation:
    """Test the new topology implementation with column hierarchy and URI-based row tracking."""
    
    @pytest.mark.django_db
    def test_column_only_topology_creates_minimal_structure(self, initial_data_empty, updater_polars_column_only):
        """Test that column-only topology creates minimal triple structure."""
        df = pl.DataFrame(simple_test_data)
        stats = updater_polars_column_only.import_csv_with_smart_updates(df, "columnOnlyTest")
        
        # Verify column resources were created
        column_resources = Resource.objects.filter(uri__contains="/columns/")
        assert column_resources.count() == 4, f"Expected 4 column resources, got {column_resources.count()}"
        
        # Verify column names
        column_names = set(column_resources.values_list('name', flat=True))
        expected_columns = {"id", "title", "category", "year"}
        assert column_names == expected_columns, f"Expected columns {expected_columns}, got {column_names}"
        
                # Verify Dataset → Column relationships
        dataset = Resource.objects.filter(uri__endswith="/datasets/columnonlytest").first()
        assert dataset is not None, "Dataset resource should exist"

        has_part_prop = Resource.objects.get(uri=HAS_PART_URI)
        dataset_to_column_triples = Triple.objects.filter(
            subject=dataset,
            predicate=has_part_prop,
            object__in=column_resources
        )
        assert dataset_to_column_triples.count() == 4, "Should have 4 dataset→column relationships"
        
        # Verify Column → Cell relationships
        cell_resources = Resource.objects.filter(uri__contains="/datasets/columnonlytest/").exclude(uri__contains="/columns/")
        column_to_cell_triples = Triple.objects.filter(
            subject__in=column_resources,
            predicate=has_part_prop,
            object__in=cell_resources
        )
        assert column_to_cell_triples.count() == 8, "Should have 8 column→cell relationships (2 rows × 4 columns)"
        
        # Verify no row resources were created
        row_resources = Resource.objects.filter(uri__contains="/rows/")
        assert row_resources.count() == 0, "Should not create row resources in column-only mode"
        
        # Verify minimal triple count: 4 dataset→column + 8 column→cell + 8 cell→value = 20 triples
        assert stats.triples_created == 20, f"Expected 20 minimal triples, got {stats.triples_created}"
    
    @pytest.mark.django_db
    def test_row_topology_creates_dual_hierarchy(self, initial_data_empty, updater_polars_row_topology):
        """Test that row topology creates both column and row hierarchies."""
        
        # DEBUG: Check what resources exist BEFORE import
        existing_resources = Resource.objects.filter(uri__contains="/datasets/rowtopologytest/")
        print(f"DEBUG: Found {existing_resources.count()} existing resources BEFORE import:")
        for resource in existing_resources:
            print(f"  - {resource.uri}")
        
        df = pl.DataFrame(simple_test_data)
        stats = updater_polars_row_topology.import_csv_with_smart_updates(df, "rowTopologyTest")
        
        # Verify both column and row resources were created
        column_resources = Resource.objects.filter(uri__contains="/columns/")
        row_resources = Resource.objects.filter(uri__contains="/rows/")
        
        assert column_resources.count() == 4, f"Expected 4 column resources, got {column_resources.count()}"
        assert row_resources.count() == 2, f"Expected 2 row resources, got {row_resources.count()}"
        
        # Verify row names (should be sequential 1-based)
        row_names = sorted(row_resources.values_list('name', flat=True))
        assert len(row_names) == 2, f"Expected 2 row names, got {len(row_names)}"
        assert all(name.startswith("Row ") for name in row_names), f"All row names should start with 'Row ', got {row_names}"
        # Should be sequential numbers
        row_numbers = [int(name.split()[-1]) for name in row_names]
        assert row_numbers[1] == row_numbers[0] + 1, f"Row numbers should be sequential, got {row_numbers}"
        
        # Verify dual hierarchy: cells should be connected to both columns and rows
        has_part_prop = Resource.objects.get(uri=HAS_PART_URI)
        cell_resources = Resource.objects.filter(uri__contains="/datasets/rowtopologytest/").exclude(uri__contains="/columns/").exclude(uri__contains="/rows/")
        
        # DEBUG: Print all cell resources to see what's there
        print(f"DEBUG: Found {cell_resources.count()} cell resources:")
        for cell in cell_resources:
            print(f"  - {cell.uri}")
        
        # Each cell should have 2 incoming hasPart relationships (one from column, one from row)
        for cell in cell_resources:
            incoming_triples = Triple.objects.filter(predicate=has_part_prop, object=cell)
            print(f"DEBUG: Cell {cell.uri} has {incoming_triples.count()} incoming hasPart relationships")
            assert incoming_triples.count() == 2, f"Cell {cell.uri} should have 2 incoming hasPart relationships"
            
            # Verify one comes from column, one from row
            source_types = set()
            for triple in incoming_triples:
                if "/columns/" in triple.subject.uri:
                    source_types.add("column")
                elif "/rows/" in triple.subject.uri:
                    source_types.add("row")
            
            assert source_types == {"column", "row"}, f"Cell {cell.uri} should be connected to both column and row"
    
    @pytest.mark.django_db
    def test_first_column_topology_creates_star_pattern(self, initial_data_empty, updater_polars_first_column_topology):
        """Test that first_column topology creates star pattern connections."""
        df = pl.DataFrame(simple_test_data)
        stats = updater_polars_first_column_topology.import_csv_with_smart_updates(df, "firstColumnTest")
        
        # Verify no row resources were created
        row_resources = Resource.objects.filter(uri__contains="/rows/")
        assert row_resources.count() == 0, "Should not create row resources in first_column mode"
        
        # Verify sameRow property was created
        same_row_prop = Resource.objects.filter(uri__contains="/properties/samerow").first()
        assert same_row_prop is not None, "Should create sameRow property"
        assert same_row_prop.name == "sameRow", "Property should be named 'sameRow'"
        
        # Verify star pattern: first column cells should connect to other cells in same row
        same_row_triples = Triple.objects.filter(predicate=same_row_prop)
        
        # With 2 rows and 4 columns each, expect 3 connections per row (first to other 3) = 6 total
        assert same_row_triples.count() == 6, f"Expected 6 star pattern connections, got {same_row_triples.count()}"
        
        # Verify first column cells (alphabetically first = "category") are the anchors
        first_column_cells = Resource.objects.filter(uri__contains="/category/")
        
        for first_cell in first_column_cells:
            # Each first column cell should be the subject of 3 sameRow triples
            outgoing_same_row = Triple.objects.filter(subject=first_cell, predicate=same_row_prop)
            assert outgoing_same_row.count() == 3, f"First column cell {first_cell.uri} should connect to 3 other cells"
    
    @pytest.mark.django_db
    def test_mesh_topology_creates_full_connectivity(self, initial_data_empty, updater_polars_mesh_topology):
        """Test that mesh topology creates full mesh connections."""
        df = pl.DataFrame(simple_test_data)
        stats = updater_polars_mesh_topology.import_csv_with_smart_updates(df, "meshTopologyTest")
        
        # Verify no row resources were created
        row_resources = Resource.objects.filter(uri__contains="/rows/")
        assert row_resources.count() == 0, "Should not create row resources in mesh mode"
        
        # Verify sameRow property was created
        same_row_prop = Resource.objects.filter(uri__contains="/properties/samerow").first()
        assert same_row_prop is not None, "Should create sameRow property"
        
        # Verify full mesh: each cell connects to every other cell in same row
        same_row_triples = Triple.objects.filter(predicate=same_row_prop)
        
        # With 2 rows and 4 columns each:
        # Per row: 4 cells = 4×3 = 12 bidirectional connections (each pair creates 2 triples)
        # Total: 2 rows × 12 = 24 connections
        assert same_row_triples.count() == 24, f"Expected 24 mesh connections, got {same_row_triples.count()}"
        
        # Verify bidirectional connections: if A→B exists, then B→A should also exist
        for triple in same_row_triples:
            reverse_triple = Triple.objects.filter(
                subject=triple.object,
                predicate=same_row_prop,
                object=triple.subject
            )
            assert reverse_triple.exists(), f"Missing reverse connection for {triple.subject.uri} → {triple.object.uri}"
    
    @pytest.mark.django_db
    def test_uri_based_row_tracking_works(self, initial_data_empty, updater_polars_column_only):
        """Test that row information is properly embedded in cell URIs."""
        df = pl.DataFrame(simple_test_data)
        stats = updater_polars_column_only.import_csv_with_smart_updates(df, "uriRowTest")
        
        # Test the helper methods for URI parsing
        updater = updater_polars_column_only
        
        # Get a sample cell URI
        cell_resource = Resource.objects.filter(uri__contains="/title/").first()
        assert cell_resource is not None, "Should find a title cell"
        
        # Test row ID extraction
        row_id = updater._extract_row_id_from_uri(cell_resource.uri)
        assert row_id in ["1", "2"], f"Expected row ID '1' or '2', got '{row_id}'"
        
        # Test column name extraction
        column_name = updater._extract_column_name_from_uri(cell_resource.uri)
        assert column_name == "title", f"Expected column name 'title', got '{column_name}'"
        
        # Verify all cells have proper URI structure
        cell_resources = Resource.objects.filter(uri__contains="/datasets/urirowtest/").exclude(uri__contains="/columns/")
        
        for cell in cell_resources:
            # URI should follow pattern: .../datasets/urirowtest/{column}/{row_id}
            parts = cell.uri.split('/')
            assert len(parts) >= 6, f"URI should have at least 6 parts: {cell.uri}"
            assert "datasets" in parts, f"URI should contain 'datasets': {cell.uri}"
            assert "urirowtest" in parts, f"URI should contain dataset name: {cell.uri}"
            
            # Last part should be row ID (1-based)
            row_part = parts[-1]
            assert row_part in ["1", "2"], f"Last URI part should be row ID '1' or '2': {cell.uri}"
    
    @pytest.mark.django_db
    def test_topology_logging_and_stats(self, initial_data_empty, updater_polars_mesh_topology, caplog):
        """Test that topology logging and statistics are correct."""
        import logging
        caplog.set_level(logging.INFO)
        
        df = pl.DataFrame(simple_test_data)
        stats = updater_polars_mesh_topology.import_csv_with_smart_updates(df, "loggingTest")
        
        # Check that topology-specific logging occurred
        log_messages = [record.message for record in caplog.records]
        topology_logs = [msg for msg in log_messages if "topology" in msg.lower()]
        
        assert len(topology_logs) > 0, "Should have topology-related log messages"
        
        # Verify stats include topology information
        assert stats.triples_created > 0, "Should have created triples"
        
        # Mesh topology should create many triples due to full connectivity
        # Expected: 4 dataset→column + 8 column→cell + 8 cell→value + 24 mesh = 44 total
        assert stats.triples_created == 44, f"Expected 44 triples for mesh topology, got {stats.triples_created}"
    
    @pytest.mark.django_db
    def test_column_resources_have_proper_uris_and_names(self, initial_data_empty, updater_polars_column_only):
        """Test that column resources have proper URIs and semantic names."""
        df = pl.DataFrame(simple_test_data)
        stats = updater_polars_column_only.import_csv_with_smart_updates(df, "columnSemanticTest")
        
        # Get column resources
        column_resources = Resource.objects.filter(uri__contains="/columns/")
        
        for column in column_resources:
            # Verify URI structure
            assert "/columns/" in column.uri, f"Column URI should contain '/columns/': {column.uri}"
            assert "columnsemantictest" in column.uri, f"Column URI should contain dataset name: {column.uri}"
            
            # Verify semantic names
            assert column.name in ["id", "title", "category", "year"], f"Column should have semantic name: {column.name}"
            
            # Verify resource type
            assert column.resource_type == ResourceType.IRI, f"Column should be IRI type: {column.resource_type}"
            
            # Verify source
            assert column.source == slugify_uri_part(INSTITUTION), f"Column should have proper source: {column.source}" 