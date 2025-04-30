# properties/models.py
# Modèles pour la gestion des logements et leurs caractéristiques

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()

class Amenity(models.Model):
    """
    Modèle pour les équipements disponibles dans les logements.
    Exemple: WiFi, climatisation, piscine, etc.
    """
    name = models.CharField(_('nom'), max_length=100)
    icon = models.CharField(_('icône'), max_length=50, blank=True)
    category = models.CharField(_('catégorie'), max_length=50, blank=True)
    
    class Meta:
        verbose_name = _('équipement')
        verbose_name_plural = _('équipements')
        ordering = ['name']
        db_table = 'findam_amenities'
        
    def __str__(self):
        return self.name

class City(models.Model):
    """
    Modèle pour les villes disponibles au Cameroun.
    """
    name = models.CharField(_('nom'), max_length=100)
    
    class Meta:
        verbose_name = _('ville')
        verbose_name_plural = _('villes')
        ordering = ['name']
        db_table = 'findam_cities'
        
    def __str__(self):
        return self.name

class Neighborhood(models.Model):
    """
    Modèle pour les quartiers des villes.
    """
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='neighborhoods')
    name = models.CharField(_('nom'), max_length=100)
    
    class Meta:
        verbose_name = _('quartier')
        verbose_name_plural = _('quartiers')
        ordering = ['city', 'name']
        db_table = 'findam_neighborhoods'
        
    def __str__(self):
        return f"{self.name}, {self.city.name}"

