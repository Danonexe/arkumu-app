import os
import tempfile
import zipfile
import shutil
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile

class ImportViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.import_url = reverse('import-list')
        
        # Create a temp directory for test files
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a test CSV file
        self.csv_content = b"id;name;age\n1;John;30\n2;Jane;25\n"
        self.csv_path = os.path.join(self.temp_dir, "people.csv")
        with open(self.csv_path, "wb") as f:
            f.write(self.csv_content)
            
        # Create a test ZIP file
        self.zip_path = os.path.join(self.temp_dir, "test_data.zip")
        with zipfile.ZipFile(self.zip_path, 'w') as zipf:
            zipf.write(self.csv_path, arcname="people.csv")
    def test_import_directory_with_path(self, mock_import):
        """Test importing from a directory path"""
        # Mock the NEW directory import workflow task
        mock_task = MagicMock()
        mock_task.id = 'test-task-123'
        mock_import.return_value = mock_task
        
        # Make the request
        data = {
            "directory_path": self.temp_dir,
            "institution": "TEST",
            "delimiter": ";"
        }
        response = self.client.post(self.import_url, data, format='json')
        
        # Assert the response
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)  # Async task returns 202
        self.assertIn("task_id", response.data)
        self.assertEqual(response.data["task_id"], 'test-task-123')
        
        # Assert the NEW directory import workflow was called with correct args
        mock_import.assert_called_once()
        # Check that the task was called with directory processing parameters
        args, kwargs = mock_import.call_args
        self.assertIn("s3_folder_prefix", kwargs)  # NEW system uses S3
        self.assertIn("institution", kwargs)
        self.assertEqual(kwargs["institution"], "TEST")
    
    @patch('arkumu.importer.tasks.import_metadata.run_csv_directory_import_workflow.delay')
    def test_import_directory_with_zip(self, mock_import):
        """Test importing from a ZIP file upload"""
        # Mock the NEW directory import workflow task
        mock_task = MagicMock()
        mock_task.id = 'test-task-456'
        mock_import.return_value = mock_task
        
        # Create a ZIP file for upload
        with open(self.zip_path, 'rb') as f:
            zip_content = f.read()
        
        zip_file = SimpleUploadedFile(
            "test_data.zip",
            zip_content,
            content_type="application/zip"
        )
        
        # Make the request
        data = {
            "zip_file": zip_file,
            "institution": "TEST",
            "delimiter": ";"
        }
        response = self.client.post(self.import_url, data, format='multipart')
        
        # Assert the response
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)  # Async task returns 202
        self.assertIn("task_id", response.data)
        self.assertEqual(response.data["task_id"], 'test-task-456')
        
        # Assert the NEW directory import workflow was called with correct args
        mock_import.assert_called_once()
        args, kwargs = mock_import.call_args
        self.assertIn("s3_folder_prefix", kwargs)  # NEW system uses S3
        self.assertIn("institution", kwargs)
        self.assertEqual(kwargs["institution"], "TEST")
    
    def test_import_directory_without_path_or_zip(self):
        """Test that an error is returned when neither path nor zip is provided"""
        # Make the request without directory_path or zip_file
        data = {
            "institution": "TEST",
            "delimiter": ";"
        }
        response = self.client.post(self.import_url, data, format='json')
        
        # Assert error response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Either directory_path or zip_file must be provided", str(response.data)) 