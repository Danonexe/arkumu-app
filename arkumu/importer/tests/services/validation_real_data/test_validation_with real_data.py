import pytest
import os
from pathlib import Path

from arkumu.importer.services.validation import MappingValidator, validate_mapping
from arkumu.importer.services.validation_utils import ValidationReport


def test_validation_with_sample_data(validator, sample_mapping_file, sample_csv_file, sample_related_data_dir):
    """Test validation with sample data from fixtures."""
    print(f"\nValidating mapping file: {sample_mapping_file}")
    print(f"CSV file: {sample_csv_file}")
    print(f"Related data dir: {sample_related_data_dir}")
    
    # Test basic structure validation
    structure_report = validator.validate_mapping_file(sample_mapping_file)
    print(f"\nStructure validation report:\n{structure_report.summary()}")
    assert structure_report.is_valid, "Mapping file structure should be valid"
    
    # Test validation against CSV data
    data_report = validator.validate_mapping_against_data(sample_mapping_file, sample_csv_file)
    print(f"\nData validation report:\n{data_report.summary()}")
    assert data_report.is_valid, "Mapping against CSV should be valid"
    
    # Test reference validation - expect failure due to missing ref3
    reference_report = validator.validate_references(
        sample_mapping_file, 
        sample_csv_file,
        data_dir=sample_related_data_dir
    )
    print(f"\nReference validation report:\n{reference_report.summary()}")
    
    # Should fail due to missing reference - ref3
    assert not reference_report.is_valid, "Reference validation should fail with intentionally missing reference"
    assert any(error.error_type == "INVALID_REFERENCE" for error in reference_report.errors), "Should have invalid reference error"


def test_convenience_function(sample_mapping_file, sample_csv_file, sample_related_data_dir):
    """Test the convenience function for validation."""
    # Non-strict validation (still fails on errors, but ignores warnings)
    result = validate_mapping(
        sample_mapping_file,
        sample_csv_file,
        data_dir=sample_related_data_dir,
        strict=False
    )
    
    # Should fail when errors are present, regardless of strict mode
    assert result is False
    
    # Strict validation (fails on both errors and warnings)
    result = validate_mapping(
        sample_mapping_file,
        sample_csv_file,
        data_dir=sample_related_data_dir,
        strict=True
    )
    
    # Should also fail with errors present
    assert result is False


@pytest.mark.django_db
def test_external_mapping_validation(external_mapping_file, external_csv_file, external_data_dir, validator):
    """
    Test validation with external files provided via command line or environment variables.
    
    This test is skipped if the external files are not provided.
    Uses django_db mark to allow database access for reference validation.
    """
    try:
        mapping_file = external_mapping_file()
        csv_file = external_csv_file()
        data_dir = external_data_dir()
    except (FileNotFoundError, RuntimeError) as e:
        pytest.skip(f"Skipping external validation test: {str(e)}")
    
    print(f"\nValidating external mapping: {mapping_file}")
    print(f"Against CSV: {csv_file}")
    print(f"With related data from: {data_dir}")
    
    # Use the combined validate_mapping function to get detailed column validation
    result = validate_mapping(
        mapping_file,
        csv_file,
        data_dir=data_dir,
        strict=False,  # Don't fail on warnings
        print_output=True  # Print the detailed report
    )
    
    # Log validation results for manual inspection
    # Don't assert anything here since we don't know if the external files are valid
    print(f"Validation {'passed' if result else 'failed'}")


def test_file_paths_exist(sample_mapping_file, sample_csv_file, sample_related_data_dir):
    """Test that fixture file paths actually exist and can be accessed."""
    # Basic check that our fixtures actually create files
    assert os.path.exists(sample_mapping_file), "Sample mapping file should exist"
    assert os.path.exists(sample_csv_file), "Sample CSV file should exist"
    assert os.path.exists(sample_related_data_dir), "Sample related data directory should exist"
    
    # Check related data file
    related_file = os.path.join(sample_related_data_dir, "RelatedData.csv")
    assert os.path.exists(related_file), "Related data file should exist"
    
    print(f"\nSample mappings at: {sample_mapping_file}")
    print(f"Sample CSV at: {sample_csv_file}")
    print(f"Sample related data at: {related_file}") 