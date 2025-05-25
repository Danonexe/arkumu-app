#!/usr/bin/env python

import os
import tempfile
import shutil
import pytest

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
# PlaceholderManager no longer used - relationships handled in post-processing


@pytest.mark.django_db
def test_real_scenario_multiple_files():
    """Test real scenario with multiple CSV files and cross-references"""
    
    # Create temporary directory
    test_dir = tempfile.mkdtemp()
    
    try:
        # Create departments.csv
        departments_data = """id;name;budget
DEPT001;Engineering;500000
DEPT002;Marketing;300000
DEPT003;Sales;400000"""
        
        with open(os.path.join(test_dir, "departments.csv"), 'w') as f:
            f.write(departments_data)
        
        # Create employees.csv (references departments)
        employees_data = """id;name;email;department_id;manager_id
EMP001;John Doe;john@company.com;DEPT001;
EMP002;Jane Smith;jane@company.com;DEPT001;EMP001
EMP003;Bob Johnson;bob@company.com;DEPT002;
EMP004;Alice Brown;alice@company.com;DEPT002;EMP003
EMP005;Grace Lee;grace@company.com;DEPT999;EMP001"""  # DEPT999 doesn't exist
        
        with open(os.path.join(test_dir, "employees.csv"), 'w') as f:
            f.write(employees_data)
        
        # Create projects.csv (references departments and employees)
        projects_data = """id;name;department_id;lead_id;budget
PROJ001;Website Redesign;DEPT002;EMP003;50000
PROJ002;Mobile App;DEPT001;EMP001;100000
PROJ003;Secret Project;DEPT999;EMP999;1000000"""  # References non-existent dept and employee
        
        with open(os.path.join(test_dir, "projects.csv"), 'w') as f:
            f.write(projects_data)
        
        # Create tasks.csv (references projects and employees)
        tasks_data = """id;name;project_id;assignee_id;status
TASK001;Design mockups;PROJ001;EMP003;In Progress
TASK002;Frontend development;PROJ002;EMP001;Not Started
TASK003;Backend API;PROJ002;EMP002;In Progress
TASK004;Deployment;PROJ999;EMP999;Blocked"""  # References non-existent project and employee
        
        with open(os.path.join(test_dir, "tasks.csv"), 'w') as f:
            f.write(tasks_data)
        
        # Test the import
        institution = "REAL_TEST"
        base_uri = "http://test.arkumu.org/data"
        
        print(f"\n=== IMPORTING DIRECTORY: {test_dir} ===")
        
        stats = ImportWorkflowService.import_csv_directory(
            directory_path=test_dir,
            institution=institution,
            base_uri=base_uri,
            delimiter=";",
            has_quoted_fields=False
        )
        
        print(f"\n=== RESULTS ===")
        print(f"Files processed: {stats['files_processed']}")
        print(f"Resources created: {stats['resources_created']}")
        print(f"Triples created: {stats['triples_created']}")
        print(f"Errors: {stats['errors']}")
        
        # Assertions
        assert stats['files_processed'] == 4, "Should process all 4 CSV files"
        assert stats['resources_created'] > 0, "Should create resources for all data"
        assert stats['triples_created'] > 0, "Should create triples for all data"
        assert stats['errors'] == 0, "Should have no errors"
        
        print(f"\n✅ SUCCESS: All data imported as literals!")
        print(f"📊 {stats['resources_created']} resources and {stats['triples_created']} triples created")
        print(f"🔗 Relationships can now be processed in post-processing phase")
        
    finally:
        # Clean up
        shutil.rmtree(test_dir)
