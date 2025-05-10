# payments/models.py
# Modèles pour la gestion des paiements et versements

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from properties.models import Property
from bookings.models import Booking, PaymentTransaction

User = get_user_model()

class PaymentMethod(models.Model):
    """
    Modèle pour les méthodes de paiement enregistrées par les utilisateurs.
    """
    PAYMENT_TYPE_CHOICES = (
        ('mobile_money', _('Mobile Money')),
        ('credit_card', _('Carte de crédit')),
        ('bank_account', _('Compte bancaire')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_methods')
    
    payment_type = models.CharField(_('type de paiement'), max_length=20, choices=PAYMENT_TYPE_CHOICES)
    is_default = models.BooleanField(_('méthode par défaut'), default=False)
    is_verified = models.BooleanField(_('vérifiée'), default=False)
    
    # Informations communes
    nickname = models.CharField(_('nom de la méthode'), max_length=100, blank=True)
    
    # Informations spécifiques au type de paiement
    account_number = models.CharField(_('numéro de compte/carte'), max_length=30, blank=True)
    account_name = models.CharField(_('titulaire du compte'), max_length=100, blank=True)
    
    # Pour Mobile Money
    phone_number = models.CharField(_('numéro de téléphone'), max_length=20, blank=True)
    operator = models.CharField(_('opérateur'), max_length=20, blank=True)
    
    # Pour les cartes bancaires (masquer le numéro complet)
    last_digits = models.CharField(_('derniers chiffres'), max_length=4, blank=True)
    expiry_date = models.DateField(_('date d\'expiration'), null=True, blank=True)
    
    # Pour les comptes bancaires
    bank_name = models.CharField(_('nom de la banque'), max_length=100, blank=True)
    branch_code = models.CharField(_('code d\'agence'), max_length=20, blank=True)
    
    # Métadonnées
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('méthode de paiement')
        verbose_name_plural = _('méthodes de paiement')
        ordering = ['-is_default', '-created_at']
        db_table = 'findam_payment_methods'
        
    def __str__(self):
        if self.nickname:
            return f"{self.nickname} ({self.get_payment_type_display()})"
        return f"{self.get_payment_type_display()} - {self.user.email}"
    
    def save(self, *args, **kwargs):
        """Surcharge de la méthode save pour gérer la méthode par défaut."""
        if self.is_default:
            # Mettre à jour toutes les autres méthodes de paiement de l'utilisateur
            PaymentMethod.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

class Transaction(models.Model):
    """
    Modèle principal pour toutes les transactions financières.
    """
    TRANSACTION_TYPE_CHOICES = (
        ('payment', _('Paiement de réservation')),
        ('refund', _('Remboursement')),
        ('payout', _('Versement au propriétaire')),
        ('subscription', _('Abonnement propriétaire')),
        ('commission', _('Commission plateforme')),
        ('adjustment', _('Ajustement manuel')),
    )
    
    STATUS_CHOICES = (
        ('pending', _('En attente')),
        ('processing', _('En cours de traitement')),
        ('completed', _('Terminée')),
        ('failed', _('Échouée')),
        ('refunded', _('Remboursée')),
        ('cancelled', _('Annulée')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Utilisateur concerné
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    
    # Type et statut
    transaction_type = models.CharField(_('type de transaction'), max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    status = models.CharField(_('statut'), max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Montants
    amount = models.DecimalField(_('montant'), max_digits=10, decimal_places=2)
    currency = models.CharField(_('devise'), max_length=3, default='XAF')  # Franc CFA
    
    # Références
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='financial_transactions')
    payment_transaction = models.ForeignKey(PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='financial_transactions')
    external_reference = models.CharField(_('référence externe'), max_length=100, blank=True)
    
    # Description et notes
    description = models.CharField(_('description'), max_length=255)
    admin_notes = models.TextField(_('notes administrateur'), blank=True)
    
    # Métadonnées
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    processed_at = models.DateTimeField(_('date de traitement'), null=True, blank=True)
    
    class Meta:
        verbose_name = _('transaction')
        verbose_name_plural = _('transactions')
        ordering = ['-created_at']
        db_table = 'findam_transactions'
        
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} {self.currency} - {self.user.email}"
    
    def mark_as_completed(self):
        """Marque la transaction comme terminée."""
        self.status = 'completed'
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'processed_at'])
        
        # Traiter les actions spécifiques selon le type de transaction
        if self.transaction_type == 'payment' and self.booking:
            self.booking.payment_status = 'paid'
            self.booking.save(update_fields=['payment_status'])
        
        elif self.transaction_type == 'refund' and self.booking:
            self.booking.payment_status = 'refunded'
            self.booking.save(update_fields=['payment_status'])

class Payout(models.Model):
    """
    Modèle pour les versements aux propriétaires.
    """
    STATUS_CHOICES = (
        ('pending', _('En attente')),
        ('scheduled', _('Programmé')),  # Nouveau statut pour les versements programmés
        ('ready', _('Prêt à verser')),  # Nouveau statut pour les versements prêts à être traités
        ('processing', _('En cours de traitement')),
        ('completed', _('Terminé')),
        ('failed', _('Échoué')),
        ('cancelled', _('Annulé')),  # Nouveau statut pour les versements annulés
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payouts')
    
    # Montants
    amount = models.DecimalField(_('montant'), max_digits=10, decimal_places=2)
    currency = models.CharField(_('devise'), max_length=3, default='XAF')  # Franc CFA
    
    # Méthode de paiement
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, related_name='payouts')
    
    # Statut
    status = models.CharField(_('statut'), max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Références
    transaction = models.OneToOneField(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='payout')
    external_reference = models.CharField(_('référence externe'), max_length=100, blank=True)
    
    # Pour les versements groupés (plusieurs réservations)
    bookings = models.ManyToManyField(Booking, related_name='payouts')
    
    # Informations supplémentaires
    period_start = models.DateField(_('début de la période'), null=True, blank=True)
    period_end = models.DateField(_('fin de la période'), null=True, blank=True)
    
    # Nouveaux champs pour l'anti-escrow
    scheduled_at = models.DateTimeField(_('date programmée'), null=True, blank=True)
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='processed_payouts'
    )
    escrow_reason = models.CharField(_('raison de séquestre'), max_length=100, blank=True)
    
    # Notes
    notes = models.TextField(_('notes'), blank=True)
    admin_notes = models.TextField(_('notes administrateur'), blank=True)
    
    # Métadonnées
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    processed_at = models.DateTimeField(_('date de traitement'), null=True, blank=True)
    
    class Meta:
        verbose_name = _('versement')
        verbose_name_plural = _('versements')
        ordering = ['-created_at']
        db_table = 'findam_payouts'
        
    def __str__(self):
        return f"Versement de {self.amount} {self.currency} à {self.owner.email}"
    
    def mark_as_completed(self):
        """Marque le versement comme terminé."""
        self.status = 'completed'
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'processed_at'])
        
        # Créer une transaction correspondante si elle n'existe pas déjà
        if not self.transaction:
            transaction = Transaction.objects.create(
                user=self.owner,
                transaction_type='payout',
                status='completed',
                amount=self.amount,
                currency=self.currency,
                description=f"Versement pour la période du {self.period_start} au {self.period_end}",
                processed_at=self.processed_at
            )
            self.transaction = transaction
            self.save(update_fields=['transaction'])
    
    def mark_as_ready(self):
        """Marque le versement comme prêt à verser."""
        self.status = 'ready'
        self.save(update_fields=['status'])
    
    def schedule(self, scheduled_date):
        """Programme le versement pour une date future."""
        self.status = 'scheduled'
        self.scheduled_at = scheduled_date
        self.save(update_fields=['status', 'scheduled_at'])
    
    def cancel(self, cancelled_by=None, reason=None):
        """Annule le versement."""
        self.status = 'cancelled'
        self.processed_by = cancelled_by
        if reason:
            self.escrow_reason = reason
        self.save(update_fields=['status', 'processed_by', 'escrow_reason'])
        
        # Si une transaction existe, la marquer comme annulée également
        if self.transaction:
            self.transaction.status = 'cancelled'
            self.transaction.save(update_fields=['status'])
    
    # Méthode statique pour créer un versement programmé pour une réservation
    @classmethod
    def schedule_for_booking(cls, booking, scheduled_date=None, **kwargs):
        """
        Crée un versement programmé pour une réservation.
        
        Args:
            booking (Booking): La réservation pour laquelle programmer un versement
            scheduled_date (datetime): Date et heure prévues pour le versement
            
        Returns:
            Payout: L'objet versement programmé
        """
        # Si aucune date n'est fournie, programmer 24h après le check-in
        if not scheduled_date:
            check_in_datetime = timezone.make_aware(
                timezone.datetime.combine(booking.check_in_date, timezone.datetime.min.time())
            )
            scheduled_date = check_in_datetime + timezone.timedelta(hours=24)
        
        # Calculer le montant (prix de la réservation - commission du propriétaire)
        from .models import Commission
        
        # Obtenir ou calculer la commission
        commission = Commission.objects.filter(booking=booking).first()
        if not commission:
            commission = Commission.calculate_for_booking(booking)
        
        # Montant à verser = prix total - commission propriétaire
        payout_amount = booking.total_price - commission.owner_amount
        
        # Créer le versement
        payout = cls.objects.create(
            owner=booking.property.owner,
            amount=payout_amount,
            currency='XAF',  # Devise par défaut
            status='scheduled',
            scheduled_at=scheduled_date,
            period_start=booking.check_in_date,
            period_end=booking.check_out_date,
            notes=f"Versement automatique pour la réservation {booking.id}",
            **kwargs
        )
        
        # Ajouter la réservation au versement
        payout.bookings.add(booking)
        
        return payout

