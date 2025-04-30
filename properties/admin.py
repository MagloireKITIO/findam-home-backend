# properties/admin.py
# Configuration de l'interface d'administration pour les modèles properties

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import (
    Amenity,
    City,
    Neighborhood,
    Property,
    PropertyImage,
    Availability,
    LongStayDiscount
)

class NeighborhoodInline(admin.TabularInline):
    """Configuration inline pour les quartiers d'une ville."""
    model = Neighborhood
    extra = 1

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle City."""
    list_display = ('name',)
    search_fields = ('name',)
    inlines = [NeighborhoodInline]

@admin.register(Neighborhood)
class NeighborhoodAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Neighborhood."""
    list_display = ('name', 'city')
    list_filter = ('city',)
    search_fields = ('name', 'city__name')

@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Amenity."""
    list_display = ('name', 'icon', 'category')
    list_filter = ('category',)
    search_fields = ('name', 'category')

class PropertyImageInline(admin.TabularInline):
    """Configuration inline pour les images d'un logement."""
    model = PropertyImage
    extra = 1
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        """Affiche une prévisualisation de l'image."""
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" />', obj.image.url)
        return "Pas d'image"
    
    image_preview.short_description = _("Aperçu")

class LongStayDiscountInline(admin.TabularInline):
    """Configuration inline pour les réductions de long séjour d'un logement."""
    model = LongStayDiscount
    extra = 1

class AvailabilityInline(admin.TabularInline):
    """Configuration inline pour les indisponibilités d'un logement."""
    model = Availability
    extra = 1
    fields = ('start_date', 'end_date', 'booking_type', 'external_client_name', 'external_client_phone')

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Property."""
    list_display = ('title', 'owner', 'city', 'neighborhood', 'property_type', 
                    'price_per_night', 'capacity', 'is_published', 'is_verified')
    list_filter = ('is_published', 'is_verified', 'property_type', 'city', 
                   'allow_discount', 'cancellation_policy')
    search_fields = ('title', 'description', 'owner__email', 'owner__first_name', 
                     'owner__last_name', 'city__name', 'neighborhood__name')
    readonly_fields = ('avg_rating', 'rating_count', 'created_at', 'updated_at')
    filter_horizontal = ('amenities',)
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('owner', 'title', 'description', 'property_type')
        }),
        (_('Configuration'), {
            'fields': ('capacity', 'bedrooms', 'bathrooms')
        }),
        (_('Localisation'), {
            'fields': ('city', 'neighborhood', 'address', 'latitude', 'longitude')
        }),
        (_('Tarifs'), {
            'fields': ('price_per_night', 'price_per_week', 'price_per_month', 
                      'cleaning_fee', 'security_deposit')
        }),
        (_('Options'), {
            'fields': ('allow_discount', 'cancellation_policy', 'amenities')
        }),
        (_('Statut'), {
            'fields': ('is_published', 'is_verified')
        }),
        (_('Évaluations'), {
            'fields': ('avg_rating', 'rating_count')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    inlines = [PropertyImageInline, LongStayDiscountInline, AvailabilityInline]
    
    def save_model(self, request, obj, form, change):
        """Ajout automatique du propriétaire lors de la création depuis l'admin."""
        if not change and not obj.owner:  # Seulement lors de la création
            obj.owner = request.user
        super().save_model(request, obj, form, change)

@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle PropertyImage."""
    list_display = ('property', 'image_preview', 'is_main', 'order', 'created_at')
    list_filter = ('is_main', 'property__title')
    search_fields = ('property__title', 'caption')
    
    def image_preview(self, obj):
        """Affiche une prévisualisation de l'image."""
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" />', obj.image.url)
        return "Pas d'image"
    
    image_preview.short_description = _("Aperçu")

@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Availability."""
    list_display = ('property', 'start_date', 'end_date', 'booking_type', 'external_client_name')
    list_filter = ('booking_type', 'start_date', 'end_date')
    search_fields = ('property__title', 'external_client_name', 'external_client_phone', 'notes')
    date_hierarchy = 'start_date'

@admin.register(LongStayDiscount)
class LongStayDiscountAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle LongStayDiscount."""
    list_display = ('property', 'min_days', 'discount_percentage')
    list_filter = ('min_days', 'discount_percentage')
    search_fields = ('property__title',)