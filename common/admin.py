# common/admin.py
from django.contrib import admin
from .models import SystemConfiguration

@admin.register(SystemConfiguration)
class SystemConfigurationAdmin(admin.ModelAdmin):
    """Admin pour les configurations système."""
    list_display = ['key', 'value', 'last_updated']
    search_fields = ['key', 'value', 'description']
    readonly_fields = ['last_updated']
    fieldsets = (
        (None, {
            'fields': ('key', 'value', 'description')
        }),
        ('Métadonnées', {
            'fields': ('last_updated',),
            'classes': ('collapse',)
        })
    )
    
    def has_delete_permission(self, request, obj=None):
        """Restreindre la suppression des configurations critiques."""
        if obj and obj.key in ['CANCELLATION_GRACE_PERIOD_MINUTES']:
            return False
        return super().has_delete_permission(request, obj)