class Commission(models.Model):
    """
    Modèle pour suivre les commissions de la plateforme.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='commission')
    
    # Montants
    owner_amount = models.DecimalField(_('montant propriétaire'), max_digits=10, decimal_places=2, default=0)
    tenant_amount = models.DecimalField(_('montant locataire'), max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(_('montant total'), max_digits=10, decimal_places=2, default=0)
    
    # Taux de commission
    owner_rate = models.DecimalField(_('taux propriétaire (%)'), max_digits=5, decimal_places=2, default=3.0)
    tenant_rate = models.DecimalField(_('taux locataire (%)'), max_digits=5, decimal_places=2, default=7.0)
    
    # Référence à la transaction
    transaction = models.OneToOneField(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='commission')
    
    # Métadonnées
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('commission')
        verbose_name_plural = _('commissions')
        db_table = 'findam_commissions'
        
    def __str__(self):
        return f"Commission sur réservation {self.booking.id} - Total: {self.total_amount}"
    
    def save(self, *args, **kwargs):
        """Surcharge de la méthode save pour calculer le montant total."""
        self.total_amount = self.owner_amount + self.tenant_amount
        super().save(*args, **kwargs)
    
    @classmethod
    def calculate_for_booking(cls, booking):
        """
        Calcule et crée la commission pour une réservation.
        Retourne l'objet Commission créé ou mis à jour.
        """
        # Importer Decimal si ce n'est pas déjà fait
        from decimal import Decimal
        
        # Calculer la commission du propriétaire (% du prix de base)
        base_price = booking.base_price
        owner_rate = Decimal('3.0')  # Taux par défaut pour le propriétaire
        
        # Vérifier si le propriétaire a un abonnement pour ajuster le taux
        owner = booking.property.owner
        active_subscription = owner.subscriptions.filter(
            status='active',
            end_date__gt=timezone.now()
        ).first()
        
        if active_subscription:
            if active_subscription.subscription_type == 'monthly':
                owner_rate = Decimal('2.0')
            elif active_subscription.subscription_type == 'quarterly':
                owner_rate = Decimal('1.5')
            elif active_subscription.subscription_type == 'yearly':
                owner_rate = Decimal('1.0')
        
        owner_amount = (base_price * owner_rate) / Decimal('100')
        
        # La commission du locataire est déjà incluse dans le service_fee
        tenant_amount = booking.service_fee
        tenant_rate = Decimal('7.0')
        
        # Créer ou mettre à jour la commission
        commission, created = cls.objects.update_or_create(
            booking=booking,
            defaults={
                'owner_amount': owner_amount,
                'tenant_amount': tenant_amount,
                'owner_rate': owner_rate,
                'tenant_rate': tenant_rate
            }
        )
        
        return commission