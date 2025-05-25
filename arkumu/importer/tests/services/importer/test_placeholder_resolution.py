import os
import json
import tempfile
import shutil
import pytest
from django.test import TestCase

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.importer.placeholder_manager import PlaceholderManager
from arkumu.metadata.models.resource import Resource
from arkumu.metadata.models.triples import Triple


class PlaceholderResolutionTest(TestCase):
    """Test placeholder creation and resolution with controlled data"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data directory and files"""
        super().setUpClass()
        
        # Create temporary directory for test data
        cls.test_data_dir = tempfile.mkdtemp()
        
        # Create test CSV files
        cls._create_test_csv_files()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data directory"""
        super().tearDownClass()
        
        # Remove temporary directory
        if os.path.exists(cls.test_data_dir):
            shutil.rmtree(cls.test_data_dir)
    
    @classmethod
    def _create_test_csv_files(cls):
        """Create test CSV files with controlled data for placeholder testing"""
        
        # Projects CSV (will be imported after tasks to test resolution)
        projects_data = """id;name;description
PROJ001;Project Alpha;First project
PROJ002;Project Beta;Second project
PROJ003;Project Gamma;Third project"""
        
        with open(os.path.join(cls.test_data_dir, "projects.csv"), 'w') as f:
            f.write(projects_data)
        
        # People CSV (will be imported after tasks to test resolution)
        people_data = """id;name;email
EMP001;John Doe;john@example.com
EMP002;Jane Smith;jane@example.com
EMP003;Bob Johnson;bob@example.com"""
        
        with open(os.path.join(cls.test_data_dir, "people.csv"), 'w') as f:
            f.write(people_data)
        
        # Tasks CSV (references projects and people that don't exist yet)
        tasks_data = """id;name;project_id;assignee_id;status
TASK001;Setup database;PROJ001;EMP001;In Progress
TASK002;Design UI;PROJ001;EMP002;Not Started
TASK003;Write tests;PROJ002;EMP001;Completed
TASK004;Deploy app;PROJ002;EMP003;In Progress
TASK005;Documentation;PROJ003;EMP002;Not Started
TASK006;Bug fixes;PROJ999;EMP003;In Progress"""
        
        with open(os.path.join(cls.test_data_dir, "tasks.csv"), 'w') as f:
            f.write(tasks_data)
        
        # Assignments CSV (relationship table)
        assignments_data = """id;project_id;person_id;role
