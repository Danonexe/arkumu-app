from django.apps import AppConfig


class ImportConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arkumu.importer'
    
    def ready(self):
        # Import tasks to ensure they are registered with Huey
        try:
            from arkumu.importer.tasks.import_metadata import run_mapping_aware_import_workflow
        except ImportError:
            # Fall back to the main tasks module if it exists
            try:
                from arkumu.importer.tasks import run_import
            except ImportError:
                pass  # No tasks to import
