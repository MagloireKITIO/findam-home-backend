# payments/admin.py
# Configuration de l'interface d'administration pour l'application payments

from django.utils import timezone
from gettext import ngettext
from pyexpat.errors import messages
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import PaymentMethod, Transaction, Payout, Commission, PaymentMethodChange

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle PaymentMethod."""
    list_display = ('user', 'payment_type', 'nickname', 'status', 'is_active', 'created_at')
    list_filter = ('payment_type', 'status', 'is_active', 'operator')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'nickname')
    list_editable = ('is_active',)
    readonly_fields = ('notchpay_recipient_id', 'verification_attempts', 'last_verification_at')
    
    fieldsets = (
        (_('Informations générales'), {
            'fields': ('user', 'payment_type', 'nickname', 'is_default', 'is_active', 'status')
        }),
        (_('Informations Mobile Money'), {
            'fields': ('phone_number', 'operator'),
            'classes': ('collapse',)
        }),
        (_('Informations bancaires'), {
            'fields': ('account_number', 'account_name', 'bank_name', 'branch_code'),
            'classes': ('collapse',)
        }),
        (_('Vérification'), {
            'fields': ('notchpay_recipient_id', 'verification_attempts', 'last_verification_at', 'verification_notes'),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:  # Editing
            readonly.extend(['user', 'payment_type'])
        return readonly
    
    def user_email(self, obj):
        """Affiche l'email de l'utilisateur."""
        return obj.user.email
    
    def payment_type_display(self, obj):
        """Affiche le type de paiement."""
        return obj.get_payment_type_display()
    
    user_email.short_description = _('Utilisateur')
    payment_type_display.short_description = _('Type de paiement')

@admin.register(PaymentMethodChange)
class PaymentMethodChangeAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour les modifications de méthodes de paiement des propriétaires"""
    
    list_display = [
        'get_owner_name', 
        'get_owner_email', 
        'change_type', 
        'get_payment_method_type',
        'status', 
        'created_at',
        'reviewed_by'
    ]
    
    list_filter = [
        'change_type', 
        'status', 
        'created_at',
        'payment_method__payment_type'
    ]
    
    search_fields = [
        'payment_method__user__first_name',
        'payment_method__user__last_name',
        'payment_method__user__email'
    ]
    
    readonly_fields = [
        'id',
        'payment_method', 
        'change_type', 
        'modified_by',
        'previous_data',
        'created_at',
        'updated_at'
    ]
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('payment_method', 'change_type', 'status', 'modified_by')
        }),
        (_('Dates'), {
            'fields': ('created_at', 'updated_at', 'reviewed_at')
        }),
        (_('Révision'), {
            'fields': ('reviewed_by', 'admin_notes')
        }),
        (_('Données techniques'), {
            'fields': ('id', 'previous_data'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-created_at']
    
    def get_owner_name(self, obj):
        return obj.payment_method.user.get_full_name() or obj.payment_method.user.email
    get_owner_name.short_description = _('Propriétaire')
    
    def get_owner_email(self, obj):
        return obj.payment_method.user.email
    get_owner_email.short_description = _('Email')
    
    def get_payment_method_type(self, obj):
        return obj.payment_method.get_payment_type_display()
    get_payment_method_type.short_description = _('Type de méthode')
    
    def save_model(self, request, obj, form, change):
        """Auto-remplir reviewed_by et reviewed_at lors de l'approbation/rejet"""
        if change and form.initial.get('status') != form.cleaned_data.get('status'):
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)
    
    # Ajout des actions custom
    actions = ['approve_changes', 'reject_changes']
    
    def approve_changes(self, request, queryset):
        """Approuver les modifications sélectionnées"""
        updated = queryset.filter(status='pending').update(
            status='approved',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated} modification(s) approuvée(s).")
    approve_changes.short_description = _("Approuver les modifications sélectionnées")
    
    def reject_changes(self, request, queryset):
        """Rejeter les modifications sélectionnées"""
        updated = queryset.filter(status='pending').update(
            status='rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{updated} modification(s) rejetée(s).")
    reject_changes.short_description = _("Rejeter les modifications sélectionnées")
    
    def has_delete_permission(self, request, obj=None):
        """Empêcher la suppression des logs de modification"""
        return False

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
    """Configuration de l'admin pour le modèle Payout avec gestion d'anti-escrow."""
    list_display = ('id', 'owner_email', 'amount', 'currency', 'status_display', 'scheduled_at_display', 'created_at', 'processed_at')
    list_filter = ('status', 'currency', 'created_at', 'processed_at', 'scheduled_at')
    search_fields = ('owner__email', 'notes', 'admin_notes', 'external_reference', 'escrow_reason')
    readonly_fields = ['created_at', 'updated_at', 'processed_at']
    filter_horizontal = ('bookings',)
    actions = ['mark_as_ready', 'process_payouts', 'cancel_payouts']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('owner', 'amount', 'currency', 'payment_method', 'status')
        }),
        (_('Programmation anti-escrow'), {
            'fields': ('scheduled_at', 'processed_by', 'escrow_reason'),
            'classes': ('wide',),
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
            'fields': ('created_at', 'updated_at', 'processed_at'),
            'classes': ('collapse',),
        }),
    )
    
    inlines = [BookingInline]
    
    def owner_email(self, obj):
        """Affiche l'email du propriétaire."""
        return obj.owner.email
    
    def status_display(self, obj):
        """Affiche le statut du versement avec code couleur."""
        status_colors = {
            'pending': 'gray',
            'scheduled': 'blue',
            'ready': 'green',
            'processing': 'orange',
            'completed': 'green',
            'failed': 'red',
            'cancelled': 'red',
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color:white; background-color:{}; padding:3px 10px; border-radius:10px;">{}</span>',
            color, obj.get_status_display()
        )
    
    def scheduled_at_display(self, obj):
        """Affiche la date programmée avec formatage."""
        if not obj.scheduled_at:
            return '-'
        
        # Vérifier si la date est passée ou future
        now = timezone.now()
        if obj.scheduled_at < now:
            return format_html(
                '<span style="color: #777;">{} <small>(passée)</small></span>',
                obj.scheduled_at.strftime('%d/%m/%Y %H:%M')
            )
        else:
            # Calculer le délai
            delta = obj.scheduled_at - now
            days = delta.days
            hours = delta.seconds // 3600
            
            if days > 0:
                delay_text = f"Dans {days}j {hours}h"
            else:
                delay_text = f"Dans {hours}h"
            
            return format_html(
                '<span>{} <small style="color: #28a745;">({}))</small></span>',
                obj.scheduled_at.strftime('%d/%m/%Y %H:%M'), delay_text
            )
    
    owner_email.short_description = _('Propriétaire')
    status_display.short_description = _('Statut')
    scheduled_at_display.short_description = _('Date programmée')
    
    def mark_as_ready(self, request, queryset):
        """Action pour marquer les versements sélectionnés comme prêts à être traités."""
        updated = 0
        for payout in queryset.filter(status='scheduled'):
            payout.status = 'ready'
            payout.admin_notes += f"\nMarqué comme prêt par {request.user.email} le {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            payout.save(update_fields=['status', 'admin_notes'])
            updated += 1
        
        self.message_user(
            request,
            ngettext(
                '%d versement a été marqué comme prêt à être traité.',
                '%d versements ont été marqués comme prêts à être traités.',
                updated
            ) % updated,
            messages.SUCCESS if updated > 0 else messages.WARNING
        )
    
    def process_payouts(self, request, queryset):
        """Action pour traiter immédiatement les versements sélectionnés."""
        from payments.services.payout_service import PayoutService
        
        # Marquer d'abord tous les versements programmés comme prêts
        for payout in queryset.filter(status='scheduled'):
            payout.status = 'ready'
            payout.admin_notes += f"\nMarqué comme prêt par {request.user.email} le {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            payout.save(update_fields=['status', 'admin_notes'])
        
        # Ensuite, traiter tous les versements prêts
        ready_payouts = [p.id for p in queryset.filter(status='ready')]
        
        if ready_payouts:
            # Exécuter le traitement de façon asynchrone pour éviter de bloquer l'admin
            from django.core.management import call_command
            # Lancer la commande dans un processus séparé
            import threading
            thread = threading.Thread(
                target=lambda: call_command('process_payouts', payout_ids=','.join([str(pid) for pid in ready_payouts]))
            )
            thread.start()
            
            self.message_user(
                request,
                ngettext(
                    'Traitement du versement lancé en arrière-plan.',
                    'Traitement de %d versements lancé en arrière-plan.',
                    len(ready_payouts)
                ) % len(ready_payouts),
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                _('Aucun versement prêt à être traité parmi les sélectionnés.'),
                messages.WARNING
            )
    
    def cancel_payouts(self, request, queryset):
        """Action pour annuler les versements sélectionnés."""
        updated = 0
        for payout in queryset.filter(status__in=['pending', 'scheduled', 'ready']):
            payout.status = 'cancelled'
            payout.processed_by = request.user
            payout.admin_notes += f"\nAnnulé par {request.user.email} le {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            payout.save(update_fields=['status', 'processed_by', 'admin_notes'])
            updated += 1
        
        self.message_user(
            request,
            ngettext(
                '%d versement a été annulé.',
                '%d versements ont été annulés.',
                updated
            ) % updated,
            messages.SUCCESS if updated > 0 else messages.WARNING
        )
    
    def get_queryset(self, request):
        """Optimise les requêtes avec les jointures nécessaires."""
        queryset = super().get_queryset(request)
        return queryset.select_related('owner', 'payment_method', 'processed_by')
    
    def save_model(self, request, obj, form, change):
        """
        Surcharge pour gérer les actions spéciales lors de la sauvegarde.
        """
        if change and 'status' in form.changed_data:
            # Si on change le statut manuellement
            old_status = Payout.objects.get(pk=obj.pk).status if obj.pk else None
            new_status = obj.status
            
            # Si le statut passe à 'completed'
            if new_status == 'completed' and old_status != 'completed':
                obj.processed_at = timezone.now()
                if not obj.processed_by:
                    obj.processed_by = request.user
            
            # Si le statut passe à 'ready' depuis 'scheduled'
            if old_status == 'scheduled' and new_status == 'ready':
                if not obj.admin_notes:
                    obj.admin_notes = ""
                obj.admin_notes += f"\nMarqué comme prêt par {request.user.email} le {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Si le statut passe à 'cancelled'
            if new_status == 'cancelled':
                if not obj.processed_by:
                    obj.processed_by = request.user
        
        super().save_model(request, obj, form, change)
    
    mark_as_ready.short_description = _("Marquer comme prêts à verser")
    process_payouts.short_description = _("Traiter les versements immédiatement")
    cancel_payouts.short_description = _("Annuler les versements sélectionnés")

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