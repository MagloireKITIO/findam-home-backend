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
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promo_codes')
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
    tenant = models.ForeignKey(User, on_delete=models.PROTECT, related_name='bookings')
    
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
    
    class Meta:
        verbose_name = _('réservation')
        verbose_name_plural = _('réservations')
        ordering = ['-created_at']
        db_table = 'findam_bookings'
        
    def __str__(self):
        return f"Réservation de {self.property.title} par {self.tenant.email} du {self.check_in_date} au {self.check_out_date}"
    
    def save(self, *args, **kwargs):
        """Surcharge de la méthode save pour des comportements personnalisés."""
        # Calculer le prix total si ce n'est pas déjà fait
        if not self.total_price:
            self.calculate_total_price()
        
        # Si c'est une nouvelle réservation, mettre à jour les disponibilités du logement
        is_new = self._state.adding
        old_status = None
        
        if not is_new:
            try:
                old_obj = Booking.objects.get(pk=self.pk)
                old_status = old_obj.status
            except Booking.DoesNotExist:
                pass
        
        # Sauvegarder d'abord
        super().save(*args, **kwargs)
        
        # Gérer les disponibilités si le statut a changé
        status_changed = old_status != self.status if old_status else is_new
        
        if status_changed:
            self.handle_availability_changes(is_new, old_status)
    
    def calculate_total_price(self):
        """Calcule le prix total de la réservation."""
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
        
        # Calculer les frais de service (7% pour le locataire)
        self.service_fee = (self.base_price - self.discount_amount) * 0.07
        
        # Calculer le total
        self.total_price = (
            self.base_price + 
            self.cleaning_fee + 
            self.security_deposit + 
            self.service_fee - 
            self.discount_amount
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
        """Annule la réservation."""
        self.status = 'cancelled'
        self.cancelled_at = timezone.now()
        self.cancelled_by = cancelled_by
        self.save()
        
        # Si un code promo a été utilisé, le réactiver
        if self.promo_code and not self.promo_code.is_active:
            self.promo_code.is_active = True
            self.promo_code.save(update_fields=['is_active'])
        
        # Ajouter ici la logique de remboursement selon la politique d'annulation
        # (à implémenter dans un service séparé)

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
            # Le propriétaire évalue le locataire
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