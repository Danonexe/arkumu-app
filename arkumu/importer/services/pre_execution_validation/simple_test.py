"""
Simple test to verify the pre-execution validation service structure.

This test verifies that the service can be imported and basic functionality works
without requiring external dependencies.
"""

def test_imports():
    """Test that all modules can be imported"""
    try:
        from . import validation_result
        from . import integration_helpers
        
        print("✅ All modules imported successfully")
        print(f"   - ValidationSeverity: {validation_result.ValidationSeverity}")
        print(f"   - ValidationCategory: {validation_result.ValidationCategory}")
        print(f"   - ValidationMode: {validation_result.ValidationMode}")
        print(f"   - ValidationErrorCodes: {validation_result.ValidationErrorCodes}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


def test_validation_result_classes():
    """Test validation result classes"""
    try:
        from .validation_result import (
            ValidationIssue,
            ValidationSeverity,
            ValidationCategory,
            ValidationMode,
            PreExecutionValidationResult
        )
        
        # Create a sample validation issue
        issue = ValidationIssue(
            code="TEST_ERROR",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FILE_STRUCTURE,
            message="Test error message",
            file_path="/test/file.csv",
            column_name="test_column"
        )
        
        print("✅ ValidationIssue created successfully")
        print(f"   - Code: {issue.code}")
        print(f"   - Severity: {issue.severity}")
        print(f"   - Message: {issue.message}")
        print(f"   - String representation: {str(issue)}")
        
        # Create a validation result
        result = PreExecutionValidationResult(
            is_valid=False,
            validation_mode=ValidationMode.STRICT,
            overall_confidence=0.8
        )
        
        # Add issue to result
        result.add_issue(issue)
        
        print("✅ PreExecutionValidationResult created successfully")
        print(f"   - Is valid: {result.is_valid}")
        print(f"   - Confidence: {result.overall_confidence}")
        print(f"   - Issues: {len(result.all_issues)}")
        print(f"   - Has blocking issues: {result.has_blocking_issues()}")
        
        # Test serialization
        result_dict = result.to_dict()
        print(f"   - Serialization: {type(result_dict)} with {len(result_dict)} keys")
        
        return True
        
    except Exception as e:
        print(f"❌ Validation result test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_codes():
    """Test error codes"""
    try:
        from .validation_result import ValidationErrorCodes
        
        # Test some error codes
        error_codes = [
            ValidationErrorCodes.FILE_NOT_FOUND,
            ValidationErrorCodes.REQUIRED_COLUMN_MISSING,
            ValidationErrorCodes.INVALID_RELATIONSHIP,
            ValidationErrorCodes.HIGH_MEMORY_USAGE
        ]
        
        print("✅ Error codes accessible")
        for code in error_codes:
            print(f"   - {code}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error codes test failed: {e}")
        return False


def test_package_structure():
    """Test package structure"""
    try:
        from . import (
            PreExecutionValidator,
            ValidationIssue,
            ValidationSeverity,
            ValidationCategory,
            ValidationMode,
            ValidationErrorCodes
        )
        
        print("✅ Package structure valid")
        print(f"   - PreExecutionValidator: {PreExecutionValidator}")
        print(f"   - ValidationIssue: {ValidationIssue}")
        print(f"   - ValidationSeverity: {ValidationSeverity}")
        print(f"   - ValidationCategory: {ValidationCategory}")
        print(f"   - ValidationMode: {ValidationMode}")
        print(f"   - ValidationErrorCodes: {ValidationErrorCodes}")
        
        return True
        
    except Exception as e:
        print(f"❌ Package structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_simple_tests():
    """Run simple tests without external dependencies"""
    print("🔧 Running Simple Pre-Execution Validation Tests")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Validation Result Classes", test_validation_result_classes),
        ("Error Codes", test_error_codes),
        ("Package Structure", test_package_structure),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                failed += 1
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ {test_name} FAILED with exception: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed")
    
    return failed == 0


if __name__ == "__main__":
    run_simple_tests()