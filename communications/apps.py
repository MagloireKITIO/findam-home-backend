from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'communications'
    
    def ready(self):
        """Importe les signaux lors du chargement de l'application."""
        import communications.signals