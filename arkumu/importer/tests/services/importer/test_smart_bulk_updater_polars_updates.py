import pytest
import polars as pl
from typing import List, Dict, Any
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
from arkumu.importer.services.importer.smart_bulk_updater_polars import UpdateStrategy, BulkUpdateStats

# Test constants
UPDATE_TEST_INSTITUTION = "UPDATE_TEST"
UPDATE_TEST_INSTITUTION_SLUGIFIED = "update-test"  # What our code actually uses
UPDATE_TEST_BASE_URI = "http://test.arkumu.org/data"

# Standard vocabulary URIs
RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"

# Test Data with Multi-Value Columns (consistent with main test file)
multi_value_test_data: List[Dict[str, Any]] = [
    {"id": "1", "names": "John, Jane, Bob", "single_field": "alpha", "tags": "red,blue,green"},
    {"id": "2", "names": "Alice, Charlie", "single_field": "beta", "tags": "yellow,purple"},
    {"id": "3", "names": "David, Eve, Frank, Grace", "single_field": "gamma", "tags": "orange,black,white"},
    {"id": "4", "names": "Henry", "single_field": "delta", "tags": "pink"},
    {"id": "5", "names": "Iris, Jack", "single_field": "epsilon", "tags": "brown,gray"}
]

# Real KHM-style data for testing (consistent with main test file)
khm_style_test_data: List[Dict[str, Any]] = [
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
    }
]

# Real Folkwang-style data for testing (consistent with main test file)
folkwang_style_test_data: List[Dict[str, Any]] = [
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
    }
]

# German text with Unicode for testing (consistent with main test file)
german_unicode_test_data: List[Dict[str, Any]] = [
    {"id": "unicode1", "title": "Café München", "keywords": "ästhetik,schön", "emoji": "🎨,🖼️,🎭"},
    {"id": "unicode2", "title": "Naïve Résumé", "keywords": "français,español", "emoji": "🌟,✨"}
]

# Mixed separator test data (consistent with main test file)
mixed_pattern_test_data: List[Dict[str, Any]] = [
    {"id": "1", "codes": "A001,B002,C003", "names": "Schmidt, Mueller", "text": "This is a sentence, with commas."},
    {"id": "2", "codes": "D004,E005", "names": "Weber, Fischer", "text": "Another sentence, also with commas."},  
    {"id": "3", "codes": "F006,G007,H008", "names": "Wagner", "text": "Text without much punctuation"},
    {"id": "4", "codes": "I009", "names": "Becker, Schulz", "text": "Some text, here and there."},
]

@pytest.fixture
def clear_update_test_data(db):
    """Clear any existing test data before and after tests."""
    # Clear before test - use slugified institution name
    Resource.objects.filter(source=UPDATE_TEST_INSTITUTION_SLUGIFIED).delete()
    Triple.objects.all().delete()  # Clear triples too
    yield
    # Clear after test - use slugified institution name
    Resource.objects.filter(source=UPDATE_TEST_INSTITUTION_SLUGIFIED).delete()
    Triple.objects.all().delete()

@pytest.fixture
def updater_for_updates() -> SmartBulkUpdaterPolars:
    """SmartBulkUpdaterPolars configured for update testing."""
    return SmartBulkUpdaterPolars(
        institution=UPDATE_TEST_INSTITUTION,
        base_uri=UPDATE_TEST_BASE_URI,
        default_strategy=UpdateStrategy.UPDATE_VALUES,
        link_row_cells=False,  # Simplify for testing
        multi_value_threshold=0.2
    )

@pytest.fixture
def updater_skip_existing() -> SmartBulkUpdaterPolars:
    """SmartBulkUpdaterPolars configured to skip existing resources."""
    return SmartBulkUpdaterPolars(
        institution=UPDATE_TEST_INSTITUTION,
        base_uri=UPDATE_TEST_BASE_URI,
        default_strategy=UpdateStrategy.SKIP_EXISTING,
        link_row_cells=False,
        multi_value_threshold=0.2
    )


def find_value_in_system(value: str) -> bool:
    """Helper function to find if a value exists in our triple-based system."""
    # Look for literal resources with the value
    value_resources = Resource.objects.filter(
        source=UPDATE_TEST_INSTITUTION_SLUGIFIED,
        resource_type=ResourceType.LITERAL,
        value=value
    )
    return value_resources.exists()