ASSIGN001;PROJ001;EMP001;Developer
ASSIGN002;PROJ001;EMP002;Designer
ASSIGN003;PROJ002;EMP001;Lead Developer
ASSIGN004;PROJ003;EMP003;Tester"""
        
        with open(os.path.join(cls.test_data_dir, "assignments.csv"), 'w') as f:
            f.write(assignments_data)

    def test_placeholder_creation_and_resolution_sequence(self):
        """Test that placeholders are created and then resolved in the correct sequence"""
        
        institution = "TEST_PLACEHOLDER"
        base_uri = "http://test.arkumu.org/data"
        
        # Clear any existing placeholders
        initial_placeholders = PlaceholderManager.count_placeholders(institution)
        print(f"Initial placeholders in system: {initial_placeholders}")
        
        # Step 1: Import tasks.csv first - this should create placeholders for projects and people
        print("\n=== STEP 1: Import tasks.csv (creates placeholders) ===")
        tasks_csv = os.path.join(self.test_data_dir, "tasks.csv")
        
        stats1 = ImportWorkflowService.import_csv(
            csv_path=tasks_csv,
            dataset_name="tasks",
            institution=institution,
            base_uri=base_uri,
            delimiter=";",
            has_quoted_fields=False
        )
        
        print(f"Step 1 stats: {stats1}")
        
        # Check that placeholders were created
        placeholders_after_step1 = PlaceholderManager.count_placeholders(institution)
        print(f"Placeholders after step 1: {placeholders_after_step1}")
        
        # Should have created placeholders for project_id and assignee_id references
        self.assertGreater(stats1["placeholders_created"], 0, "Should have created placeholders for references")
        self.assertGreater(placeholders_after_step1, initial_placeholders, "Total placeholders should have increased")
        
        # Step 2: Import projects.csv - this should resolve project placeholders
        print("\n=== STEP 2: Import projects.csv (resolves project placeholders) ===")
        projects_csv = os.path.join(self.test_data_dir, "projects.csv")
        
        stats2 = ImportWorkflowService.import_csv(
            csv_path=projects_csv,
            dataset_name="projects",
            institution=institution,
            base_uri=base_uri,
            delimiter=";",
            has_quoted_fields=False
        )
        
        print(f"Step 2 stats: {stats2}")
        
        placeholders_after_step2 = PlaceholderManager.count_placeholders(institution)
        print(f"Placeholders after step 2: {placeholders_after_step2}")
        
        # Should have resolved some placeholders
        self.assertGreater(stats2["placeholders_resolved"], 0, "Should have resolved project placeholders")
        self.assertLess(placeholders_after_step2, placeholders_after_step1, "Total placeholders should have decreased")
        
        # Step 3: Import people.csv - this should resolve people placeholders
        print("\n=== STEP 3: Import people.csv (resolves people placeholders) ===")
        people_csv = os.path.join(self.test_data_dir, "people.csv")
        
        stats3 = ImportWorkflowService.import_csv(
            csv_path=people_csv,
            dataset_name="people",
            institution=institution,
            base_uri=base_uri,
            delimiter=";",
            has_quoted_fields=False
        )
        
        print(f"Step 3 stats: {stats3}")
        
        placeholders_after_step3 = PlaceholderManager.count_placeholders(institution)
        print(f"Placeholders after step 3: {placeholders_after_step3}")
        
        # Should have resolved more placeholders
        self.assertGreater(stats3["placeholders_resolved"], 0, "Should have resolved people placeholders")
        self.assertLess(placeholders_after_step3, placeholders_after_step2, "Total placeholders should have decreased further")
        
        # Check final state
        print(f"\n=== FINAL STATE ===")
        print(f"Initial placeholders: {initial_placeholders}")
        print(f"After tasks: {placeholders_after_step1}")
        print(f"After projects: {placeholders_after_step2}")
        print(f"After people: {placeholders_after_step3}")
        
        # Should still have some unresolved placeholders (PROJ999 doesn't exist)
        self.assertGreater(placeholders_after_step3, 0, "Should still have unresolved placeholders for non-existent references")
        
        # Analyze remaining placeholders
        unresolved = PlaceholderManager.get_unresolved_placeholders(institution)
        print(f"Unresolved placeholders: {len(unresolved)}")
        for placeholder in unresolved:
            print(f"  - {placeholder['name']}: {placeholder['value']}")

    def test_directory_import_with_placeholder_resolution(self):
        """Test placeholder resolution when importing entire directory"""
        
        institution = "TEST_DIR_PLACEHOLDER"
        base_uri = "http://test.arkumu.org/data"
        
        # Import entire directory at once
        print("\n=== Directory Import Test ===")
        
        stats = ImportWorkflowService.import_csv_directory(
            directory_path=self.test_data_dir,
            institution=institution,
            base_uri=base_uri,
            delimiter=";",
            has_quoted_fields=False
        )
        
        print(f"Directory import stats: {stats}")
        
        # Check that placeholders were both created and resolved
        self.assertGreater(stats["placeholders_created"], 0, "Should have created placeholders")
        self.assertGreater(stats["placeholders_resolved"], 0, "Should have resolved placeholders")
        
        # Should have some unresolved placeholders (for PROJ999 which doesn't exist)
        self.assertGreater(stats["total_placeholders"], 0, "Should have some unresolved placeholders")

    def test_relationship_table_with_placeholders(self):
        """Test that relationship tables work with placeholder resolution"""
        
        institution = "TEST_REL_PLACEHOLDER"
        base_uri = "http://test.arkumu.org/data"
        
        # Create relationship config for assignments table
        relationship_config = {
            "assignments": [
                {"column": "project_id", "target_table": "projects"},
                {"column": "person_id", "target_table": "people"}
            ]
        }
        
        # Save relationship config to file
        rel_config_path = os.path.join(self.test_data_dir, "relationship_config.json")
        with open(rel_config_path, 'w') as f:
            json.dump(relationship_config, f, indent=2)
        
        print("\n=== Relationship Table with Placeholders Test ===")
        
        # Import directory with relationship config
        stats = ImportWorkflowService.import_csv_directory(
            directory_path=self.test_data_dir,
            institution=institution,
            base_uri=base_uri,
            delimiter=";",
            has_quoted_fields=False,
            relationship_config_path=rel_config_path
        )
        
        print(f"Relationship import stats: {stats}")
        
        # Should have created relationships
        self.assertGreater(stats["relationships_created"], 0, "Should have created relationships")
        
        # Should have created and resolved placeholders
        self.assertGreater(stats["placeholders_created"], 0, "Should have created placeholders")
        self.assertGreater(stats["placeholders_resolved"], 0, "Should have resolved placeholders") 