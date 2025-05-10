# bookings/admin.py
# Configuration de l'interface d'administration pour les modèles bookings

from datetime import timezone
from django.urls import reverse
from gettext import ngettext
from pyexpat.errors import messages
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

class PayoutInline(admin.TabularInline):
    """Configuration inline pour les versements d'une réservation."""
    from payments.models import Payout
    model = Payout.bookings.through
    extra = 0
    verbose_name = _('Versement programmé')
    verbose_name_plural = _('Versements programmés')
    can_delete = False
    fields = ['payout_id', 'payout_amount', 'payout_status', 'payout_scheduled']
    readonly_fields = ['payout_id', 'payout_amount', 'payout_status', 'payout_scheduled']
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def payout_id(self, obj):
        """Renvoie un lien vers le versement."""
        payout = obj.payout
        url = reverse(
            f'admin:{payout._meta.app_label}_{payout._meta.model_name}_change',
            args=[payout.id]
        )
        return format_html('<a href="{}">{}</a>', url, payout.id)
    
    def payout_amount(self, obj):
        """Renvoie le montant du versement."""
        return f"{obj.payout.amount} {obj.payout.currency}"
    
    def payout_status(self, obj):
        """Renvoie le statut du versement avec code couleur."""
        payout = obj.payout
        status_colors = {
            'pending': '#6c757d',
            'scheduled': '#007bff',
            'ready': '#28a745',
            'processing': '#fd7e14',
            'completed': '#28a745',
            'failed': '#dc3545',
            'cancelled': '#dc3545',
        }
        color = status_colors.get(payout.status, '#6c757d')
        return format_html(
            '<span style="color:white; background-color:{}; padding:3px 10px; border-radius:10px;">{}</span>',
            color, payout.get_status_display()
        )
    
    def payout_scheduled(self, obj):
        """Renvoie la date programmée du versement."""
        payout = obj.payout
        if not payout.scheduled_at:
            return '-'
        return payout.scheduled_at.strftime('%d/%m/%Y %H:%M')
    
    payout_id.short_description = _('ID')
    payout_amount.short_description = _('Montant')
    payout_status.short_description = _('Statut')
    payout_scheduled.short_description = _('Date programmée')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Booking avec gestion d'anti-escrow."""
    list_display = (
        'id', 'property_title', 'tenant_name', 'check_in_date', 'check_out_date', 
        'total_price', 'status', 'payment_status', 'escrow_status', 'created_at'
    )
    list_filter = (
        'status', 'payment_status', 'created_at', 'check_in_date', 
        'property__city', 'property__property_type'
    )
    search_fields = (
        'id', 'property__title', 'tenant__email', 'tenant__first_name', 
        'tenant__last_name', 'property__city__name'
    )
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at', 'cancelled_at', 'escrow_status']
    actions = ['schedule_payout', 'release_funds_immediately', 'mark_as_completed']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('property', 'tenant', 'check_in_date', 'check_out_date', 'guests_count')
        }),
        (_('Prix et paiement'), {
            'fields': ('base_price', 'cleaning_fee', 'security_deposit', 'service_fee',
                      'promo_code', 'discount_amount', 'total_price')
        }),
        (_('Statuts'), {
            'fields': ('status', 'payment_status', 'escrow_status')
        }),
        (_('Communication'), {
            'fields': ('special_requests', 'notes')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at', 'cancelled_at', 'cancelled_by')
        }),
    )
    
    inlines = [PaymentTransactionInline, PayoutInline, BookingReviewInline]
    
    def property_title(self, obj):
        """Affiche le titre du logement."""
        return obj.property.title
    
    def tenant_name(self, obj):
        """Affiche le nom du locataire."""
        return obj.tenant.get_full_name() or obj.tenant.email
    
    def escrow_status(self, obj):
        """Affiche le statut de séquestre pour cette réservation."""
        # Vérifier s'il existe un versement programmé
        from payments.models import Payout
        payout = Payout.objects.filter(
            bookings__id=obj.id
        ).order_by('-created_at').first()
        
        if not payout:
            if obj.payment_status == 'paid':
                return format_html(
                    '<span style="color:#6c757d;">En séquestre (non programmé)</span>'
                )
            else:
                return format_html(
                    '<span style="color:#dc3545;">Non payé</span>'
                )
        
        status_styles = {
            'pending': ('En séquestre', '#6c757d'),
            'scheduled': ('Programmé', '#007bff'),
            'ready': ('Prêt à verser', '#28a745'),
            'processing': ('Versement en cours', '#fd7e14'),
            'completed': ('Versé', '#28a745'),
            'failed': ('Échec du versement', '#dc3545'),
            'cancelled': ('Versement annulé', '#dc3545'),
        }
        
        label, color = status_styles.get(payout.status, ('Inconnu', '#6c757d'))
        
        # Ajouter la date programmée si pertinent
        date_info = ""
        if payout.status == 'scheduled' and payout.scheduled_at:
            date_info = f" pour le {payout.scheduled_at.strftime('%d/%m/%Y')}"
        elif payout.status == 'completed' and payout.processed_at:
            date_info = f" le {payout.processed_at.strftime('%d/%m/%Y')}"
        
        return format_html(
            '<span style="color:{}">{}{}</span>',
            color, label, date_info
        )
    
    def schedule_payout(self, request, queryset):
        """
        Action pour programmer un versement pour les réservations sélectionnées.
        """
        from payments.services.payout_service import PayoutService
        
        payouts_created = 0
        skipped = 0
        
        for booking in queryset:
            # Vérifier les conditions pour programmer un versement
            if booking.payment_status != 'paid':
                skipped += 1
                continue
            
            # Vérifier s'il y a déjà un versement programmé
            from payments.models import Payout
            if Payout.objects.filter(
                bookings__id=booking.id,
                status__in=['pending', 'scheduled', 'ready', 'processing']
            ).exists():
                skipped += 1
                continue
            
            # Programmer le versement 24h après le check-in
            check_in_datetime = timezone.make_aware(
                timezone.datetime.combine(booking.check_in_date, timezone.datetime.min.time())
            )
            scheduled_date = check_in_datetime + timezone.timedelta(hours=24)
            
            # Si la date de check-in est déjà passée, programmer pour dans 1h
            if scheduled_date <= timezone.now():
                scheduled_date = timezone.now() + timezone.timedelta(hours=1)
            
            payout = PayoutService.schedule_payout_for_booking(booking, scheduled_date)
            
            if payout:
                payouts_created += 1
                payout.admin_notes += f"\nVersement programmé manuellement par {request.user.email}"
                payout.save(update_fields=['admin_notes'])
        
        if payouts_created > 0:
            self.message_user(
                request,
                ngettext(
                    '%d versement a été programmé avec succès.',
                    '%d versements ont été programmés avec succès.',
                    payouts_created
                ) % payouts_created,
                messages.SUCCESS
            )
        
        if skipped > 0:
            self.message_user(
                request,
                ngettext(
                    '%d réservation a été ignorée (non payée ou déjà avec versement).',
                    '%d réservations ont été ignorées (non payées ou déjà avec versement).',
                    skipped
                ) % skipped,
                messages.WARNING
            )
    
    def release_funds_immediately(self, request, queryset):
        """
        Action pour libérer immédiatement les fonds pour les réservations sélectionnées.
        """
        from payments.services.payout_service import PayoutService
        
        succeeded = 0
        failed = 0
        
        for booking in queryset:
            # Vérifier que la réservation est payée
            if booking.payment_status != 'paid':
                failed += 1
                continue
            
            try:
                # Récupérer le versement existant ou en créer un nouveau
                from payments.models import Payout
                payout = Payout.objects.filter(
                    bookings__id=booking.id,
                    status__in=['pending', 'scheduled']
                ).first()
                
                if payout:
                    # Marquer comme prêt à verser
                    payout.mark_as_ready()
                    payout.processed_by = request.user
                    payout.admin_notes += f"\nVersement immédiat déclenché par {request.user.email}"
                    payout.save(update_fields=['processed_by', 'admin_notes'])
                else:
                    # Créer un nouveau versement et le marquer comme prêt
                    payout = PayoutService.schedule_payout_for_booking(booking)
                    if payout:
                        payout.mark_as_ready()
                        payout.processed_by = request.user
                        payout.admin_notes += f"\nVersement immédiat créé par {request.user.email}"
                        payout.save(update_fields=['processed_by', 'admin_notes'])
                
                if payout:
                    succeeded += 1
                else:
                    failed += 1
            
            except Exception as e:
                failed += 1
                self.message_user(
                    request,
                    f"Erreur pour la réservation {booking.id}: {str(e)}",
                    messages.ERROR
                )
        
        if succeeded > 0:
            self.message_user(
                request,
                ngettext(
                    'Versement immédiat déclenché pour %d réservation.',
                    'Versement immédiat déclenché pour %d réservations.',
                    succeeded
                ) % succeeded,
                messages.SUCCESS
            )
        
        if failed > 0:
            self.message_user(
                request,
                ngettext(
                    'Échec pour %d réservation.',
                    'Échec pour %d réservations.',
                    failed
                ) % failed,
                messages.ERROR
            )
    
    def mark_as_completed(self, request, queryset):
        """
        Action pour marquer les réservations comme terminées et déclencher les versements.
        """
        completed = 0
        triggered = 0
        
        for booking in queryset.filter(status='confirmed'):
            booking.status = 'completed'
            booking.save(update_fields=['status'])
            completed += 1
            
            # Vérifier s'il y a un versement programmé à déclencher
            from payments.models import Payout
            payout = Payout.objects.filter(
                bookings__id=booking.id,
                status='scheduled'
            ).first()
            
            if payout:
                payout.mark_as_ready()
                payout.processed_by = request.user
                payout.admin_notes += f"\nDéclenché suite à la complétion de la réservation par {request.user.email}"
                payout.save(update_fields=['processed_by', 'admin_notes'])
                triggered += 1
        
        if completed > 0:
            self.message_user(
                request,
                ngettext(
                    '%d réservation a été marquée comme terminée.',
                    '%d réservations ont été marquées comme terminées.',
                    completed
                ) % completed,
                messages.SUCCESS
            )
        
        if triggered > 0:
            self.message_user(
                request,
                ngettext(
                    'Versement déclenché pour %d réservation.',
                    'Versements déclenchés pour %d réservations.',
                    triggered
                ) % triggered,
                messages.SUCCESS
            )
    
    property_title.short_description = _('Logement')
    tenant_name.short_description = _('Locataire')
    escrow_status.short_description = _('Statut des fonds')
    
    schedule_payout.short_description = _("Programmer le versement")
    release_funds_immediately.short_description = _("Libérer les fonds immédiatement")
    mark_as_completed.short_description = _("Marquer comme terminées et déclencher les versements")

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