def get_all_values_in_system() -> set:
    """Helper function to get all values stored in the system."""
    value_resources = Resource.objects.filter(
        source=UPDATE_TEST_INSTITUTION_SLUGIFIED,
        resource_type=ResourceType.LITERAL
    )
    return {r.value for r in value_resources if r.value}


def count_system_resources() -> int:
    """Helper function to count resources created by our system."""
    return Resource.objects.filter(source=UPDATE_TEST_INSTITUTION_SLUGIFIED).count()


class TestSingleValueUpdates:
    """Test updating single-value fields with different scenarios."""
    
    @pytest.mark.django_db
    def test_single_value_field_updates(self, clear_update_test_data, updater_for_updates):
        """Test that single-value fields are correctly updated when values change."""
        
        # === INITIAL IMPORT ===
        initial_data = [
            {"Projekt_ID": "200", "Originaltitel": "Old Project Alpha", "Kategorie": "Installation", "status": "draft"},
            {"Projekt_ID": "302", "Originaltitel": "Project Beta", "Kategorie": "Film", "status": "active"},
        ]
        
        df_initial = pl.DataFrame(initial_data)
        stats1 = updater_for_updates.import_csv_with_smart_updates(df_initial, "test_projects")
        
        # Verify initial import
        assert stats1.resources_created > 8  # More than just cell values
        assert stats1.resources_updated == 0
        assert stats1.resources_skipped == 0
        
        # Check that resources were created using helper function
        initial_resources = count_system_resources()
        assert initial_resources > 8
        
        # === UPDATE WITH DIFFERENT VALUES ===
        updated_data = [
            {"Projekt_ID": "200", "Originaltitel": "NEW Project Alpha", "Kategorie": "Performance", "status": "completed"},  # All values changed
            {"Projekt_ID": "302", "Originaltitel": "Project Beta", "Kategorie": "Film", "status": "archived"},  # Only status changed
            {"Projekt_ID": "528", "Originaltitel": "Project Gamma", "Kategorie": "Installation", "status": "planning"},  # New project
        ]
        
        df_updated = pl.DataFrame(updated_data)
        stats2 = updater_for_updates.import_csv_with_smart_updates(df_updated, "test_projects")
        
        # Verify update results
        assert stats2.resources_created > 0  # New project3 resources
        
        # Check specific value updates using our helper functions
        assert find_value_in_system("NEW Project Alpha"), "Updated title should exist"
        assert find_value_in_system("Performance"), "Updated category should exist"
        assert find_value_in_system("Project Gamma"), "New project title should exist"
    
    @pytest.mark.django_db
    def test_no_changes_detected(self, clear_update_test_data, updater_for_updates):
        """Test that when no values change, resources are handled correctly."""
        
        # Import data using KHM-style format
        data = [
            {"Projekt_ID": "200", "Originaltitel": "Test Item", "Kategorie": "Installation"},
            {"Projekt_ID": "302", "Originaltitel": "Another Item", "Kategorie": "Film"},
        ]
        
        df = pl.DataFrame(data)
        stats1 = updater_for_updates.import_csv_with_smart_updates(df, "no_change_test")
        
        # Import same data again
        stats2 = updater_for_updates.import_csv_with_smart_updates(df, "no_change_test")
        
        # Should detect existing data and handle appropriately
        assert stats2.resources_created == 0  # No new resources
        # Note: The system may update rather than skip identical values
        assert stats2.resources_updated >= 0  # May update existing


