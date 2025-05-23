# bookings/models.py
# Modèles pour la gestion des réservations

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from properties.models import Property, Availability

User = get_user_model()

class PromoCode(models.Model):
    """
    Modèle pour les codes promotionnels qui peuvent être appliqués aux réservations.
    """
    code = models.CharField(_('code'), max_length=20, unique=True)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='promo_codes')
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promo_codes', null=True, blank=True)
    discount_percentage = models.DecimalField(
        _('pourcentage de réduction'), 
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    is_active = models.BooleanField(_('actif'), default=True)
    expiry_date = models.DateTimeField(_('date d\'expiration'))
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_promo_codes')
    
    class Meta:
        verbose_name = _('code promo')
        verbose_name_plural = _('codes promo')
        ordering = ['-created_at']
        db_table = 'findam_promo_codes'
        
    def __str__(self):
        return f"{self.code} - {self.discount_percentage}% pour {self.property.title}"
    
    def is_valid(self):
        """Vérifie si le code promo est valide."""
        return self.is_active and timezone.now() < self.expiry_date
    
    def mark_as_used(self):
        """Marque le code promo comme utilisé (désactivé)."""
        self.is_active = False
        self.save(update_fields=['is_active'])
    
    def is_valid_for_user(self, user):
        """Vérifie si le code promo est valide pour un utilisateur donné."""
        # Le code n'est pas valide pour le propriétaire du logement
        if user == self.property.owner:
            return False
        
        # Si pas de tenant spécifié, valide pour tous (sauf propriétaire)
        if not self.tenant:
            return True
        
        # Si tenant spécifié, valide seulement pour ce tenant
        return self.tenant == user

class Booking(models.Model):
    """
    Modèle principal pour les réservations.
    """
    STATUS_CHOICES = (
        ('pending', _('En attente')),
        ('confirmed', _('Confirmée')),
        ('cancelled', _('Annulée')),
        ('completed', _('Terminée')),
    )
    
    PAYMENT_STATUS_CHOICES = (
        ('pending', _('En attente')),
        ('authorized', _('Autorisé')),
        ('paid', _('Payé')),
        ('refunded', _('Remboursé')),
        ('failed', _('Échoué')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name='bookings')
    tenant = models.ForeignKey(User, on_delete=models.PROTECT, related_name='bookings', null=True, blank=True)
    
    # Dates et nombre de personnes
    check_in_date = models.DateField(_('date d\'arrivée'))
    check_out_date = models.DateField(_('date de départ'))
    guests_count = models.PositiveSmallIntegerField(_('nombre de personnes'), default=1)
    
    # Prix et paiement
    base_price = models.DecimalField(_('prix de base'), max_digits=10, decimal_places=2)
    cleaning_fee = models.DecimalField(_('frais de ménage'), max_digits=10, decimal_places=2, default=0)
    security_deposit = models.DecimalField(_('caution'), max_digits=10, decimal_places=2, default=0)
    promo_code = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    discount_amount = models.DecimalField(_('montant de la réduction'), max_digits=10, decimal_places=2, default=0)
    service_fee = models.DecimalField(_('frais de service'), max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(_('prix total'), max_digits=10, decimal_places=2)
    
    # Statuts
    status = models.CharField(_('statut'), max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(_('statut de paiement'), max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    
    # Communication et notes
    special_requests = models.TextField(_('demandes spéciales'), blank=True)
    notes = models.TextField(_('notes'), blank=True)
    
    # Métadonnées
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    cancelled_at = models.DateTimeField(_('date d\'annulation'), null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cancelled_bookings')

    # réservations externes
    is_external = models.BooleanField(_('réservation externe'), default=False)
    external_client_name = models.CharField(_('nom du client externe'), max_length=200, blank=True)
    external_client_phone = models.CharField(_('téléphone du client externe'), max_length=20, blank=True)
    external_notes = models.TextField(_('notes sur la réservation externe'), blank=True)
    
    class Meta:
        verbose_name = _('réservation')
        verbose_name_plural = _('réservations')
        ordering = ['-created_at']
        db_table = 'findam_bookings'
    
    def __init__(self, *args, **kwargs):
        """Initialisation avec capture de l'état initial pour détecter les changements."""
        super().__init__(*args, **kwargs)
        # Capture de l'état initial des champs clés après initialisation
        if self.pk:  # Seulement pour les objets existants
            self._previous_status = self.status
        else:
            self._previous_status = None
        
    def __str__(self):
        if self.is_external:
            return f"Réservation externe - {self.external_client_name} - {self.property.title} du {self.check_in_date} au {self.check_out_date}"
        return f"Réservation de {self.property.title} par {self.tenant.email if self.tenant else 'Unknown'} du {self.check_in_date} au {self.check_out_date}"
    
    def save(self, *args, **kwargs):
        """Surcharge de la méthode save pour des comportements personnalisés."""
        # Capture de l'état précédent pour les signaux
        is_new = self._state.adding
        old_status = None
        
        if not is_new:
            try:
                old_obj = Booking.objects.get(pk=self.pk)
                old_status = old_obj.status
                # Stocker le statut précédent pour la détection dans les signaux
                self._previous_status = old_status
            except Booking.DoesNotExist:
                pass
        
        # CORRECTION: Pour les réservations externes, ne pas calculer les prix
        if self.is_external:
            # Forcer les valeurs à zéro pour les réservations externes
            self.base_price = 0
            self.cleaning_fee = 0
            self.security_deposit = 0
            self.service_fee = 0
            self.discount_amount = 0
            self.total_price = 0
        elif not self.total_price:
            # Calculer le prix total seulement si ce n'est pas déjà fait ET si ce n'est pas externe
            self.calculate_total_price()
        
        # Sauvegarder d'abord
        super().save(*args, **kwargs)
        
        # Gérer les disponibilités si le statut a changé
        status_changed = old_status != self.status if old_status else is_new
        
        if status_changed:
            self.handle_availability_changes(is_new, old_status)
            
    
    def calculate_total_price(self):
        """Calcule le prix total de la réservation."""
        # AJOUT: Ne rien faire pour les réservations externes
        if self.is_external:
            return 0
        
        # Prix de base
        days = (self.check_out_date - self.check_in_date).days
        self.base_price = self.property.calculate_price_for_days(days)
        
        # Ajouter les frais de ménage
        self.cleaning_fee = self.property.cleaning_fee or 0
        
        # Ajouter la caution
        self.security_deposit = self.property.security_deposit or 0
        
        # Calculer la réduction si un code promo est appliqué
        self.discount_amount = 0
        if self.promo_code and self.promo_code.is_valid():
            discount_rate = self.promo_code.discount_percentage / 100
            self.discount_amount = self.base_price * discount_rate
        
        # Assurons-nous que les valeurs sont des objets Decimal pour éviter les erreurs de type
        from decimal import Decimal
        
        # Convertir en Decimal si ce n'est pas déjà le cas
        base_price = Decimal(str(self.base_price)) if not isinstance(self.base_price, Decimal) else self.base_price
        discount_amount = Decimal(str(self.discount_amount)) if not isinstance(self.discount_amount, Decimal) else self.discount_amount
        cleaning_fee = Decimal(str(self.cleaning_fee)) if not isinstance(self.cleaning_fee, Decimal) else self.cleaning_fee
        security_deposit = Decimal(str(self.security_deposit)) if not isinstance(self.security_deposit, Decimal) else self.security_deposit
        
        # Calculer les frais de service (7% pour le locataire)
        self.service_fee = (base_price - discount_amount) * Decimal('0.07')
        
        # Calculer le total
        self.total_price = (
            base_price + 
            cleaning_fee + 
            security_deposit + 
            self.service_fee - 
            discount_amount
        )
        
        return self.total_price
    
    def handle_availability_changes(self, is_new, old_status):
        """Gère les modifications de disponibilité en fonction des changements de statut."""
        # Si la réservation est confirmée, créer une indisponibilité
        if self.status == 'confirmed':
            # Vérifier s'il existe déjà une disponibilité pour cette réservation
            availability = Availability.objects.filter(
                property=self.property,
                booking_id=self.id
            ).first()
            
            if not availability:
                # Créer une nouvelle indisponibilité
                Availability.objects.create(
                    property=self.property,
                    start_date=self.check_in_date,
                    end_date=self.check_out_date,
                    booking_type='booking',
                    booking_id=self.id
                )
        
        # Si la réservation est annulée, supprimer l'indisponibilité
        elif old_status == 'confirmed' and self.status == 'cancelled':
            Availability.objects.filter(
                property=self.property,
                booking_id=self.id
            ).delete()
    
    def cancel(self, cancelled_by=None):
        """
        Marque la réservation comme annulée sans traiter les remboursements.
        Cette méthode est maintenant un wrapper simple pour maintenir la compatibilité.
        Pour une annulation complète avec remboursement, utilisez CancellationService.cancel_booking()
        """
        self.status = 'cancelled'
        self.cancelled_at = timezone.now()
        self.cancelled_by = cancelled_by
        self.save()
        
        # Si un code promo a été utilisé, le réactiver
        if self.promo_code and not self.promo_code.is_active:
            self.promo_code.is_active = True
            self.promo_code.save(update_fields=['is_active'])
        
        return self

class BookingReview(models.Model):
    """
    Modèle pour les avis sur les réservations.
    """
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveSmallIntegerField(
        _('note'), 
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(_('commentaire'))
    
    # Pour différencier les avis laissés par le propriétaire ou le locataire
    is_from_owner = models.BooleanField(_('de la part du propriétaire'), default=False)
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('avis de réservation')
        verbose_name_plural = _('avis de réservations')
        ordering = ['-created_at']
        db_table = 'findam_booking_reviews'
        
    def __str__(self):
        reviewer = "propriétaire" if self.is_from_owner else "locataire"
        return f"Avis de {reviewer} sur réservation {self.booking.id}"
    
    def save(self, *args, **kwargs):
        """Surcharge de la méthode save pour mettre à jour les notes moyennes."""
        super().save(*args, **kwargs)
        
        # Mettre à jour la note moyenne du logement
        if not self.is_from_owner:
            self.booking.property.update_rating(self.rating)
        
        # Mettre à jour la note moyenne du locataire ou du propriétaire
        if self.is_from_owner:
            # Le propriétaire évalue le locataire, vérifier que le tenant existe
            if self.booking.tenant:  # Ajouter cette vérification
                self.booking.tenant.profile.update_rating(self.rating)
        else:
            # Le locataire évalue le propriétaire
            self.booking.property.owner.profile.update_rating(self.rating)

class PaymentTransaction(models.Model):
    """
    Modèle pour les transactions de paiement.
    """
    PAYMENT_METHOD_CHOICES = (
        ('mobile_money', _('Mobile Money')),
        ('credit_card', _('Carte de crédit')),
        ('bank_transfer', _('Virement bancaire')),
    )
    
    STATUS_CHOICES = (
        ('pending', _('En attente')),
        ('processing', _('En cours de traitement')),
        ('completed', _('Terminée')),
        ('failed', _('Échouée')),
        ('refunded', _('Remboursée')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name='transactions')
    
    amount = models.DecimalField(_('montant'), max_digits=10, decimal_places=2)
    payment_method = models.CharField(_('méthode de paiement'), max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(_('statut'), max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Pour stocker les réponses de l'API de paiement
    transaction_id = models.CharField(_('ID de transaction'), max_length=100, blank=True)
    payment_response = models.JSONField(_('réponse de paiement'), null=True, blank=True)
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('transaction de paiement')
        verbose_name_plural = _('transactions de paiement')
        ordering = ['-created_at']
        db_table = 'findam_payment_transactions'
        
    def __str__(self):
        return f"Paiement de {self.amount} pour réservation {self.booking.id} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        """Surcharge de la méthode save pour mettre à jour le statut de paiement de la réservation."""
        super().save(*args, **kwargs)
        
        # Mettre à jour le statut de paiement de la réservation
        if self.status == 'completed':
            self.booking.payment_status = 'paid'
        elif self.status == 'refunded':
            self.booking.payment_status = 'refunded'
        elif self.status == 'failed':
            self.booking.payment_status = 'failed'
        elif self.status == 'processing':
            self.booking.payment_status = 'authorized'
        else:
            self.booking.payment_status = 'pending'
        
        self.booking.save(update_fields=['payment_status'])