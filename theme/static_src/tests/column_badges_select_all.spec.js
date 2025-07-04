const { test, expect } = require('@playwright/test');

test.describe('Column Badges Select All Behavior', () => {
  
  test.beforeEach(async ({ page }) => {
    // Navigate to the CSV mapping editor page
    await page.goto('/metadata/csv-mapping/');
    
    // Wait for page to load and select an organization to get datasets
    await page.waitForLoadState('networkidle');
    
    // Select first available organization if exists
    const orgSelector = page.locator('#organization-selector');
    const options = await orgSelector.locator('option[value!=""]').count();
    if (options > 0) {
      const firstOptionValue = await orgSelector.locator('option[value!=""]').first().getAttribute('value');
      await orgSelector.selectOption(firstOptionValue);
      
      // Wait for HTMX request to load datasets
      await page.waitForResponse('**/metadata/csv-mapping/');
      await page.waitForLoadState('networkidle');
    }
  });

  test('should display Select All button initially when no columns selected', async ({ page }) => {
    // Look for any dataset column badges container
    const columnBadgesContainer = page.locator('[id^="column-badges-"]').first();
    
    if (await columnBadgesContainer.isVisible()) {
      // Get the dataset name from the container ID
      const containerId = await columnBadgesContainer.getAttribute('id');
      const datasetName = containerId.replace('column-badges-', '');
      
      // Check that Select All button exists and is visible
      const selectAllBtn = page.locator(`#select-all-${datasetName}`);
      await expect(selectAllBtn).toBeVisible();
      await expect(selectAllBtn).toContainText('Select All');
      
      // Deselect All button should not be visible initially
      const deselectAllBtn = page.locator(`#deselect-all-${datasetName}`);
      await expect(deselectAllBtn).not.toBeVisible();
    }
  });

  test('should select all columns when Select All button is clicked', async ({ page }) => {
    // Find first dataset with column badges
    const columnBadgesContainer = page.locator('[id^="column-badges-"]').first();
    
    if (await columnBadgesContainer.isVisible()) {
      const containerId = await columnBadgesContainer.getAttribute('id');
      const datasetName = containerId.replace('column-badges-', '');
      
      // Count initial unselected columns (badge-outline class)
      const initialUnselectedCount = await page.locator(`#column-badges-${datasetName} .badge-outline`).count();
      
      if (initialUnselectedCount > 0) {
        // Click Select All button
        const selectAllBtn = page.locator(`#select-all-${datasetName}`);
        await selectAllBtn.click();
        
        // Wait for HTMX response to update the column badges
        await page.waitForResponse('**/csv_select_all_dataset_columns/');
        await page.waitForTimeout(500); // Allow time for DOM update
        
        // Verify all columns are now selected (should have badge-primary, not badge-outline)
        const selectedColumns = await page.locator(`#column-badges-${datasetName} .badge-primary:not(.badge-outline)`).count();
        const totalColumns = await page.locator(`#column-badges-${datasetName} .column-badge`).count();
        
        expect(selectedColumns).toBe(totalColumns);
        
        // Verify no unselected columns remain
        const remainingUnselected = await page.locator(`#column-badges-${datasetName} .badge-outline`).count();
        expect(remainingUnselected).toBe(0);
      }
    }
  });

  test('should show Deselect All button after all columns are selected', async ({ page }) => {
    // Find first dataset with column badges
    const columnBadgesContainer = page.locator('[id^="column-badges-"]').first();
    
    if (await columnBadgesContainer.isVisible()) {
      const containerId = await columnBadgesContainer.getAttribute('id');
      const datasetName = containerId.replace('column-badges-', '');
      
      // Click Select All to select all columns
      const selectAllBtn = page.locator(`#select-all-${datasetName}`);
      if (await selectAllBtn.isVisible()) {
        await selectAllBtn.click();
        await page.waitForResponse('**/csv_select_all_dataset_columns/');
        await page.waitForTimeout(500);
        
        // Verify Deselect All button is now visible
        const deselectAllBtn = page.locator(`#deselect-all-${datasetName}`);
        await expect(deselectAllBtn).toBeVisible();
        await expect(deselectAllBtn).toContainText('Deselect All');
        
        // Select All button should no longer be visible
        await expect(selectAllBtn).not.toBeVisible();
      }
    }
  });

  test('should show Add to Workspace button when columns are selected', async ({ page }) => {
    // Find first dataset with column badges
    const columnBadgesContainer = page.locator('[id^="column-badges-"]').first();
    
    if (await columnBadgesContainer.isVisible()) {
      const containerId = await columnBadgesContainer.getAttribute('id');
      const datasetName = containerId.replace('column-badges-', '');
      
      // Click Select All to select all columns
      const selectAllBtn = page.locator(`#select-all-${datasetName}`);
      if (await selectAllBtn.isVisible()) {
        await selectAllBtn.click();
        await page.waitForResponse('**/csv_select_all_dataset_columns/');
        await page.waitForTimeout(500);
        
        // Verify Add to Workspace button appears
        const addToWorkspaceBtn = page.locator(`#add-to-workspace-${datasetName}`);
        await expect(addToWorkspaceBtn).toBeVisible();
        await expect(addToWorkspaceBtn).toContainText('Add to Workspace');
        
        // Button should show the count of selected columns
        const buttonText = await addToWorkspaceBtn.textContent();
        expect(buttonText).toMatch(/Add to Workspace \(\d+\)/);
      }
    }
  });

  test('should deselect all columns when Deselect All button is clicked', async ({ page }) => {
    // Find first dataset with column badges
    const columnBadgesContainer = page.locator('[id^="column-badges-"]').first();
    
    if (await columnBadgesContainer.isVisible()) {
      const containerId = await columnBadgesContainer.getAttribute('id');
      const datasetName = containerId.replace('column-badges-', '');
      
      // First select all columns
      const selectAllBtn = page.locator(`#select-all-${datasetName}`);
      if (await selectAllBtn.isVisible()) {
        await selectAllBtn.click();
        await page.waitForResponse('**/csv_select_all_dataset_columns/');
        await page.waitForTimeout(500);
        
        // Now click Deselect All
        const deselectAllBtn = page.locator(`#deselect-all-${datasetName}`);
        await deselectAllBtn.click();
        await page.waitForResponse('**/csv_deselect_all_dataset_columns/');
        await page.waitForTimeout(500);
        
        // Verify all columns are now unselected (should have badge-outline)
        const totalColumns = await page.locator(`#column-badges-${datasetName} .column-badge`).count();
        const unselectedColumns = await page.locator(`#column-badges-${datasetName} .badge-outline`).count();
        
        expect(unselectedColumns).toBe(totalColumns);
        
        // Select All button should be visible again
        await expect(selectAllBtn).toBeVisible();
        
        // Deselect All button should no longer be visible
        await expect(deselectAllBtn).not.toBeVisible();
        
        // Add to Workspace button should not be visible
        const addToWorkspaceBtn = page.locator(`#add-to-workspace-${datasetName}`);
        await expect(addToWorkspaceBtn).not.toBeVisible();
      }
    }
  });

  test('should handle HTMX errors gracefully during select/deselect operations', async ({ page }) => {
    // Mock a failed HTMX response for select all
    await page.route('**/csv_select_all_dataset_columns/', async route => {
      await route.fulfill({
        status: 500,
        contentType: 'text/html',
        body: 'Server Error'
      });
    });
    
    // Find first dataset with column badges
    const columnBadgesContainer = page.locator('[id^="column-badges-"]').first();
    
    if (await columnBadgesContainer.isVisible()) {
      const containerId = await columnBadgesContainer.getAttribute('id');
      const datasetName = containerId.replace('column-badges-', '');
      
      const selectAllBtn = page.locator(`#select-all-${datasetName}`);
      if (await selectAllBtn.isVisible()) {
        await selectAllBtn.click();
        
        // Wait for the error response
        await page.waitForResponse('**/csv_select_all_dataset_columns/');
        await page.waitForTimeout(500);
        
        // Error toast should appear
        await expect(page.locator('#status-toast')).toBeVisible();
        await expect(page.locator('#status-message')).toContainText('Request failed: 500');
      }
    }
  });

});