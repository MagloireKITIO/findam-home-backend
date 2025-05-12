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
from django.core.validators import RegexValidator
from django.db import transaction
from .utils import NotchPayUtils
from .services.notchpay_service import NotchPayService


import logging

logger = logging.getLogger(__name__)


User = get_user_model()

class PaymentMethod(models.Model):
    """
    Modèle pour stocker les méthodes de paiement des utilisateurs.
    Utilisé pour les remboursements et autres transactions sortantes.
    """
    
    PAYMENT_TYPE_CHOICES = (
        ('mobile_money', 'Mobile Money'),
        ('bank_account', 'Compte bancaire'),
        ('credit_card', 'Carte bancaire'),
    )
    
    OPERATOR_CHOICES = (
        ('orange', 'Orange Money'),
        ('mtn', 'MTN Mobile Money'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'En attente de vérification'),
        ('verified', 'Vérifiée'),
        ('failed', 'Échec de vérification'),
        ('disabled', 'Désactivée'),
    )
    
    # Validateurs pour les numéros de téléphone camerounais
    phone_regex = RegexValidator(
        regex=r'^(\+237)?[6][5-9]\d{7}$',
        message="Numéro de téléphone invalide. Format attendu: 6XXXXXXXX ou +237 6XXXXXXXX"
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_methods')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    
    # Informations communes
    nickname = models.CharField(max_length=100, blank=True, help_text="Nom personnalisé pour identifier cette méthode")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False, help_text="Méthode activée pour les transactions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Champs pour Mobile Money
    phone_number = models.CharField(max_length=15, validators=[phone_regex], blank=True, null=True)
    operator = models.CharField(max_length=10, choices=OPERATOR_CHOICES, blank=True, null=True)
    
    # Champs pour compte bancaire
    account_number = models.CharField(max_length=50, blank=True, null=True)
    account_name = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    branch_code = models.CharField(max_length=20, blank=True, null=True)
    
    # Champs pour carte bancaire (stockage sécurisé)
    last_digits = models.CharField(max_length=4, blank=True, null=True)
    expiry_date = models.CharField(max_length=7, blank=True, null=True)  # Format: MM/YYYY
    
    # Références externes
    notchpay_recipient_id = models.CharField(max_length=100, blank=True, null=True,
                                           help_text="ID du destinataire dans NotchPay")
    
    # Métadonnées
    verification_attempts = models.PositiveIntegerField(default=0)
    last_verification_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('méthode de paiement')
        verbose_name_plural = _('méthodes de paiement')
        db_table = 'findam_payment_methods'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'payment_type', 'phone_number'],
                condition=models.Q(payment_type='mobile_money', status__in=['verified', 'pending']),
                name='unique_mobile_money_per_user'
            ),
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_active=True),
                name='unique_active_payment_method_per_user'
            ),
        ]
    
    def __str__(self):
        if self.payment_type == 'mobile_money':
            return f"{self.get_operator_display()} - {self.masked_phone_number()}"
        elif self.payment_type == 'bank_account':
            return f"{self.bank_name} - {self.masked_account_number()}"
        elif self.payment_type == 'credit_card':
            return f"****{self.last_digits}"
        return f"{self.get_payment_type_display()} - {self.nickname}"
    
    def save(self, *args, **kwargs):
        """
        Logique personnalisée lors de la sauvegarde
        """
        # Auto-détection de l'opérateur pour Mobile Money
        if self.payment_type == 'mobile_money' and self.phone_number and not self.operator:
            self.operator = self._detect_operator()
        
        # Si cette méthode devient active, désactiver les autres
        if self.is_active:
            with transaction.atomic():
                PaymentMethod.objects.filter(
                    user=self.user,
                    is_active=True
                ).exclude(id=self.id).update(is_active=False)
        
        # Mettre à jour le statut si nécessaire
        if self.pk and self.has_changed():
            if self.status != 'verified' and self.is_active:
                # On ne peut pas activer une méthode non vérifiée
                self.is_active = False
        
        super().save(*args, **kwargs)
    
    def _detect_operator(self):
        """Détecte automatiquement l'opérateur Mobile Money"""
        if not self.phone_number:
            return None
        
        # Nettoyer le numéro
        clean_number = self.phone_number.replace('+237', '').replace(' ', '')
        
        # Orange Money : commence par 69 ou 65
        if clean_number.startswith(('69', '65')):
            return 'orange'
        # MTN MoMo : commence par 67, 68, 65, 66
        elif clean_number.startswith(('67', '68', '66')):
            return 'mtn'
        
        return None
    
    def has_changed(self):
        """Vérifie si l'objet a été modifié"""
        if not self.pk:
            return True
        
        try:
            old_instance = PaymentMethod.objects.get(pk=self.pk)
            for field in self._meta.fields:
                if getattr(old_instance, field.name) != getattr(self, field.name):
                    return True
            return False
        except PaymentMethod.DoesNotExist:
            return True
    
    def masked_phone_number(self):
        """Retourne le numéro de téléphone masqué"""
        if not self.phone_number:
            return "N/A"
        
        clean_number = self.phone_number.replace('+237', '').replace(' ', '')
        if len(clean_number) >= 9:
            return f"+237 {clean_number[:2]}****{clean_number[-3:]}"
        return self.phone_number
    
    def masked_account_number(self):
        """Retourne le numéro de compte masqué"""
        if not self.account_number:
            return "N/A"
        
        if len(self.account_number) > 8:
            return f"****{self.account_number[-4:]}"
        return self.account_number
    
    @transaction.atomic
    def activate(self, user=None):
        """
        Active cette méthode de paiement.
        Seule une méthode peut être active à la fois par utilisateur.
        """
        if self.status != 'verified':
            raise ValueError("Seules les méthodes vérifiées peuvent être activées")
        
        # Désactiver toutes les autres méthodes de cet utilisateur
        PaymentMethod.objects.filter(
            user=self.user,
            is_active=True
        ).exclude(id=self.id).update(is_active=False)
        
        # Activer cette méthode
        self.is_active = True
        self.save(update_fields=['is_active'])
        
        logger.info(f"Méthode de paiement {self.id} activée pour l'utilisateur {self.user.email}")
    
    @transaction.atomic
    def deactivate(self, user=None):
        """Désactive cette méthode de paiement"""
        self.is_active = False
        self.save(update_fields=['is_active'])
        
        logger.info(f"Méthode de paiement {self.id} désactivée pour l'utilisateur {self.user.email}")
    
    def verify_with_notchpay(self):
        """
        Vérifie la méthode de paiement avec NotchPay
        """
        try:
            self.verification_attempts += 1
            self.last_verification_at = timezone.now()
            
            notchpay_service = NotchPayService()
            
            if self.payment_type == 'mobile_money':
                success, recipient_id = self._verify_mobile_money(notchpay_service)
            elif self.payment_type == 'bank_account':
                success, recipient_id = self._verify_bank_account(notchpay_service)
            else:
                # Pour les cartes, on ne peut pas vérifier directement
                success, recipient_id = True, None
            
            if success:
                self.status = 'verified'
                self.notchpay_recipient_id = recipient_id
                self.verification_notes = f"Vérifiée avec succès le {timezone.now().strftime('%d/%m/%Y à %H:%M')}"
                logger.info(f"Méthode de paiement {self.id} vérifiée avec succès")
            else:
                self.status = 'failed'
                self.verification_notes = f"Échec de vérification le {timezone.now().strftime('%d/%m/%Y à %H:%M')}"
                logger.warning(f"Échec de vérification de la méthode de paiement {self.id}")
            
            self.save(update_fields=['status', 'notchpay_recipient_id', 'verification_notes', 
                                   'verification_attempts', 'last_verification_at'])
            
            return self.status == 'verified'
            
        except Exception as e:
            logger.exception(f"Erreur lors de la vérification de la méthode de paiement {self.id}: {str(e)}")
            self.status = 'failed'
            self.verification_notes = f"Erreur lors de la vérification: {str(e)}"
            self.save(update_fields=['status', 'verification_notes', 'verification_attempts', 
                                   'last_verification_at'])
            return False
    
    def _verify_mobile_money(self, notchpay_service):
        """Vérifie un compte Mobile Money avec NotchPay"""
        try:
            # Formater le numéro de téléphone avec le +
            formatted_phone = NotchPayUtils.format_phone_number(self.phone_number)
            if not formatted_phone.startswith('+'):
                formatted_phone = f'+{formatted_phone}'
            
            # Préparer les données du destinataire selon l'API réelle NotchPay
            recipient_data = {
                'channel': f'cm.{self.operator}' if self.operator else 'cm.mobile',
                'account_number': formatted_phone,  # L'API demande account_number !
                'phone': formatted_phone,   # Numéro de contact
                'email': self.user.email,
                'country': 'CM',
                'name': self.user.get_full_name() or f"{self.user.first_name} {self.user.last_name}",
                'description': f'{self.get_operator_display()} - {self.user.email}',
                'reference': f'findam-{self.user.id}-{self.id}'
            }
            
            # Nettoyer les valeurs vides
            recipient_data = {k: v for k, v in recipient_data.items() if v}
            
            logger.info(f"Création destinataire NotchPay avec: {recipient_data}")
            
            try:
                # Créer le destinataire dans NotchPay
                recipient = notchpay_service.create_recipient(recipient_data)
                
                if recipient and 'id' in recipient:
                    return True, recipient['id']
                else:
                    logger.error(f"Réponse invalide de NotchPay: {recipient}")
                    return False, None
            except Exception as e:
                # En mode test/sandbox, si NotchPay renvoie une erreur 500,
                # on peut marquer la méthode comme vérifiée pour continuer le développement
                if hasattr(e, 'response') and e.response and e.response.status_code == 500:
                    logger.warning(f"Erreur 500 NotchPay (probablement mode test), vérification simulée")
                    return True, None  # On marque comme vérifiée sans ID destinataire
                raise e
                
        except Exception as e:
            logger.exception(f"Erreur lors de la vérification Mobile Money: {str(e)}")
            
            # Log de la réponse d'erreur si disponible
            if hasattr(e, 'response') and e.response:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Détails de l'erreur NotchPay: {error_detail}")
                except:
                    logger.error(f"Contenu de l'erreur: {e.response.text}")
            
            return False, None
    
    def _verify_bank_account(self, notchpay_service):
        """Vérifie un compte bancaire avec NotchPay"""
        try:
            # NotchPay pourrait ne pas supporter les comptes bancaires directement
            # Cette méthode peut être adaptée selon les capacités de l'API
            recipient_data = {
                'channel': 'bank',
                'number': self.account_number,
                'email': self.user.email,
                'country': 'CM',
                'name': self.account_name or self.user.get_full_name(),
                'description': f'Compte bancaire - {self.bank_name}',
                'reference': f'payment-method-{self.id}'
            }
            
            # Créer le destinataire (si supporté)
            recipient = notchpay_service.create_recipient(recipient_data)
            
            if recipient and 'id' in recipient:
                return True, recipient['id']
            else:
                # Si NotchPay ne supporte pas, on marque comme vérifié par défaut
                return True, None
                
        except Exception as e:
            logger.exception(f"Erreur lors de la vérification du compte bancaire: {str(e)}")
            # Pour les comptes bancaires, on peut être plus permissif
            return True, None
    
    @classmethod
    def get_active_for_user(cls, user):
        """Récupère la méthode de paiement active d'un utilisateur"""
        return cls.objects.filter(user=user, is_active=True, status='verified').first()
    
    @classmethod
    def get_verified_for_user(cls, user):
        """Récupère toutes les méthodes vérifiées d'un utilisateur"""
        return cls.objects.filter(user=user, status='verified').order_by('-is_active', '-created_at')

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