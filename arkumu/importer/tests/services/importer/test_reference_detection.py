import pytest
from arkumu.importer.services.importer.reference_resolver import ReferenceResolver


class TestReferenceDetection:
    """Test our generic reference detection logic"""
    
    def test_reference_column_detection(self):
        """Test that reference columns are correctly identified"""
        
        test_cases = [
            # (column_name, value, expected_result, description)
            ("project_id", "PROJ001", True, "Standard _id suffix"),
            ("assignee_id", "EMP001", True, "Standard _id suffix"),
            ("user_id", "123", True, "Numeric ID with _id suffix"),
            ("category_ref", "CAT001", True, "Reference suffix"),
            ("owner_key", "USR123", True, "Key suffix"),
            ("id_parent", "TASK001", True, "ID prefix"),
            ("ref_category", "CAT001", True, "Ref prefix"),
            
            # Should NOT be detected as references
            ("id", "PROJ001", False, "Primary key column"),
            ("name", "John Doe", False, "Regular text field"),
            ("status", "Active", False, "Regular text field"),
            ("description", "Some long description", False, "Long text field"),
            ("email", "test@example.com", False, "Email field"),
            ("created_at", "2023-01-01", False, "Date field"),
            ("parent_task", "TASK001", False, "Compound name without clear reference pattern"),
        ]
        
        for column_name, value, expected, description in test_cases:
            result = ReferenceResolver.is_reference_column(column_name, value)
            assert result == expected, f"Failed for {column_name}='{value}' ({description}): expected {expected}, got {result}"
    
    def test_reference_parsing(self):
        """Test that references are correctly parsed to extract table and ID"""
        
        test_cases = [
            # (column_name, value, expected_table, expected_id)
            ("project_id", "PROJ001", "project", "PROJ001"),
            ("assignee_id", "EMP001", "assignee", "EMP001"),
            ("user_id", "123", "user", "123"),
            ("category_ref", "CAT001", "category", "CAT001"),
            ("owner_key", "USR123", "owner", "USR123"),
            ("id_parent", "TASK001", "parent", "TASK001"),
            ("ref_category", "CAT001", "category", "CAT001"),
        ]
        
        for column_name, value, expected_table, expected_id in test_cases:
            target_table, target_id = ReferenceResolver.parse_reference(column_name, value)
            assert target_table == expected_table, f"Table parsing failed for {column_name}: expected '{expected_table}', got '{target_table}'"
            assert target_id == expected_id, f"ID parsing failed for {column_name}: expected '{expected_id}', got '{target_id}'"
    
    def test_edge_cases(self):
        """Test edge cases and invalid inputs"""
        
        # Empty/None inputs
        assert ReferenceResolver.is_reference_column("", "value") == False
        assert ReferenceResolver.is_reference_column("column", "") == False
        assert ReferenceResolver.is_reference_column(None, "value") == False
        assert ReferenceResolver.is_reference_column("column", None) == False
        
        # Parse reference edge cases
        assert ReferenceResolver.parse_reference("", "value") == (None, None)
        assert ReferenceResolver.parse_reference("column", "") == (None, None)
        assert ReferenceResolver.parse_reference("id", "123") == (None, None)  # Primary key
    
    def test_id_value_detection(self):
        """Test the _looks_like_id_value helper method"""
        
        id_values = [
            "123",           # Numeric
            "PROJ001",       # Alphanumeric with prefix
            "EMP-001",       # With separator
            "abc123",        # Mixed
            "UUID-123-456",  # UUID-like
        ]
        
        non_id_values = [
            "John Doe",                    # Name
            "test@example.com",           # Email
            "This is a long description", # Long text
            "",                           # Empty
            "a" * 101,                    # Too long
        ]
        
        for value in id_values:
            assert ReferenceResolver._looks_like_id_value(value), f"'{value}' should be detected as ID-like"
        
        for value in non_id_values:
            assert not ReferenceResolver._looks_like_id_value(value), f"'{value}' should NOT be detected as ID-like"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 