"""
Playwright tests for the ingest interface functionality.
Tests the complete workflow including authentication, file selection, and HTMX interactions.
"""
import pytest
from playwright.sync_api import Page, expect


class TestIngestInterface:
    """Test suite for the ingest interface functionality."""
    
    def test_login_and_access_ingest_interface(self, page: Page):
        """Test successful login and access to ingest interface."""
        # Navigate to login page
        page.goto("http://localhost:8000/accounts/login/")
        expect(page).to_have_title("Sign In")
        
        # Fill in credentials
        page.fill('input[name="login"]', "fco")
        page.fill('input[name="password"]', "test")
        
        # Submit login form
        page.click('button[type="submit"]')
        
        # Verify successful login
        expect(page).to_have_url("http://localhost:8000/")
        expect(page.locator('text="Successfully signed in as fco"')).to_be_visible()
        
        # Navigate to ingest interface
        page.goto("http://localhost:8000/importer/ingest/")
        expect(page).to_have_title("arkumu")
        
        # Verify main interface elements are present
        expect(page.locator('h1:has-text("Metadata Ingestion")')).to_be_visible()
        expect(page.locator('h2:has-text("Select Files")')).to_be_visible()
        expect(page.locator('h2:has-text("Configure Mapping")')).to_be_visible()
        expect(page.locator('h2:has-text("Progress Dashboard")')).to_be_visible()

    def test_organization_selection_functionality(self, page: Page):
        """Test organization selection dropdown functionality."""
        # Login first
        page.goto("http://localhost:8000/accounts/login/")
        page.fill('input[name="login"]', "fco")
        page.fill('input[name="password"]', "test")
        page.click('button[type="submit"]')
        
        # Navigate to ingest interface
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Test organization dropdown
        organization_select = page.locator('#organization-select')
        expect(organization_select).to_be_visible()
        
        # Verify dropdown options are present
        expect(organization_select.locator('option:has-text("Folkwang Universität der Künste")')).to_be_visible()
        expect(organization_select.locator('option:has-text("Kunsthochschule für Medien Köln")')).to_be_visible()
        
        # Select an organization
        organization_select.select_option("Kunsthochschule für Medien Köln")
        
        # Verify organization was selected
        expect(organization_select.locator('option[selected]:has-text("Kunsthochschule für Medien Köln")')).to_be_visible()

    def test_mapping_configuration_interface(self, page: Page):
        """Test the mapping configuration interface elements."""
        # Login and navigate to ingest interface
        page.goto("http://localhost:8000/accounts/login/")
        page.fill('input[name="login"]', "fco")
        page.fill('input[name="password"]', "test")
        page.click('button[type="submit"]')
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Test mapping section elements
        expect(page.locator('text="Select Mapping"')).to_be_visible()
        expect(page.locator('text="Required"')).to_be_visible()
        
        # Test import strategy radio buttons
        expect(page.locator('text="Use Selected Mapping"')).to_be_visible()
        expect(page.locator('text="Entity-Based Import"')).to_be_visible()
        
        # Verify Entity-Based Import is selected by default
        expect(page.locator('input[type="radio"]:checked + * >> text="Entity-Based Import"')).to_be_visible()
        
        # Test configuration checkboxes
        expect(page.locator('text="Use modern table services"')).to_be_visible()
        expect(page.locator('text="Link cells in same row"')).to_be_visible()

    def test_start_import_button_disabled_state(self, page: Page):
        """Test that Start Import button is disabled when no files are selected."""
        # Login and navigate to ingest interface
        page.goto("http://localhost:8000/accounts/login/")
        page.fill('input[name="login"]', "fco")
        page.fill('input[name="password"]', "test")
        page.click('button[type="submit"]')
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Verify Start Import button is disabled initially
        start_button = page.locator('button:has-text("Start Import")')
        expect(start_button).to_be_visible()
        expect(start_button).to_be_disabled()

    def test_file_selection_counter(self, page: Page):
        """Test that file selection counter shows correct initial state."""
        # Login and navigate to ingest interface
        page.goto("http://localhost:8000/accounts/login/")
        page.fill('input[name="login"]', "fco")
        page.fill('input[name="password"]', "test")
        page.click('button[type="submit"]')
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Verify initial file selection state
        expect(page.locator('text="Selected:"')).to_be_visible()
        expect(page.locator('text="0 files"')).to_be_visible()
        expect(page.locator('text="No files selected"')).to_be_visible()

    def test_overview_and_graph_buttons_disabled(self, page: Page):
        """Test that Overview and Graph buttons are disabled when no mapping is selected."""
        # Login and navigate to ingest interface
        page.goto("http://localhost:8000/accounts/login/")
        page.fill('input[name="login"]', "fco")
        page.fill('input[name="password"]', "test")
        page.click('button[type="submit"]')
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Verify Overview and Graph buttons are disabled
        overview_button = page.locator('button:has-text("Overview")')
        graph_button = page.locator('button:has-text("Graph")')
        
        expect(overview_button).to_be_visible()
        expect(overview_button).to_be_disabled()
        expect(graph_button).to_be_visible()
        expect(graph_button).to_be_disabled()

    def test_progress_dashboard_initial_state(self, page: Page):
        """Test the initial state of the progress dashboard."""
        # Login and navigate to ingest interface
        page.goto("http://localhost:8000/accounts/login/")
        page.fill('input[name="login"]', "fco")
        page.fill('input[name="password"]', "test")
        page.click('button[type="submit"]')
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Verify progress dashboard initial state
        expect(page.locator('h2:has-text("Progress Dashboard")')).to_be_visible()
        expect(page.locator('text="Select files and configure import to begin"')).to_be_visible()
        expect(page.locator('h3:has-text("Activity Log")')).to_be_visible()

    def test_htmx_file_browser_organization_change(self, page: Page):
        """Test HTMX functionality when changing organization selection."""
        # Login and navigate to ingest interface
        page.goto("http://localhost:8000/accounts/login/")
        page.fill('input[name="login"]', "fco")
        page.fill('input[name="password"]', "test")
        page.click('button[type="submit"]')
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Select an organization to trigger HTMX request
        organization_select = page.locator('#organization-select')
        organization_select.select_option("Kunsthochschule für Medien Köln")
        
        # Wait for HTMX response and verify file browser area updates
        # Note: In a real scenario, this would show files or an error message
        # For now, we verify the organization selection triggered an update
        page.wait_for_timeout(1000)  # Give HTMX time to process
        
        # Verify that the interface is still functional after the HTMX request
        expect(page.locator('h2:has-text("Select Files")')).to_be_visible()
        expect(organization_select.locator('option[selected]:has-text("Kunsthochschule für Medien Köln")')).to_be_visible()

    @pytest.mark.skip(reason="Requires test data setup")
    def test_file_selection_with_real_files(self, page: Page):
        """Test file selection functionality with actual files present.
        
        This test is skipped because it requires proper test data setup
        with actual files in the S3 bucket for the test organization.
        """
        pass

    @pytest.mark.skip(reason="Requires mapping data setup")
    def test_mapping_selection_functionality(self, page: Page):
        """Test mapping selection dropdown functionality.
        
        This test is skipped because it requires proper test mappings
        to be created for the test organization.
        """
        pass