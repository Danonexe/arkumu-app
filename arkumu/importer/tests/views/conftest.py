"""
Pytest configuration for views tests.
Imports fixtures from execution tests for integration testing.
"""
import pytest

# Import shared fixtures from execution tests for integration testing
from arkumu.importer.tests.services.execution.conftest import (
    fuk_mapping_from_s3,
    production_test_mapping,
    real_csv_data,
    bucket_service,
    mapping_adapter,
    execution_statistics
)