# payments/admin.py
# Configuration de l'interface d'administration pour l'application payments

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import PaymentMethod, Transaction, Payout, Commission

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle PaymentMethod."""
    list_display = ('user_email', 'payment_type_display', 'nickname', 'is_default', 'is_verified', 'created_at')
    list_filter = ('payment_type', 'is_default', 'is_verified', 'created_at')
    search_fields = ('user__email', 'nickname', 'account_name', 'phone_number')
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('user', 'payment_type', 'nickname', 'is_default', 'is_verified')
        }),
        (_('Informations communes'), {
            'fields': ('account_number', 'account_name')
        }),
        (_('Mobile Money'), {
            'fields': ('phone_number', 'operator'),
            'classes': ('collapse',),
        }),
        (_('Carte Bancaire'), {
            'fields': ('last_digits', 'expiry_date'),
            'classes': ('collapse',),
        }),
        (_('Compte Bancaire'), {
            'fields': ('bank_name', 'branch_code'),
            'classes': ('collapse',),
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def user_email(self, obj):
        """Affiche l'email de l'utilisateur."""
        return obj.user.email
    
    def payment_type_display(self, obj):
        """Affiche le type de paiement."""
        return obj.get_payment_type_display()
    
    user_email.short_description = _('Utilisateur')
    payment_type_display.short_description = _('Type de paiement')

class BookingInline(admin.TabularInline):
    """Configuration inline pour les réservations d'un versement."""
    from bookings.models import Booking
    model = Payout.bookings.through
    extra = 0
    verbose_name = _('Réservation')
    verbose_name_plural = _('Réservations')
    can_delete = False
    readonly_fields = ['booking_id', 'booking_title', 'booking_dates', 'booking_amount']
    fields = ['booking_id', 'booking_title', 'booking_dates', 'booking_amount']
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def booking_id(self, obj):
        """Retourne l'ID de la réservation."""
        return obj.booking.id
    
    def booking_title(self, obj):
        """Retourne le titre du logement de la réservation."""
        return obj.booking.property.title
    
    def booking_dates(self, obj):
        """Retourne les dates de la réservation."""
        return f"{obj.booking.check_in_date} - {obj.booking.check_out_date}"
    
    def booking_amount(self, obj):
        """Retourne le montant de la réservation."""
        return obj.booking.total_price
    
    booking_id.short_description = _('ID')
    booking_title.short_description = _('Logement')
    booking_dates.short_description = _('Dates')
    booking_amount.short_description = _('Montant')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Transaction."""
    list_display = ('id', 'user_email', 'transaction_type_display', 'status_display', 'amount', 'currency', 'created_at')
    list_filter = ('transaction_type', 'status', 'currency', 'created_at')
    search_fields = ('user__email', 'description', 'external_reference', 'booking__id')
    readonly_fields = ['created_at', 'updated_at', 'processed_at']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('user', 'transaction_type', 'status', 'amount', 'currency')
        }),
        (_('Références'), {
            'fields': ('booking', 'payment_transaction', 'external_reference')
        }),
        (_('Description et notes'), {
            'fields': ('description', 'admin_notes')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at', 'processed_at')
        }),
    )
    
    def user_email(self, obj):
        """Affiche l'email de l'utilisateur."""
        return obj.user.email
    
    def transaction_type_display(self, obj):
        """Affiche le type de transaction."""
        return obj.get_transaction_type_display()
    
    def status_display(self, obj):
        """Affiche le statut de la transaction."""
        return obj.get_status_display()
    
    user_email.short_description = _('Utilisateur')
    transaction_type_display.short_description = _('Type de transaction')
    status_display.short_description = _('Statut')

@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Payout."""
    list_display = ('id', 'owner_email', 'amount', 'currency', 'status_display', 'created_at', 'processed_at')
    list_filter = ('status', 'currency', 'created_at', 'processed_at')
    search_fields = ('owner__email', 'notes', 'admin_notes', 'external_reference')
    readonly_fields = ['created_at', 'updated_at', 'processed_at']
    filter_horizontal = ('bookings',)
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('owner', 'amount', 'currency', 'payment_method', 'status')
        }),
        (_('Références'), {
            'fields': ('transaction', 'external_reference')
        }),
        (_('Période'), {
            'fields': ('period_start', 'period_end')
        }),
        (_('Notes'), {
            'fields': ('notes', 'admin_notes')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at', 'processed_at')
        }),
    )
    
    inlines = [BookingInline]
    
    def owner_email(self, obj):
        """Affiche l'email du propriétaire."""
        return obj.owner.email
    
    def status_display(self, obj):
        """Affiche le statut du versement."""
        return obj.get_status_display()
    
    owner_email.short_description = _('Propriétaire')
    status_display.short_description = _('Statut')
    
    def save_model(self, request, obj, form, change):
        """
        Surcharge pour gérer l'action de complétion d'un versement.
        Si le statut passe à 'completed', marquer comme terminé.
        """
        if change and 'status' in form.changed_data and obj.status == 'completed':
            obj.mark_as_completed()
        else:
            super().save_model(request, obj, form, change)

@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Commission."""
    list_display = ('id', 'booking_ref', 'owner_amount', 'tenant_amount', 'total_amount', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('booking__id', 'booking__property__title', 'booking__tenant__email')
    readonly_fields = ['total_amount', 'created_at', 'updated_at']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('booking', 'owner_amount', 'tenant_amount', 'total_amount')
        }),
        (_('Taux de commission'), {
            'fields': ('owner_rate', 'tenant_rate')
        }),
        (_('Transaction'), {
            'fields': ('transaction',)
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def booking_ref(self, obj):
        """Affiche la référence de la réservation."""
        return f"{obj.booking.property.title} - {obj.booking.id}"
    
    booking_ref.short_description = _('Réservation')
    
    def has_add_permission(self, request):
        """Désactive l'ajout manuel de commissions."""
        return False
    
    def save_model(self, request, obj, form, change):
        """
        Surcharge pour recalculer le montant total si les montants changent.
        """
        if change and ('owner_amount' in form.changed_data or 'tenant_amount' in form.changed_data):
            obj.total_amount = obj.owner_amount + obj.tenant_amount
        super().save_model(request, obj, form, change)