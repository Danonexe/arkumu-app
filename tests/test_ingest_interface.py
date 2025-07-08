"""
Comprehensive Playwright test for the new ingest interface
Tests the complete workflow with fuk institution and fuk-test mapping
"""
import pytest
from playwright.sync_api import Page, expect


class TestIngestInterface:
    """Test suite for the ingest data interface"""
    
    def test_complete_ingest_workflow(self, page: Page):
        """Test the complete ingest workflow from login to file import"""
        
        # Navigate to login page
        page.goto("http://localhost:8000/accounts/login/")
        
        # Login with test user
        page.fill("#id_username", "fco")
        page.fill("#id_password", "test")
        page.click("button[type='submit']")
        
        # Wait for successful login redirect
        expect(page).to_have_url(lambda url: "/accounts/login/" not in url)
        
        # Navigate to ingest page
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Verify page loaded correctly
        expect(page.locator("h1")).to_have_text("Metadata Ingestion")
        
        # Select fuk organization
        organization_select = page.locator("#organization-select")
        organization_select.select_option("fuk")
        
        # Wait for HTMX to load files
        page.wait_for_selector("#file-browser .file-tree", timeout=10000)
        
        # Verify files are loaded
        expect(page.locator("#file-browser")).not_to_contain_text("Select an organization to browse files")
        
        # Check if CSV files are displayed
        csv_files = page.locator(".file-checkbox")
        expect(csv_files).to_have_count_greater_than(0)
        
        # Select first CSV file
        first_file = csv_files.first
        first_file.check()
        
        # Verify file selection counter updates
        expect(page.locator("#selected-count")).to_contain_text("1 file")
        
        # Select mapping (fuk-test)
        mapping_select = page.locator("#mapping-select")
        
        # Wait for mappings to load after organization selection
        page.wait_for_function(
            "document.querySelector('#mapping-select option[value=\"fuk-test\"]') !== null",
            timeout=10000
        )
        
        mapping_select.select_option("fuk-test")
        
        # Verify mapping buttons are enabled
        expect(page.locator("#mapping-overview-btn")).not_to_be_disabled()
        expect(page.locator("#mapping-graph-btn")).not_to_be_disabled()
        
        # Verify strategy radio button is enabled and selected
        expect(page.locator("#strategy-mapping")).not_to_be_disabled()
        expect(page.locator("#strategy-mapping")).to_be_checked()
        
        # Verify start import button is enabled
        expect(page.locator("#start-import-btn")).not_to_be_disabled()
        
        # Test mapping overview modal
        page.click("#mapping-overview-btn")
        page.wait_for_selector("#mapping-overview-modal .modal", timeout=10000)
        expect(page.locator("#mapping-overview-modal .modal")).to_be_visible()
        
        # Close modal
        page.click("#mapping-overview-modal .modal .btn-ghost")
        
        # Test mapping graph modal
        page.click("#mapping-graph-btn")
        page.wait_for_selector("#mapping-graph-modal .modal", timeout=10000)
        expect(page.locator("#mapping-graph-modal .modal")).to_be_visible()
        
        # Close modal
        page.click("#mapping-graph-modal .modal .btn-ghost")
        
        # Start import
        page.click("#start-import-btn")
        
        # Verify progress dashboard becomes visible
        expect(page.locator("#import-stats")).not_to_have_class("hidden")
        
        # Wait for import to start and check activity log
        page.wait_for_selector("#activity-log div", timeout=10000)
        expect(page.locator("#activity-log")).to_contain_text("Started import:")
        
        # Wait for some progress indicators
        page.wait_for_timeout(2000)
        
        # Verify statistics are updating
        expect(page.locator("#stat-files")).not_to_have_text("0")
    
    def test_organization_file_loading(self, page: Page):
        """Test organization file loading and error handling"""
        
        # Login
        page.goto("http://localhost:8000/accounts/login/")
        page.fill("#id_username", "fco")
        page.fill("#id_password", "test")
        page.click("button[type='submit']")
        
        # Navigate to ingest page
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Test each organization option
        organizations = ["rsh", "khm", "fuk", "hmt", "det"]
        
        for org_code in organizations:
            # Select organization
            page.locator("#organization-select").select_option(org_code)
            
            # Wait for HTMX response
            page.wait_for_timeout(2000)
            
            # Check that either files loaded or proper error message
            file_browser = page.locator("#file-browser")
            
            # Should not show the initial "Select an organization" message
            expect(file_browser).not_to_contain_text("Select an organization to browse files")
            
            # Should show either files or an appropriate error/empty state
            has_files = page.locator(".file-checkbox").count() > 0
            has_error = file_browser.locator(".alert-error").count() > 0
            has_warning = file_browser.locator(".alert-warning").count() > 0
            
            assert has_files or has_error or has_warning, f"No proper response for organization {org_code}"
    
    def test_file_selection_functionality(self, page: Page):
        """Test file selection and deselection"""
        
        # Login and navigate to ingest page
        page.goto("http://localhost:8000/accounts/login/")
        page.fill("#id_username", "fco")
        page.fill("#id_password", "test")
        page.click("button[type='submit']")
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Select fuk organization
        page.locator("#organization-select").select_option("fuk")
        page.wait_for_selector(".file-checkbox", timeout=10000)
        
        # Get all file checkboxes
        file_checkboxes = page.locator(".file-checkbox")
        checkbox_count = file_checkboxes.count()
        
        if checkbox_count > 0:
            # Test selecting multiple files
            for i in range(min(3, checkbox_count)):  # Select up to 3 files
                file_checkboxes.nth(i).check()
                
                # Verify counter updates
                expected_count = i + 1
                expect(page.locator("#selected-count")).to_contain_text(f"{expected_count} file")
            
            # Test deselecting files
            file_checkboxes.first.uncheck()
            if checkbox_count > 1:
                expected_count = min(2, checkbox_count - 1)
                expect(page.locator("#selected-count")).to_contain_text(f"{expected_count} file")
            else:
                expect(page.locator("#selected-count")).to_contain_text("0 files")
    
    def test_folder_toggle_functionality(self, page: Page):
        """Test folder expand/collapse functionality"""
        
        # Login and navigate
        page.goto("http://localhost:8000/accounts/login/")
        page.fill("#id_username", "fco")
        page.fill("#id_password", "test")
        page.click("button[type='submit']")
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Select organization with folders
        page.locator("#organization-select").select_option("fuk")
        page.wait_for_selector(".file-tree", timeout=10000)
        
        # Look for folder toggles
        folder_toggles = page.locator(".folder-toggle")
        if folder_toggles.count() > 0:
            # Test expanding a folder
            first_toggle = folder_toggles.first
            first_toggle.click()
            
            # Verify folder contents become visible
            # This would need to be implemented based on the actual folder structure
            page.wait_for_timeout(500)
            
            # Test collapsing the folder
            first_toggle.click()
            page.wait_for_timeout(500)
    
    def test_mapping_selection_workflow(self, page: Page):
        """Test mapping selection and strategy switching"""
        
        # Login and navigate
        page.goto("http://localhost:8000/accounts/login/")
        page.fill("#id_username", "fco")
        page.fill("#id_password", "test")
        page.click("button[type='submit']")
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Select fuk organization
        page.locator("#organization-select").select_option("fuk")
        
        # Wait for mappings to load
        page.wait_for_function(
            "document.querySelector('#mapping-select option').textContent !== 'Loading mappings...'",
            timeout=10000
        )
        
        # Test no mapping selected initially
        expect(page.locator("#mapping-overview-btn")).to_be_disabled()
        expect(page.locator("#mapping-graph-btn")).to_be_disabled()
        expect(page.locator("#strategy-mapping")).to_be_disabled()
        expect(page.locator("#strategy-entity")).to_be_checked()
        
        # Select fuk-test mapping if available
        mapping_options = page.locator("#mapping-select option")
        fuk_test_option = page.locator("#mapping-select option[value*='fuk-test']")
        
        if fuk_test_option.count() > 0:
            page.locator("#mapping-select").select_option(label="fuk-test")
            
            # Verify buttons become enabled
            expect(page.locator("#mapping-overview-btn")).not_to_be_disabled()
            expect(page.locator("#mapping-graph-btn")).not_to_be_disabled()
            expect(page.locator("#strategy-mapping")).not_to_be_disabled()
            expect(page.locator("#strategy-mapping")).to_be_checked()
        
        # Test switching back to no mapping
        page.locator("#mapping-select").select_option("")
        expect(page.locator("#mapping-overview-btn")).to_be_disabled()
        expect(page.locator("#mapping-graph-btn")).to_be_disabled()
        expect(page.locator("#strategy-entity")).to_be_checked()
    
    def test_import_button_enabling_logic(self, page: Page):
        """Test when the start import button becomes enabled"""
        
        # Login and navigate
        page.goto("http://localhost:8000/accounts/login/")
        page.fill("#id_username", "fco")
        page.fill("#id_password", "test")
        page.click("button[type='submit']")
        page.goto("http://localhost:8000/importer/ingest/")
        
        # Initially disabled
        expect(page.locator("#start-import-btn")).to_be_disabled()
        
        # Still disabled after selecting organization
        page.locator("#organization-select").select_option("fuk")
        expect(page.locator("#start-import-btn")).to_be_disabled()
        
        # Should become enabled after selecting files
        page.wait_for_selector(".file-checkbox", timeout=10000)
        file_checkboxes = page.locator(".file-checkbox")
        
        if file_checkboxes.count() > 0:
            file_checkboxes.first.check()
            expect(page.locator("#start-import-btn")).not_to_be_disabled()
            
            # Should become disabled again if no files selected
            file_checkboxes.first.uncheck()
            expect(page.locator("#start-import-btn")).to_be_disabled()


@pytest.fixture
def page(browser):
    """Create a new page for each test"""
    page = browser.new_page()
    yield page
    page.close()


@pytest.fixture
def browser():
    """Create browser instance"""
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Set to True for CI
        yield browser
        browser.close()