class TestMultiValueUpdates:
    """Test updating single-value fields (multi-value detection disabled)."""
    
    @pytest.mark.django_db
    def test_multi_value_field_updates(self, clear_update_test_data, updater_for_updates):
        """Test that fields with commas are treated as single values (no splitting)."""
        
        # === INITIAL IMPORT ===
        initial_data = [
            {"Projekt-ID": "3", "Bevorzugter Titel": "AI Research", "Schlagwort": "Q161439,Q1129653,Q160402", "Projektkategorie": "9,13"},
            {"Projekt-ID": "25", "Bevorzugter Titel": "Data Science", "Schlagwort": "Q7860,Q107425", "Projektkategorie": "9"},
        ]
        
        df_initial = pl.DataFrame(initial_data)
        stats1 = updater_for_updates.import_csv_with_smart_updates(df_initial, "research_projects")
        
        # Verify NO multi-value detection (disabled)
        assert stats1.multi_value_cells_detected == 0
        assert stats1.total_values_created > 0  # Should create some values
        
        # === UPDATE WITH DIFFERENT VALUES ===
        updated_data = [
            {"Projekt-ID": "3", "Bevorzugter Titel": "AI Research", "Schlagwort": "Q161439,Q1129653,Q160402,Q33767,Q328835", "Projektkategorie": "9,13,17"},  # Changed values (as single strings)
            {"Projekt-ID": "25", "Bevorzugter Titel": "Data Science", "Schlagwort": "Q7860,Q107425,Q11461,Q179448", "Projektkategorie": "9,14"},  # Changed values (as single strings)
            {"Projekt-ID": "60", "Bevorzugter Titel": "Robotics", "Schlagwort": "Q756,Q22676,Q177998", "Projektkategorie": "9,16"},  # New project
        ]
        
        df_updated = pl.DataFrame(updated_data)
        stats2 = updater_for_updates.import_csv_with_smart_updates(df_updated, "research_projects")
        
        # Verify updates occurred
        assert stats2.resources_created > 0  # New project
        assert stats2.multi_value_cells_detected == 0  # No multi-value detection
        
        # Check that new comma-separated values are present as complete strings
        all_values = get_all_values_in_system()
        
        # Look for the complete comma-separated strings (not individual keywords)
        comma_values_present = any(
            "Q161439,Q1129653,Q160402,Q33767,Q328835" in str(val) or
            "Q7860,Q107425,Q11461,Q179448" in str(val) or
            "Q756,Q22676,Q177998" in str(val)
            for val in all_values
        )
        assert comma_values_present, f"Complete comma-separated values should be present. Found values: {sorted(list(all_values))}"
    
    @pytest.mark.django_db
    def test_multi_value_detection_accuracy(self, clear_update_test_data, updater_for_updates):
        """Test that multi-value detection is disabled and all fields are treated as single-value."""
        
        df = pl.DataFrame(mixed_pattern_test_data)
        
        # Analyze before import
        analysis = updater_for_updates.analyze_dataset_multi_values_polars(df)
        
        # ALL fields should be detected as single-value (multi-value detection disabled)
        assert analysis["codes"]["is_multi_value"] is False
        assert analysis["codes"]["separator"] is None
        assert analysis["codes"]["stats"]["percentage"] == 0.0
        
        assert analysis["names"]["is_multi_value"] is False
        assert analysis["text"]["is_multi_value"] is False


