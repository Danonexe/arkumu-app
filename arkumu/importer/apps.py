from django.apps import AppConfig


class ImportConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arkumu.importer'
    
    def ready(self):
        # Import tasks to ensure they are registered with Huey
        from arkumu.importer.tasks import import_metadata
