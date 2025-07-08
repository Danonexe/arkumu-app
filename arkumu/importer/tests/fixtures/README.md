# Test Fixtures for Arkumu Importer

This directory contains test fixtures for the Arkumu importer services tests.

## Directory Structure

```
fixtures/
├── mappings/           # JSON mapping configurations
│   ├── simple_mapping.json      # Basic person mapping
│   └── complex_mapping.json     # Complex event mapping with relationships
└── data/               # Test CSV data files
    ├── person_data.csv          # Simple person data
    ├── events_data.csv          # Event data with relationships
    ├── complex_data.csv         # Complex data with various types
    └── invalid_data.csv         # Data with validation errors
```

## Mapping Fixtures

### simple_mapping.json
- Basic person mapping with name, age, location
- Simple ontology mapping to CIDOC-CRM classes
- One relationship (person-location)
- Validation status: validated

### complex_mapping.json  
- Complex event mapping with multiple columns and relationships
- Multiple data types (string, date, integer, text)
- Three relationships between events, participants, and locations
- Validation rules for dates and durations
- Validation status: validated

## Data Fixtures

### person_data.csv
- 10 rows of person data (name, age, location)
- Semicolon-separated values
- Clean data for successful imports

### events_data.csv
- 10 rows of event data with dates, locations, participants
- Matches the complex_mapping.json structure
- Includes duration in minutes

### complex_data.csv
- 10 rows with various data types
- Includes ID, dates, booleans, floating point numbers
- Tags and categories for testing complex mappings

### invalid_data.csv
- 10 rows with various data validation errors
- Invalid ages, missing names, empty locations
- Useful for testing error handling and validation

## Usage in Tests

These fixtures can be loaded in tests using the provided conftest.py fixtures:

```python
def test_with_fixtures(mapping_fixtures_path, data_fixtures_path):
    # Load mapping fixture
    mapping_path = mapping_fixtures_path / "simple_mapping.json"
    with open(mapping_path) as f:
        mapping_config = json.load(f)
    
    # Load data fixture
    data_path = data_fixtures_path / "person_data.csv"
    with open(data_path) as f:
        csv_data = f.read()
```

Or use the factory methods in conftest.py to create test objects based on these fixtures.