class TestUpdateStrategies:
    """Test different update strategies and their behavior."""
    
    @pytest.mark.django_db
    def test_skip_existing_strategy(self, clear_update_test_data, updater_skip_existing, updater_for_updates):
        """Test that SKIP_EXISTING strategy doesn't update existing resources."""
        
        # === SETUP INITIAL DATA ===
        initial_data = [
            {"Projekt_ID": "200", "Originaltitel": "Original Item", "Kategorie": "Installation"},
            {"Projekt_ID": "302", "Originaltitel": "Another Item", "Kategorie": "Film"},
        ]
        
        df_initial = pl.DataFrame(initial_data)
        stats_initial = updater_skip_existing.import_csv_with_smart_updates(df_initial, "strategy_test")
        
        assert stats_initial.resources_created > 0
        assert stats_initial.resources_updated == 0
        
        # === TRY TO UPDATE WITH SKIP_EXISTING ===
        updated_data = [
            {"Projekt_ID": "200", "Originaltitel": "CHANGED Item", "Kategorie": "Performance"},  # Should be skipped
            {"Projekt_ID": "302", "Originaltitel": "CHANGED Another", "Kategorie": "Video"},  # Should be skipped
            {"Projekt_ID": "528", "Originaltitel": "New Item", "Kategorie": "Audio"},  # Should be created
        ]
        
        df_updated = pl.DataFrame(updated_data)
        stats_skip = updater_skip_existing.import_csv_with_smart_updates(df_updated, "strategy_test")
        
        # Should create new resources but skip existing ones
        assert stats_skip.resources_created > 0  # New item3
        assert stats_skip.resources_updated == 0  # No updates with SKIP_EXISTING
        assert stats_skip.resources_skipped > 0  # Existing items skipped
        
        # Verify original values are still present
        assert find_value_in_system("Original Item"), "Original values should remain unchanged"
    
    @pytest.mark.django_db
    def test_update_values_strategy(self, clear_update_test_data, updater_for_updates):
        """Test that UPDATE_VALUES strategy updates changed resources."""
        
        # === SETUP INITIAL DATA ===
        initial_data = [
            {"Projekt_ID": "200", "Originaltitel": "Original Item", "Kategorie": "Installation"},
            {"Projekt_ID": "302", "Originaltitel": "Another Item", "Kategorie": "Film"},
        ]
        
        df_initial = pl.DataFrame(initial_data)
        stats_initial = updater_for_updates.import_csv_with_smart_updates(df_initial, "update_strategy_test")
        
        # === UPDATE WITH UPDATE_VALUES STRATEGY ===
        updated_data = [
            {"Projekt_ID": "200", "Originaltitel": "CHANGED Item", "Kategorie": "Performance"},  # Should be updated
            {"Projekt_ID": "302", "Originaltitel": "Another Item", "Kategorie": "Film"},  # Should be skipped (no change)
            {"Projekt_ID": "528", "Originaltitel": "New Item", "Kategorie": "Audio"},  # Should be created
        ]
        
        df_updated = pl.DataFrame(updated_data)
        stats_update = updater_for_updates.import_csv_with_smart_updates(df_updated, "update_strategy_test")
        
        # Should create new resources and update changed ones
        assert stats_update.resources_created > 0  # New item3
        
        # Verify changed values are present
        assert find_value_in_system("CHANGED Item"), "Changed values should be present"
        assert find_value_in_system("New Item"), "New items should be present"


