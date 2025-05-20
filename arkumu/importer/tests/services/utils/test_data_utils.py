import pytest
import os
import tempfile
import unicodedata
from arkumu.importer.services.data_utils import (
    normalize_string_nfc,
    normalize_dict_values_nfc,
    normalize_csv_data_nfc,
    read_csv_with_nfc
)


class TestNFCNormalization:
    """Test the NFC normalization functions."""
    
    def test_normalize_string_nfc(self):
        """Test that strings are properly normalized to NFC form."""
        # Common examples with decomposed characters (NFD)
        decomposed = "café"  # 'é' as 'e' + combining accent
        # Create intentionally decomposed form for testing
        decomposed_nfd = unicodedata.normalize('NFD', decomposed)
        
        # Verify we actually have a decomposed string for testing
        assert len(decomposed_nfd) > len(decomposed), "Decomposed string didn't create properly for test"
        
        # Test normalization
        normalized = normalize_string_nfc(decomposed_nfd)
        assert normalized == decomposed
        assert len(normalized) == len(decomposed)
        assert unicodedata.normalize('NFC', decomposed_nfd) == normalized
        
        # Test normalization of already-normalized string (should be unchanged)
        already_normalized = "München"
        assert normalize_string_nfc(already_normalized) == already_normalized
        
        # Test normalization with a more complex example
        complex_str = "Überstraße in Köln"
        decomposed_complex = unicodedata.normalize('NFD', complex_str)
        assert normalize_string_nfc(decomposed_complex) == complex_str
        
        # Test non-string input
        assert normalize_string_nfc(None) is None
        assert normalize_string_nfc(123) == 123
        assert normalize_string_nfc([]) == []
        
    def test_normalize_dict_values_nfc(self):
        """Test normalizing dictionaries with string values."""
        # Create a dictionary with some decomposed strings
        decomposed_greeting = unicodedata.normalize('NFD', "Olá")
        decomposed_city = unicodedata.normalize('NFD', "São Paulo")
        
        test_dict = {
            "greeting": decomposed_greeting,
            "city": decomposed_city,
            "count": 42,  # Non-string value
            "items": ["a", "b"],  # Non-string value
            "nested": {"key": decomposed_city}  # Nested dict (should not normalize)
        }
        
        # Normalize the dictionary
        normalized_dict = normalize_dict_values_nfc(test_dict)
        
        # Check that string values are normalized
        assert normalized_dict["greeting"] == unicodedata.normalize('NFC', decomposed_greeting)
        assert normalized_dict["city"] == unicodedata.normalize('NFC', decomposed_city)
        
        # Check that non-string values are unchanged
        assert normalized_dict["count"] == 42
        assert normalized_dict["items"] == ["a", "b"]
        
        # Check that nested dictionaries are preserved but not normalized
        assert normalized_dict["nested"]["key"] == decomposed_city
        
    def test_normalize_csv_data_nfc(self):
        """Test normalizing a list of dictionaries (CSV data structure)."""
        # Create some test data with decomposed strings
        row1 = {
            "name": unicodedata.normalize('NFD', "José"),
            "city": unicodedata.normalize('NFD', "Montréal"),
            "age": 30
        }
        row2 = {
            "name": unicodedata.normalize('NFD', "François"),
            "city": unicodedata.normalize('NFD', "Zürich"),
            "age": 25
        }
        
        test_data = [row1, row2]
        
        # Normalize the data
        normalized_data = normalize_csv_data_nfc(test_data)
        
        # Check that string values are normalized
        assert normalized_data[0]["name"] == "José"
        assert normalized_data[0]["city"] == "Montréal"
        assert normalized_data[1]["name"] == "François"
        assert normalized_data[1]["city"] == "Zürich"
        
        # Check that non-string values are unchanged
        assert normalized_data[0]["age"] == 30
        assert normalized_data[1]["age"] == 25
        
    def test_read_csv_with_nfc(self):
        """Test reading a CSV file with NFC normalization."""
        # Create a temporary CSV file with decomposed characters
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False) as tmp:
            # Write CSV content with intentionally decomposed characters
            # Note: This test might be system-dependent, as file systems can normalize paths
            tmp.write("name;city;age\n")
            tmp.write(f"{unicodedata.normalize('NFD', 'María')};{unicodedata.normalize('NFD', 'México')};28\n")
            tmp.write(f"{unicodedata.normalize('NFD', 'Søren')};{unicodedata.normalize('NFD', 'København')};35\n")
            csv_path = tmp.name
        
        try:
            # Read the CSV with NFC normalization
            csv_data = read_csv_with_nfc(csv_path)
            
            # Check that we got the right number of rows
            assert len(csv_data) == 2
            
            # Check that string values are normalized
            assert csv_data[0]["name"] == "María"
            assert csv_data[0]["city"] == "México"
            assert csv_data[1]["name"] == "Søren"
            assert csv_data[1]["city"] == "København"
            
            # Check that non-string values are properly parsed
            assert csv_data[0]["age"] == "28"  # Note: CSV imports typically give strings
            assert csv_data[1]["age"] == "35"
            
            # Test with custom delimiter
            csv_data_comma = read_csv_with_nfc(csv_path, delimiter=";")
            assert len(csv_data_comma) == 2
            
        finally:
            # Clean up the temporary file
            try:
                os.unlink(csv_path)
            except:
                pass  # Ignore errors during cleanup
