from django.apps import AppConfig


class CidocConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'arkumu.cidoc'
    
    def ready(self):
        """
        Connect signals when the app is ready.
        This ensures graph operations are handled via signals
        rather than being coupled to the model methods.
        """
        # Import signals module to connect the signal handlers
        from arkumu.cidoc import signals  # noqa