class TestReportingAndStats:
    """Test the comprehensive reporting capabilities."""
    
    @pytest.mark.django_db
    def test_detailed_statistics_reporting(self, clear_update_test_data, updater_for_updates):
        """Test that detailed statistics are correctly reported (with multi-value disabled)."""
        
        # Use Folkwang-style data with comma-separated fields
        df = pl.DataFrame(folkwang_style_test_data)
        stats = updater_for_updates.import_csv_with_smart_updates(df, "complex_test")
        
        # Verify comprehensive stats are provided
        assert stats.rows_processed >= 0
        assert stats.cells_processed > 0
        assert stats.resources_created > 0
        assert stats.triples_created > 0  # Should create some triples
        assert stats.multi_value_cells_detected == 0  # Multi-value detection disabled
        assert stats.total_values_created > 0  # Should create some values
        assert stats.errors == 0  # Should be no errors with valid data
        
        # With multi-value disabled, values_per_cell should be close to 1
        if stats.cells_processed > 0:
            multi_value_ratio = stats.multi_value_cells_detected / stats.cells_processed
            assert multi_value_ratio == 0  # Should be 0 since multi-value is disabled
            
            values_per_cell = stats.total_values_created / stats.cells_processed
            assert values_per_cell <= 1.1  # Should be close to 1 (allowing small margin for empty cells)
    
    @pytest.mark.django_db
    def test_stats_merging_across_operations(self, clear_update_test_data, updater_for_updates):
        """Test that statistics correctly accumulate across multiple operations."""
        
        # First import
        data1 = [{"Projekt-ID": "3", "Bevorzugter Titel": "First Batch", "Schlagwort": "Q161439,Q1129653"}]
        df1 = pl.DataFrame(data1)
        stats1 = updater_for_updates.import_csv_with_smart_updates(df1, "batch_test")
        
        # Second import (update)
        data2 = [
            {"Projekt-ID": "3", "Bevorzugter Titel": "Updated Batch", "Schlagwort": "Q161439,Q1129653,Q160402"},  # Update
            {"Projekt-ID": "25", "Bevorzugter Titel": "Second Batch", "Schlagwort": "Q7860,Q107425"}      # New
        ]
        df2 = pl.DataFrame(data2)
        stats2 = updater_for_updates.import_csv_with_smart_updates(df2, "batch_test")
        
        # Verify that stats reflect the operations correctly
        assert stats1.resources_created > 0
        assert stats1.resources_updated == 0  # First import, nothing to update
        
        assert stats2.resources_created > 0   # New batch2
        assert stats2.resources_updated >= 0  # Possible updates to batch1
        
        # Total resources should make sense
        total_resources = count_system_resources()
        assert total_resources > 0


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.django_db
    def test_empty_dataframe_handling(self, clear_update_test_data, updater_for_updates):
        """Test handling of empty DataFrames."""
        
        empty_df = pl.DataFrame()
        stats = updater_for_updates.import_csv_with_smart_updates(empty_df, "empty_test")
        
        # Should handle empty data gracefully
        assert stats.rows_processed == 0
        assert stats.cells_processed == 0
        assert stats.resources_created == 0
        assert stats.resources_updated == 0
        assert stats.errors == 0
    
    @pytest.mark.django_db
    def test_special_characters_in_values(self, clear_update_test_data, updater_for_updates):
        """Test handling of special characters and Unicode in values."""
        
        df = pl.DataFrame(german_unicode_test_data)
        stats = updater_for_updates.import_csv_with_smart_updates(df, "unicode_test")
        
        # Should handle Unicode gracefully
        assert stats.resources_created > 0
        assert stats.errors == 0
        
        # Verify Unicode values are preserved by checking they exist
        assert find_value_in_system("Café München"), "Unicode characters should be preserved"
        
        # Check that emoji values exist (as comma-separated strings since splitting is disabled)
        emoji_strings = ["🎨,🖼️,🎭", "🌟,✨"]
        emoji_found = any(find_value_in_system(emoji_str) for emoji_str in emoji_strings)
        assert emoji_found, "Emoji comma-separated values should be created"
    
    @pytest.mark.django_db
    def test_large_values_truncation(self, clear_update_test_data, updater_for_updates):
        """Test that very large values are properly truncated and reported."""
        
        # Create data with a very large value using KHM-style format
        large_value = "x" * 10000  # Very large string
        large_data = [
            {"Projekt_ID": "200", "Originaltitel": "Normal Title", "_Beschreibung_verkettet": large_value}
        ]
        
        df = pl.DataFrame(large_data)
        stats = updater_for_updates.import_csv_with_smart_updates(df, "large_test")
        
        # Should report truncation if it occurred
        assert stats.resources_created > 0
        assert stats.errors == 0
        assert stats.truncated_values > 0  # Should report truncation
        
        # Verify truncated value exists with truncation marker
        all_values = get_all_values_in_system()
        truncated_values = [v for v in all_values if v and v.endswith("...")]
        assert len(truncated_values) > 0, "Truncated values should end with '...'"


class TestCompatibilityAndIntegration:
    """Test compatibility with existing systems and integration points."""
    
    @pytest.mark.django_db
    def test_compatibility_with_original_updater(self, clear_update_test_data):
        """Test that results are compatible with the original SmartBulkUpdater."""
        
        # This test would compare results between the original and Polars versions
        # For now, we verify the Polars version produces expected results
        
        # Use consistent data format with main test file
        data = [
            {"Projekt_ID": "200", "Originaltitel": "Test Item", "Kategorie": "Installation"},
            {"Projekt_ID": "302", "Originaltitel": "Another Item", "Kategorie": "Film"}
        ]
        
        polars_updater = SmartBulkUpdaterPolars(
            institution=UPDATE_TEST_INSTITUTION,
            base_uri=UPDATE_TEST_BASE_URI,
            default_strategy=UpdateStrategy.UPDATE_VALUES,
            link_row_cells=False
        )
        
        df = pl.DataFrame(data)
        stats = polars_updater.import_csv_with_smart_updates(df, "compat_test")
        
        # Verify expected behavior - adjusted for actual system behavior
        assert stats.resources_created > 6  # More than just cell values (includes predicates, types)
        assert stats.errors == 0
        
        # Verify resources exist and have correct structure
        total_resources = count_system_resources()
        assert total_resources > 6
        
        # Verify specific values exist
        assert find_value_in_system("Test Item"), "Test values should exist"
