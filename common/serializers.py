# common/serializers.py
from rest_framework import serializers
from .models import SystemConfiguration

class SystemConfigurationSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les configurations système."""
    
    class Meta:
        model = SystemConfiguration
        fields = ['key', 'value', 'description', 'last_updated']
        read_only_fields = ['key', 'value', 'description', 'last_updated']