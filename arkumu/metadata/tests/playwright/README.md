# Playwright Testing for Arkumu Metadata App

This directory contains end-to-end tests for the Arkumu metadata application using Playwright.

These tests are located in the Django app's test directory following Django conventions: `arkumu/metadata/tests/playwright/`

## Setup

Since this project uses Docker Compose for development, the setup is different from a regular Node.js project.

1. **Install Node.js dependencies (from theme directory):**
   ```bash
   cd theme/static_src
   npm install
   ```

2. **Install Playwright browsers:**
   ```bash
   npm run install:playwright
   ```

3. **Start the Django application with Docker:**
   ```bash
   # From project root
   docker compose -f docker-compose.local.yml up -d django
   ```

4. **Build theme assets (required for styling):**
   ```bash
   # From theme/static_src directory
   npm run build
   ```

## Running Tests

All test commands should be run from the `theme/static_src` directory:

```bash
cd theme/static_src
```

### Docker-based Testing (Recommended)

**Start Django with Docker and run tests:**
```bash
npm run test:docker
```

**Start Django with Docker and run tests in UI mode:**
```bash
npm run test:docker:ui
```

**Stop Docker containers after testing:**
```bash
npm run test:docker:stop
```

### Manual Testing (Django must be running already)

**Run all tests (requires Django to be running on localhost:8000):**
```bash
npm test
```

**Run with UI mode (interactive):**
```bash
npm run test:ui
```

**Run in debug mode:**
```bash
npm run test:debug
```

**Run with browser visible (headed mode):**
```bash
npm run test:headed
```

**Run specific test file:**
```bash
npm run test:csv-mapping
```

**Build theme and run tests:**
```bash
npm run build:test
```

**View test report:**
```bash
npm run test:report
```

## Test Files

Located in `arkumu/metadata/tests/playwright/`:

- `csv_mapping_editor.spec.js` - Tests for the CSV Mapping Editor interface including:
  - Page loading and basic UI elements
  - Organization selector with HTMX integration
  - Error handling and toast notifications
  - HTMX event handlers and dynamic content loading
  - Empty state functionality

## Configuration

The Playwright configuration is in `theme/static_src/playwright.config.js` and includes:
- Base URL configuration (defaults to http://localhost:8000)
- Multiple browser testing (Chrome, Firefox, Safari)
- Mobile device testing
- Automatic Tailwind CSS build before tests
- Automatic Django server startup
- Screenshots and videos on failure
- Trace collection for debugging

## Theme Integration

This setup is integrated with the Arkumu theme structure:
- Frontend dependencies are managed in `theme/static_src/package.json`
- Tailwind CSS is automatically built before running tests
- DaisyUI components and styling are available during testing
- The configuration ensures CSS is compiled before server startup

## Environment Variables

- `BASE_URL` - Override the default base URL (default: http://localhost:8000)
- `CI` - Set to enable CI-specific configurations

## Django Integration

The tests are designed to work with Django running in Docker Compose. The recommended approach is to use the Docker-based test commands which automatically handle the Django server.

If running Django manually, make sure your application is properly configured:

**With Docker Compose (recommended):**
```bash
# Start all services
docker compose -f docker-compose.local.yml up -d

# Or just Django (if you only need the web server)
docker compose -f docker-compose.local.yml up -d django
```

**Manual Django setup:**
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver 8000
```

## Test Structure

Tests follow the Page Object Model pattern where appropriate and use Playwright's built-in assertions for reliable testing. Each test file focuses on specific functionality:

- **Setup**: Each test navigates to the appropriate page
- **Assertions**: Use expect() with Playwright locators
- **Error Handling**: Tests include scenarios for network errors, HTMX failures, and edge cases
- **Cleanup**: Tests clean up any created elements or state

## Debugging

For debugging failed tests:

1. Use `npm run test:debug` to run in debug mode
2. Use `npm run test:headed` to see the browser while tests run
3. Check the HTML report with `npm run test:report`
4. Screenshots and videos are automatically captured on failure

## Adding New Tests

When adding new tests:

1. Create new `.spec.js` files in this directory
2. Follow the existing naming convention
3. Use descriptive test names that explain what is being tested
4. Include both positive and negative test cases
5. Test error scenarios and edge cases
6. Update this README when adding new test files