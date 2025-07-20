from django.apps import AppConfig


class MetadataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arkumu.metadata'
    
    def ready(self):
        """Import signals when the app is ready"""
        import arkumu.metadata.signals