class Property(models.Model):
    """
    Modèle principal pour les logements.
    """
    PROPERTY_TYPE_CHOICES = (
        ('apartment', _('Appartement')),
        ('house', _('Maison')),
        ('villa', _('Villa')),
        ('studio', _('Studio')),
        ('room', _('Chambre')),
        ('other', _('Autre')),
    )
    
    CANCELLATION_POLICY_CHOICES = (
        ('flexible', _('Souple')),
        ('moderate', _('Modérée')),
        ('strict', _('Stricte')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties')
    title = models.CharField(_('titre'), max_length=200)
    description = models.TextField(_('description'))
    
    # Type et configuration
    property_type = models.CharField(_('type de logement'), max_length=20, choices=PROPERTY_TYPE_CHOICES)
    capacity = models.PositiveSmallIntegerField(_('capacité (personnes)'), default=1)
    bedrooms = models.PositiveSmallIntegerField(_('nombre de chambres'), default=1)
    bathrooms = models.PositiveSmallIntegerField(_('nombre de salles de bain'), default=1)
    
    # Localisation
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name='properties')
    neighborhood = models.ForeignKey(Neighborhood, on_delete=models.PROTECT, related_name='properties')
    address = models.CharField(_('adresse'), max_length=255)
    latitude = models.DecimalField(_('latitude'), max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(_('longitude'), max_digits=9, decimal_places=6, null=True, blank=True)
    
    # Tarifs
    price_per_night = models.DecimalField(_('prix par nuit'), max_digits=10, decimal_places=2)
    price_per_week = models.DecimalField(_('prix par semaine'), max_digits=10, decimal_places=2, null=True, blank=True)
    price_per_month = models.DecimalField(_('prix par mois'), max_digits=10, decimal_places=2, null=True, blank=True)
    cleaning_fee = models.DecimalField(_('frais de ménage'), max_digits=10, decimal_places=2, default=0)
    security_deposit = models.DecimalField(_('caution'), max_digits=10, decimal_places=2, default=0)
    
    # Options
    allow_discount = models.BooleanField(_('autoriser les demandes de rabais'), default=True)
    cancellation_policy = models.CharField(_('politique d\'annulation'), max_length=20, choices=CANCELLATION_POLICY_CHOICES, default='moderate')
    
    # Équipements
    amenities = models.ManyToManyField(Amenity, related_name='properties')
    
    # Statut
    is_published = models.BooleanField(_('publié'), default=False)
    is_verified = models.BooleanField(_('vérifié'), default=False)
    
    # Métadonnées
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    # Évaluations
    avg_rating = models.DecimalField(_('note moyenne'), max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(_('nombre d\'évaluations'), default=0)
    
    class Meta:
        verbose_name = _('logement')
        verbose_name_plural = _('logements')
        ordering = ['-created_at']
        db_table = 'findam_properties'
        
    def __str__(self):
        return self.title
    
    def update_rating(self, new_rating):
        """
        Met à jour la note moyenne du logement.
        """
        current_total = self.avg_rating * self.rating_count
        self.rating_count += 1
        self.avg_rating = (current_total + new_rating) / self.rating_count
        self.save(update_fields=['avg_rating', 'rating_count'])
    
    def calculate_price_for_days(self, days):
        """
        Calcule le prix pour un nombre de jours donné, en tenant compte des tarifs hebdomadaires et mensuels.
        """
        if days >= 30 and self.price_per_month:
            # Calcul basé sur le tarif mensuel
            months = days // 30
            remaining_days = days % 30
            total = (months * self.price_per_month) + (remaining_days * self.price_per_night)
        elif days >= 7 and self.price_per_week:
            # Calcul basé sur le tarif hebdomadaire
            weeks = days // 7
            remaining_days = days % 7
            total = (weeks * self.price_per_week) + (remaining_days * self.price_per_night)
        else:
            # Calcul basé sur le tarif journalier
            total = days * self.price_per_night
            
        return total

class PropertyImage(models.Model):
    """
    Modèle pour les images des logements.
    """
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(_('image'), upload_to='properties/')
    is_main = models.BooleanField(_('image principale'), default=False)
    order = models.PositiveSmallIntegerField(_('ordre'), default=0)
    caption = models.CharField(_('légende'), max_length=100, blank=True)
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('image de logement')
        verbose_name_plural = _('images de logement')
        ordering = ['property', 'order']
        db_table = 'findam_property_images'
        
    def __str__(self):
        return f"Image de {self.property.title} ({self.order})"
    
    def save(self, *args, **kwargs):
        """
        Surcharge de la méthode save pour s'assurer qu'il n'y a qu'une seule image principale par logement.
        """
        if self.is_main:
            # Mettre à jour toutes les autres images du même logement pour qu'elles ne soient pas principales
            PropertyImage.objects.filter(property=self.property, is_main=True).exclude(id=self.id).update(is_main=False)
        super().save(*args, **kwargs)

class Availability(models.Model):
    """
    Modèle pour les disponibilités des logements.
    Ce modèle utilise une approche d'enregistrement des périodes non disponibles.
    """
    BOOKING_TYPE_CHOICES = (
        ('booking', _('Réservation via l\'application')),
        ('external', _('Réservation externe')),
        ('blocked', _('Bloqué par le propriétaire')),
    )
    
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='unavailabilities')
    start_date = models.DateField(_('date de début'))
    end_date = models.DateField(_('date de fin'))
    booking_type = models.CharField(_('type de réservation'), max_length=20, choices=BOOKING_TYPE_CHOICES)
    booking_id = models.UUIDField(_('ID de réservation'), null=True, blank=True)
    
    # Infos pour les réservations externes (hors application)
    external_client_name = models.CharField(_('nom du client externe'), max_length=100, blank=True)
    external_client_phone = models.CharField(_('téléphone du client externe'), max_length=20, blank=True)
    notes = models.TextField(_('notes'), blank=True)
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('indisponibilité')
        verbose_name_plural = _('indisponibilités')
        ordering = ['property', 'start_date']
        db_table = 'findam_property_unavailabilities'
        
    def __str__(self):
        return f"{self.property.title} - {self.start_date} au {self.end_date}"
    
    def clean(self):
        """
        Validation personnalisée pour s'assurer que end_date est postérieure à start_date.
        """
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise models.ValidationError(_('La date de fin doit être postérieure à la date de début.'))

class LongStayDiscount(models.Model):
    """
    Modèle pour les réductions sur les séjours de longue durée.
    """
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='long_stay_discounts')
    min_days = models.PositiveSmallIntegerField(_('nombre minimum de jours'))
    discount_percentage = models.DecimalField(
        _('pourcentage de réduction'), 
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    class Meta:
        verbose_name = _('réduction long séjour')
        verbose_name_plural = _('réductions long séjour')
        ordering = ['property', 'min_days']
        db_table = 'findam_property_discounts'
        
    def __str__(self):
        return f"{self.property.title} - {self.discount_percentage}% pour {self.min_days}+ jours"