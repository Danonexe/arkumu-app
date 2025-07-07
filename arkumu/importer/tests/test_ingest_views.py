"""
Unit tests for ingest views
"""
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from arkumu.users.models import Organization

User = get_user_model()


class TestIngestViews(TestCase):
    """Test suite for ingest views"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.organization = Organization.objects.create(
            name='Test Organization',
            code='test'
        )
    
    def test_ingest_data_view_requires_login(self):
        """Test that ingest data view requires login"""
        url = reverse('importer:ingest_data')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)  # Permission denied
    
    def test_ingest_data_view_authenticated(self):
        """Test that authenticated user can access ingest data view"""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('importer:ingest_data')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Data Ingestion Center')
    
    def test_get_organization_files_empty_org(self):
        """Test getting files with no organization parameter"""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('importer:get_organization_files')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select an organization')
    
    def test_toggle_file_selection_requires_login(self):
        """Test that file selection toggle requires login"""
        url = reverse('importer:toggle_file_selection')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # Permission denied
    
    def test_toggle_file_selection_missing_params(self):
        """Test file selection with missing parameters"""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('importer:toggle_file_selection')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
    
    def test_select_all_files_requires_login(self):
        """Test that select all files requires login"""
        url = reverse('importer:select_all_files')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # Permission denied
    
    def test_deselect_all_files_requires_login(self):
        """Test that deselect all files requires login"""
        url = reverse('importer:deselect_all_files')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # Permission denied
    
    def test_toggle_folder_requires_login(self):
        """Test that toggle folder requires login"""
        url = reverse('importer:toggle_folder')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)  # Permission denied
    
    def test_url_patterns_exist(self):
        """Test that all URL patterns are correctly defined"""
        urls_to_test = [
            'importer:ingest_data',
            'importer:get_organization_files',
            'importer:toggle_file_selection',
            'importer:select_all_files',
            'importer:deselect_all_files',
            'importer:toggle_folder',
        ]
        
        for url_name in urls_to_test:
            url = reverse(url_name)
            self.assertIsInstance(url, str)
            self.assertTrue(url.startswith('/importer/'))
    
    def test_session_file_selection(self):
        """Test file selection session management"""
        self.client.login(username='testuser', password='testpass123')
        
        # Initially no files selected
        session = self.client.session
        self.assertEqual(session.get('ingest_selected_files', []), [])
        
        # Test deselect all (should work even with empty session)
        url = reverse('importer:deselect_all_files')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)