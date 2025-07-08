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
    
    def tearDown(self):
        # Clean up the temp directory
        shutil.rmtree(self.temp_dir)
    
    @patch('arkumu.common.import_service_bridge.bridge_service.import_csv_directory')
    def test_import_directory_with_path(self, mock_import):
        """Test importing from a directory path"""
        # Mock the import_csv_directory method
        mock_import.return_value = {"files_processed": 1, "resources_created": 10}
        
        # Make the request
        data = {
            "directory_path": self.temp_dir,
            "institution": "TEST",
            "delimiter": ";"
        }
        response = self.client.post(self.import_url, data, format='json')
        
        # Assert the response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"files_processed": 1, "resources_created": 10})
        
        # Assert the import_csv_directory was called with correct args
        mock_import.assert_called_once()
        args, kwargs = mock_import.call_args
        self.assertEqual(kwargs["directory_path"], self.temp_dir)
        self.assertEqual(kwargs["institution"], "TEST")
        self.assertEqual(kwargs["delimiter"], ";")
    
    @patch('arkumu.common.import_service_bridge.bridge_service.import_csv_directory')
    def test_import_directory_with_zip(self, mock_import):
        """Test importing from a ZIP file upload"""
        # Mock the import_csv_directory method
        mock_import.return_value = {"files_processed": 1, "resources_created": 10}
        
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
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"files_processed": 1, "resources_created": 10})
        
        # Assert the import_csv_directory was called with correct args
        mock_import.assert_called_once()
        args, kwargs = mock_import.call_args
        self.assertTrue(kwargs["directory_path"].startswith(tempfile.gettempdir()))
        self.assertEqual(kwargs["institution"], "TEST")
        self.assertEqual(kwargs["delimiter"], ";")
    
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