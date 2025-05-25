import pytest
from arkumu.importer.services.importer.row_deduplicator import (
    RowDeduplicator, DuplicateStrategy
)


class TestRowDeduplicator:
    """Test the row deduplication functionality."""
    
    def test_exact_duplicate_detection(self):
        """Test detection of exact duplicate rows."""
        deduplicator = RowDeduplicator()
        
        row_data = {
            "id": "123",
            "name": "Test Project",
            "status": "active"
        }
        
        # Process same row twice
        hash1, result1 = deduplicator.process_row(row_data, "test.csv", 1)
        hash2, result2 = deduplicator.process_row(row_data, "test.csv", 2)
        
        assert not result1.is_duplicate
        assert result2.is_duplicate
        assert result2.strategy == DuplicateStrategy.SKIP
        assert "Exact duplicate" in result2.reason
    
    def test_row_order_independence(self):
        """Test that different row orders produce same hash."""
        deduplicator = RowDeduplicator()
        
        # Same data, different order in CSV
        row1 = {"A": "value1", "B": "value2", "C": "value3"}
        row2 = {"C": "value3", "A": "value1", "B": "value2"}  # Different column order
        
        hash1 = deduplicator.generate_row_hash(row1, "file1.csv", 1)
        hash2 = deduplicator.generate_row_hash(row2, "file2.csv", 1)
        
        # Should have same content hash (order-independent)
        assert hash1.content_hash == hash2.content_hash
    
    def test_whitespace_handling(self):
        """Test that whitespace is cleaned consistently."""
        deduplicator = RowDeduplicator()
        
        row1 = {"name": "Test Project", "desc": "A description"}
        row2 = {"name": " Test Project ", "desc": " A description "}  # Extra whitespace
        
        hash1, result1 = deduplicator.process_row(row1, "test.csv", 1)
        hash2, result2 = deduplicator.process_row(row2, "test.csv", 2)
        
        assert not result1.is_duplicate
        # Should detect as exact duplicate after whitespace cleaning
        assert result2.is_duplicate
        assert result2.strategy == DuplicateStrategy.SKIP
    
    def test_timestamp_based_updates(self):
        """Test handling of updates based on timestamps."""
        deduplicator = RowDeduplicator(
            timestamp_columns=["last_modified"]
        )
        
        # Older version
        row1 = {
            "id": "123",
            "name": "Test Project",
            "last_modified": "2024-01-01 10:00:00"
        }
        
        # Newer version (same content, newer timestamp)
        row2 = {
            "id": "123",
            "name": "Test Project",
            "last_modified": "2024-01-02 10:00:00"
        }
        
        hash1, result1 = deduplicator.process_row(row1, "test.csv", 1)
        hash2, result2 = deduplicator.process_row(row2, "test.csv", 2)
        
        assert not result1.is_duplicate
        assert result2.is_duplicate
        assert result2.strategy == DuplicateStrategy.UPDATE
        assert "Newer version" in result2.reason
    
    def test_exclude_columns(self):
        """Test that excluded columns don't affect hash."""
        deduplicator = RowDeduplicator(exclude_columns=["timestamp", "auto_id"])
        
        row1 = {
            "id": "123",
            "name": "Test",
            "timestamp": "2024-01-01",
            "auto_id": "auto_123"
        }
        
        row2 = {
            "id": "123",
            "name": "Test",
            "timestamp": "2024-01-02",  # Different timestamp
            "auto_id": "auto_456"       # Different auto ID
        }
        
        hash1 = deduplicator.generate_row_hash(row1, "test.csv", 1)
        hash2 = deduplicator.generate_row_hash(row2, "test.csv", 2)
        
        # Should have same hash since excluded columns are ignored
        assert hash1.content_hash == hash2.content_hash
    
    def test_empty_value_handling(self):
        """Test consistent handling of empty/null values."""
        deduplicator = RowDeduplicator()
        
        row1 = {"id": "123", "name": "Test", "desc": ""}
        row2 = {"id": "123", "name": "Test", "desc": None}
        row3 = {"id": "123", "name": "Test", "desc": "null"}
        row4 = {"id": "123", "name": "Test", "desc": "N/A"}
        
        hash1 = deduplicator.generate_row_hash(row1, "test.csv", 1)
        hash2 = deduplicator.generate_row_hash(row2, "test.csv", 2)
        hash3 = deduplicator.generate_row_hash(row3, "test.csv", 3)
        hash4 = deduplicator.generate_row_hash(row4, "test.csv", 4)
        
        # All should have same hash (empty values normalized)
        assert hash1.content_hash == hash2.content_hash == hash3.content_hash == hash4.content_hash
    
    def test_statistics(self):
        """Test statistics generation."""
        deduplicator = RowDeduplicator()
        
        # Add some rows with duplicates
        rows = [
            {"id": "1", "name": "Project A"},
            {"id": "2", "name": "Project B"},
            {"id": "1", "name": "Project A"},  # Exact duplicate
            {"id": "2", "name": "Project B"},  # Another exact duplicate
        ]
        
        for i, row in enumerate(rows):
            deduplicator.process_row(row, "test.csv", i + 1)
        
        stats = deduplicator.get_statistics()
        
        assert stats["total_unique_rows"] == 2  # 2 unique content hashes
        assert stats["duplicate_rate"] == 0.0  # We don't track duplicates in statistics
        assert isinstance(stats["duplicate_rate"], float)
    
    def test_timestamp_exclusion_configuration(self):
        """Test that timestamp columns can be excluded from hash."""
        deduplicator = RowDeduplicator(
            timestamp_columns=["Pr_AenderungsTS", "_TS_LastModified"]
        )
        
        # Test that timestamp columns are excluded from hash
        row_with_timestamps = {
            "Projekt_ID": "5570",
            "Originaltitel": "Test Project",
            "Pr_AenderungsTS": "2024-01-01 10:00:00",
            "_TS_LastModified": "2024-01-01 10:00:00"
        }
        
        row_without_timestamps = {
            "Projekt_ID": "5570",
            "Originaltitel": "Test Project"
        }
        
        hash1 = deduplicator.generate_row_hash(row_with_timestamps, "test.csv", 1)
        hash2 = deduplicator.generate_row_hash(row_without_timestamps, "test.csv", 2)
        
        # Should have same hash since timestamps are excluded
        assert hash1.content_hash == hash2.content_hash
    
    def test_different_csv_file_orders(self):
        """Test realistic scenario: same data from different CSV file orders."""
        deduplicator = RowDeduplicator()
        
        # Simulate CSV file 1 (original order)
        csv1_rows = [
            {"Projekt_ID": "5570", "Titel": "Project A", "Status": "Active"},
            {"Projekt_ID": "5571", "Titel": "Project B", "Status": "Inactive"},
            {"Projekt_ID": "5572", "Titel": "Project C", "Status": "Active"},
        ]
        
        # Simulate CSV file 2 (different row order, same data)
        csv2_rows = [
            {"Projekt_ID": "5571", "Titel": "Project B", "Status": "Inactive"},  # Row 2 from CSV1
            {"Projekt_ID": "5572", "Titel": "Project C", "Status": "Active"},    # Row 3 from CSV1
            {"Projekt_ID": "5570", "Titel": "Project A", "Status": "Active"},    # Row 1 from CSV1
        ]
        
        # Process first CSV
        results1 = []
        for i, row in enumerate(csv1_rows):
            hash_obj, result = deduplicator.process_row(row, "projects_v1.csv", i + 1)
            results1.append(result)
        
        # Process second CSV (should all be duplicates)
        results2 = []
        for i, row in enumerate(csv2_rows):
            hash_obj, result = deduplicator.process_row(row, "projects_v2.csv", i + 1)
            results2.append(result)
        
        # First CSV: no duplicates
        assert all(not result.is_duplicate for result in results1)
        
        # Second CSV: all duplicates
        assert all(result.is_duplicate for result in results2)
        assert all(result.strategy == DuplicateStrategy.SKIP for result in results2)
        
        # Verify statistics
        stats = deduplicator.get_statistics()
        assert stats["total_unique_rows"] == 3  # Only 3 unique rows despite processing 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 