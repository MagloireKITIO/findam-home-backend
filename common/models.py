# common/models.py

from django.db import models

class SystemConfiguration(models.Model):
    """Modèle pour les configurations système globales."""
    
    key = models.CharField(max_length=100, unique=True, help_text="Clé de configuration")
    value = models.CharField(max_length=255, help_text="Valeur de configuration")
    description = models.TextField(blank=True, help_text="Description de cette configuration")
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Configuration système"
        verbose_name_plural = "Configurations système"
    
    def __str__(self):
        return f"{self.key}: {self.value}"
    
    @classmethod
    def get_value(cls, key, default=None):
        """Récupère la valeur d'une configuration par sa clé."""
        try:
            config = cls.objects.get(key=key)
            return config.value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def set_value(cls, key, value, description=None):
        """Définit la valeur d'une configuration par sa clé."""
        config, created = cls.objects.update_or_create(
            key=key,
            defaults={
                'value': value,
                'description': description or ''
            }
        )
        return config