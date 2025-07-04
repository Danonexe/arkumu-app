const { test, expect } = require('@playwright/test');

test.describe('CSV Mapping Editor', () => {
  
  test.beforeEach(async ({ page }) => {
    // Navigate to the CSV mapping editor page
    await page.goto('/metadata/csv-mapping/');
  });

  test('should load page with correct title and basic elements', async ({ page }) => {
    // Check page title
    await expect(page).toHaveTitle(/CSV Mapping Editor/);
    
    // Check main heading
    await expect(page.locator('h1')).toContainText('CSV Mapping Editor');
    
    // Check organization selector exists
    await expect(page.locator('#organization-selector')).toBeVisible();
    
    // Check main content container exists
    await expect(page.locator('#main-content')).toBeVisible();
    
    // Check navbar structure
    await expect(page.locator('.navbar')).toBeVisible();
    await expect(page.locator('.navbar-start')).toBeVisible();
    await expect(page.locator('.navbar-end')).toBeVisible();
  });

  test('should display organization selector with default option', async ({ page }) => {
    const selector = page.locator('#organization-selector');
    
    // Check selector is visible
    await expect(selector).toBeVisible();
    
    // Check default option text
    await expect(selector.locator('option[value=""]')).toContainText('Choose organization...');
    
    // Check selector has correct HTMX attributes
    await expect(selector).toHaveAttribute('hx-get');
    await expect(selector).toHaveAttribute('hx-target', '#main-content');
    await expect(selector).toHaveAttribute('hx-swap', 'innerHTML');
  });

  test('should handle organization selection and trigger HTMX request', async ({ page }) => {
    // Wait for any initial load to complete
    await page.waitForLoadState('networkidle');
    
    // Mock the HTMX response
    await page.route('**/metadata/csv-mapping/', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<div id="test-content">Organization selected content</div>'
      });
    });
    
    const selector = page.locator('#organization-selector');
    
    // Select an organization (assuming there's at least one option with value)
    const options = await selector.locator('option[value!=""]').count();
    if (options > 0) {
      const firstOptionValue = await selector.locator('option[value!=""]').first().getAttribute('value');
      await selector.selectOption(firstOptionValue);
      
      // Wait for HTMX request to complete
      await page.waitForResponse('**/metadata/csv-mapping/');
      
      // Check that main content was updated
      await expect(page.locator('#main-content')).toContainText('Organization selected content');
    }
  });

  test('should display status toast when showErrorToast is called', async ({ page }) => {
    // Wait for the page to fully load and functions to be available
    await page.waitForLoadState('domcontentloaded');
    await page.waitForFunction(() => typeof window.showErrorToast === 'function');
    
    // Initially, toast should be hidden
    await expect(page.locator('#status-toast')).toBeHidden();
    
    // Call the showErrorToast function
    await page.evaluate(() => {
      showErrorToast('Test error message');
    });
    
    // Toast should now be visible
    await expect(page.locator('#status-toast')).toBeVisible();
    await expect(page.locator('#status-message')).toContainText('Test error message');
    
    // Toast should auto-hide after 5 seconds
    await page.waitForTimeout(5100);
    await expect(page.locator('#status-toast')).toBeHidden();
  });

  test('should display success toast when showSuccessToast is called', async ({ page }) => {
    // Wait for the page to fully load and functions to be available
    await page.waitForLoadState('domcontentloaded');
    await page.waitForFunction(() => typeof window.showSuccessToast === 'function');
    
    // Initially, toast should be hidden
    await expect(page.locator('#status-toast')).toBeHidden();
    
    // Call the showSuccessToast function
    await page.evaluate(() => {
      showSuccessToast('Test success message');
    });
    
    // Toast should now be visible
    await expect(page.locator('#status-toast')).toBeVisible();
    await expect(page.locator('#status-message')).toContainText('Test success message');
    
    // Toast should auto-hide after 3 seconds
    await page.waitForTimeout(3100);
    await expect(page.locator('#status-toast')).toBeHidden();
  });

  test('should handle HTMX response errors gracefully', async ({ page }) => {
    // Mock a failed HTMX response
    await page.route('**/metadata/csv-mapping/', async route => {
      await route.fulfill({
        status: 500,
        contentType: 'text/html',
        body: 'Server Error'
      });
    });
    
    const selector = page.locator('#organization-selector');
    
    // Select an organization to trigger the request
    const options = await selector.locator('option[value!=""]').count();
    if (options > 0) {
      const firstOptionValue = await selector.locator('option[value!=""]').first().getAttribute('value');
      await selector.selectOption(firstOptionValue);
      
      // Wait for the error response
      await page.waitForResponse('**/metadata/csv-mapping/');
      
      // Error toast should appear
      await expect(page.locator('#status-toast')).toBeVisible();
      await expect(page.locator('#status-message')).toContainText('Request failed: 500');
    }
  });

  test('should enable debug mode when URL contains debug=1', async ({ page }) => {
    // Navigate with debug parameter
    await page.goto('/metadata/csv-mapping/?debug=1');
    
    // Wait for DOM to be ready and debug mode to be initialized
    await page.waitForLoadState('domcontentloaded');
    await page.waitForFunction(() => typeof window.HTMX_DEBUG !== 'undefined');
    
    // Check that debug mode is enabled
    const debugEnabled = await page.evaluate(() => {
      return window.HTMX_DEBUG === true;
    });
    
    expect(debugEnabled).toBe(true);
  });

  test('should handle network errors with appropriate messaging', async ({ page }) => {
    // Mock a network error
    await page.route('**/metadata/csv-mapping/', async route => {
      await route.abort('failed');
    });
    
    const selector = page.locator('#organization-selector');
    
    // Select an organization to trigger the request
    const options = await selector.locator('option[value!=""]').count();
    if (options > 0) {
      const firstOptionValue = await selector.locator('option[value!=""]').first().getAttribute('value');
      await selector.selectOption(firstOptionValue);
      
      // Wait a moment for the error handling
      await page.waitForTimeout(1000);
      
      // Network error toast should appear
      await expect(page.locator('#status-toast')).toBeVisible();
      await expect(page.locator('#status-message')).toContainText('Network error - please check your connection');
    }
  });

  test('should display empty state template when no datasets selected', async ({ page }) => {
    // Check if empty state template exists in DOM
    await expect(page.locator('#empty-csv-state-template')).toBeAttached();
    
    // Check empty state template content
    const template = page.locator('#empty-csv-state-template');
    await expect(template.locator('p')).toContainText('Select CSV datasets above to begin mapping');
    await expect(template.locator('p.text-xs')).toContainText('Preview column structures • Configure relationships • Design import strategy');
  });

  test('should have proper CSRF token for HTMX requests', async ({ page }) => {
    // Check that CSRF token is present in the page
    await expect(page.locator('input[name="csrfmiddlewaretoken"]')).toBeAttached();
  });

  test('should re-enable disabled buttons after HTMX errors', async ({ page }) => {
    // Create a test button and disable it
    await page.evaluate(() => {
      const testBtn = document.createElement('button');
      testBtn.id = 'test-button';
      testBtn.disabled = true;
      testBtn.textContent = 'Test Button';
      document.body.appendChild(testBtn);
    });
    
    // Trigger HTMX response error
    await page.evaluate(() => {
      const event = new CustomEvent('htmx:responseError', {
        detail: {
          xhr: { status: 500, statusText: 'Internal Server Error' }
        }
      });
      document.dispatchEvent(event);
    });
    
    // Wait a moment for error handling
    await page.waitForTimeout(100);
    
    // Button should be re-enabled
    await expect(page.locator('#test-button')).not.toBeDisabled();
    
    // Clean up
    await page.evaluate(() => {
      const testBtn = document.getElementById('test-button');
      if (testBtn) testBtn.remove();
    });
  });

  test('should handle HTMX target errors with graceful fallback', async ({ page }) => {
    // Trigger a target error event
    await page.evaluate(() => {
      const event = new CustomEvent('htmx:targetError', {
        detail: {
          target: '#dataset-nonexistent'
        },
        target: { id: 'test-source' }
      });
      document.dispatchEvent(event);
    });
    
    // Wait a moment for error handling
    await page.waitForTimeout(100);
    
    // Should not show error toast for dataset-related target errors
    await expect(page.locator('#status-toast')).toBeHidden();
  });

  test('should show error toast for critical HTMX target failures', async ({ page }) => {
    // Trigger a critical target error event
    await page.evaluate(() => {
      const event = new CustomEvent('htmx:targetError', {
        detail: {
          target: '#critical-container'
        },
        target: { id: 'important-source' }
      });
      document.dispatchEvent(event);
    });
    
    // Wait a moment for error handling
    await page.waitForTimeout(100);
    
    // Should show error toast for critical failures
    await expect(page.locator('#status-toast')).toBeVisible();
    await expect(page.locator('#status-message')).toContainText('Interface update failed - please refresh');
  });

});