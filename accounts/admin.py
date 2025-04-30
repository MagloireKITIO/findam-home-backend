# accounts/admin.py
# Configuration de l'interface d'administration pour les modèles d'accounts

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, Profile, OwnerSubscription

class ProfileInline(admin.StackedInline):
    """Configuration inline pour le profil utilisateur."""
    model = Profile
    can_delete = False
    verbose_name = _('Profil')
    verbose_name_plural = _('Profils')
    fk_name = 'user'

class UserAdmin(BaseUserAdmin):
    """Configuration de l'admin pour le modèle User personnalisé."""
    list_display = ('email', 'phone_number', 'first_name', 'last_name', 'user_type', 'is_verified', 'is_staff')
    list_filter = ('is_staff', 'is_active', 'is_verified', 'user_type')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Informations personnelles'), {'fields': ('first_name', 'last_name', 'phone_number')}),
        (_('Type d\'utilisateur'), {'fields': ('user_type',)}),
        (_('Permissions'), {'fields': ('is_active', 'is_verified', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Dates importantes'), {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'phone_number', 'password1', 'password2', 'user_type'),
        }),
    )
    search_fields = ('email', 'phone_number', 'first_name', 'last_name')
    ordering = ('email',)
    inlines = (ProfileInline,)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Profile."""
    list_display = ('user', 'city', 'country', 'verification_status', 'avg_rating')
    list_filter = ('verification_status', 'country', 'city')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'city')
    readonly_fields = ('avg_rating', 'rating_count', 'created_at', 'updated_at')

@admin.register(OwnerSubscription)
class OwnerSubscriptionAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle OwnerSubscription."""
    list_display = ('owner', 'subscription_type', 'status', 'start_date', 'end_date', 'is_active')
    list_filter = ('subscription_type', 'status')
    search_fields = ('owner__email', 'owner__first_name', 'owner__last_name')
    readonly_fields = ('created_at', 'updated_at')
    
    # Rendre is_active disponible comme colonne triable
    def is_active(self, obj):
        return obj.is_active()
    is_active.boolean = True
    is_active.short_description = _('Actif')

# Enregistrement du modèle User avec la configuration personnalisée
admin.site.register(User, UserAdmin)