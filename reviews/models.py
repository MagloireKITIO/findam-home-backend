# reviews/models.py
# Modèles pour la gestion des avis et signalements

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from properties.models import Property

User = get_user_model()

class Review(models.Model):
    """
    Modèle pour les avis détaillés sur les logements, indépendamment des réservations.
    Permet les avis plus détaillés que ceux liés directement aux réservations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='detailed_reviews')
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reviews')
    
    # Évaluation globale
    rating = models.PositiveSmallIntegerField(
        _('note globale'), 
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    
    # Évaluations détaillées par catégorie
    cleanliness_rating = models.PositiveSmallIntegerField(
        _('note propreté'), 
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    location_rating = models.PositiveSmallIntegerField(
        _('note emplacement'), 
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    value_rating = models.PositiveSmallIntegerField(
        _('note rapport qualité-prix'), 
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    communication_rating = models.PositiveSmallIntegerField(
        _('note communication'), 
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    
    # Contenu de l'avis
    title = models.CharField(_('titre'), max_length=100)
    comment = models.TextField(_('commentaire'))
    stay_date = models.DateField(_('date du séjour'))
    
    # Statut de l'avis
    is_public = models.BooleanField(_('public'), default=True)
    is_verified_stay = models.BooleanField(_('séjour vérifié'), default=False)
    
    # Métadonnées
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('avis détaillé')
        verbose_name_plural = _('avis détaillés')
        ordering = ['-created_at']
        db_table = 'findam_detailed_reviews'
        
    def __str__(self):
        return f"Avis de {self.reviewer.email} sur {self.property.title}"
    
    def save(self, *args, **kwargs):
        """Surcharge de la méthode save pour mettre à jour la note moyenne du logement."""
        super().save(*args, **kwargs)
        
        # Calculer la note moyenne (uniquement sur les avis publics)
        if self.is_public:
            property_reviews = Review.objects.filter(
                property=self.property,
                is_public=True
            )
            
            total_rating = sum(review.rating for review in property_reviews)
            count = property_reviews.count()
            
            if count > 0:
                self.property.avg_rating = total_rating / count
                self.property.rating_count = count
                self.property.save(update_fields=['avg_rating', 'rating_count'])

class ReviewImage(models.Model):
    """
    Modèle pour les images associées aux avis.
    """
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(_('image'), upload_to='reviews/')
    caption = models.CharField(_('légende'), max_length=100, blank=True)
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('image d\'avis')
        verbose_name_plural = _('images d\'avis')
        ordering = ['review', 'created_at']
        db_table = 'findam_review_images'
        
    def __str__(self):
        return f"Image pour avis {self.review.id}"

class ReviewReply(models.Model):
    """
    Modèle pour les réponses du propriétaire aux avis.
    """
    review = models.OneToOneField(Review, on_delete=models.CASCADE, related_name='owner_reply')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='review_replies')
    content = models.TextField(_('contenu de la réponse'))
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('réponse à un avis')
        verbose_name_plural = _('réponses aux avis')
        ordering = ['-created_at']
        db_table = 'findam_review_replies'
        
    def __str__(self):
        return f"Réponse à l'avis {self.review.id}"

class ReportedReview(models.Model):
    """
    Modèle pour les signalements d'avis inappropriés.
    """
    REPORT_REASON_CHOICES = (
        ('inappropriate', _('Contenu inapproprié')),
        ('fake', _('Avis frauduleux')),
        ('personal', _('Informations personnelles')),
        ('other', _('Autre raison')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reported_reviews')
    
    reason = models.CharField(_('raison'), max_length=20, choices=REPORT_REASON_CHOICES)
    details = models.TextField(_('détails'), blank=True)
    
    STATUS_CHOICES = (
        ('pending', _('En attente')),
        ('reviewed', _('Examiné')),
        ('actioned', _('Action prise')),
        ('dismissed', _('Rejeté')),
    )
    
    status = models.CharField(_('statut'), max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(_('notes administrateur'), blank=True)
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('signalement d\'avis')
        verbose_name_plural = _('signalements d\'avis')
        ordering = ['-created_at']
        db_table = 'findam_reported_reviews'
        
    def __str__(self):
        return f"Signalement de l'avis {self.review.id} pour {self.get_reason_display()}"