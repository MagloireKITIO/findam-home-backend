# bookings/admin.py
# Configuration de l'interface d'administration pour les modèles bookings

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import Booking, PromoCode, BookingReview, PaymentTransaction

class PaymentTransactionInline(admin.TabularInline):
    """Configuration inline pour les transactions de paiement d'une réservation."""
    model = PaymentTransaction
    extra = 0
    readonly_fields = ['created_at', 'updated_at']
    fields = ['amount', 'payment_method', 'status', 'transaction_id', 'created_at']

class BookingReviewInline(admin.StackedInline):
    """Configuration inline pour l'avis d'une réservation."""
    model = BookingReview
    extra = 0
    readonly_fields = ['created_at', 'updated_at']
    fields = ['rating', 'comment', 'is_from_owner', 'created_at']

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Booking."""
    list_display = ('id', 'property_title', 'tenant_name', 'check_in_date', 'check_out_date', 
                     'total_price', 'status', 'payment_status', 'created_at')
    list_filter = ('status', 'payment_status', 'created_at', 'check_in_date', 
                   'property__city', 'property__property_type')
    search_fields = ('id', 'property__title', 'tenant__email', 'tenant__first_name', 
                     'tenant__last_name', 'property__city__name')
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at', 'cancelled_at']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('property', 'tenant', 'check_in_date', 'check_out_date', 'guests_count')
        }),
        (_('Prix et paiement'), {
            'fields': ('base_price', 'cleaning_fee', 'security_deposit', 'service_fee',
                      'promo_code', 'discount_amount', 'total_price')
        }),
        (_('Statuts'), {
            'fields': ('status', 'payment_status')
        }),
        (_('Communication'), {
            'fields': ('special_requests', 'notes')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at', 'cancelled_at', 'cancelled_by')
        }),
    )
    
    inlines = [PaymentTransactionInline, BookingReviewInline]
    
    def property_title(self, obj):
        """Affiche le titre du logement."""
        return obj.property.title
    
    def tenant_name(self, obj):
        """Affiche le nom du locataire."""
        return obj.tenant.get_full_name() or obj.tenant.email
    
    property_title.short_description = _('Logement')
    tenant_name.short_description = _('Locataire')

@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle PromoCode."""
    list_display = ('code', 'property_title', 'tenant_name', 'discount_percentage', 
                    'is_active', 'expiry_date', 'created_at')
    list_filter = ('is_active', 'created_at', 'expiry_date')
    search_fields = ('code', 'property__title', 'tenant__email', 'tenant__first_name', 
                     'tenant__last_name')
    readonly_fields = ['created_at', 'created_by']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('code', 'property', 'tenant', 'discount_percentage')
        }),
        (_('Statut'), {
            'fields': ('is_active', 'expiry_date')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'created_by')
        }),
    )
    
    def property_title(self, obj):
        """Affiche le titre du logement."""
        return obj.property.title
    
    def tenant_name(self, obj):
        """Affiche le nom du locataire."""
        return obj.tenant.get_full_name() or obj.tenant.email
    
    property_title.short_description = _('Logement')
    tenant_name.short_description = _('Locataire')

@admin.register(BookingReview)
class BookingReviewAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle BookingReview."""
    list_display = ('booking_ref', 'rating', 'reviewer_type', 'created_at')
    list_filter = ('rating', 'is_from_owner', 'created_at')
    search_fields = ('booking__id', 'booking__property__title', 
                     'booking__tenant__email', 'comment')
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('booking', 'rating', 'comment', 'is_from_owner')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def booking_ref(self, obj):
        """Affiche la référence de la réservation."""
        return f"{obj.booking.property.title} - {obj.booking.id}"
    
    def reviewer_type(self, obj):
        """Affiche le type de l'utilisateur qui a laissé l'avis."""
        return _('Propriétaire') if obj.is_from_owner else _('Locataire')
    
    booking_ref.short_description = _('Réservation')
    reviewer_type.short_description = _('Type de l\'avis')

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle PaymentTransaction."""
    list_display = ('id', 'booking_ref', 'amount', 'payment_method', 
                    'status', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('id', 'booking__id', 'booking__property__title', 
                     'booking__tenant__email', 'transaction_id')
    readonly_fields = ['created_at', 'updated_at', 'payment_response_formatted']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('booking', 'amount', 'payment_method', 'status')
        }),
        (_('Détails du paiement'), {
            'fields': ('transaction_id', 'payment_response_formatted')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def booking_ref(self, obj):
        """Affiche la référence de la réservation."""
        return f"{obj.booking.property.title} - {obj.booking.id}"
    
    def payment_response_formatted(self, obj):
        """Affiche la réponse de paiement formatée en JSON."""
        if obj.payment_response:
            import json
            return format_html(
                '<pre>{}</pre>',
                json.dumps(obj.payment_response, indent=2)
            )
        return "-"
    
    booking_ref.short_description = _('Réservation')
    payment_response_formatted.short_description = _('Réponse de paiement')