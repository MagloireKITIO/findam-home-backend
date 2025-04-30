# reviews/serializers.py
# Sérialiseurs pour les avis et signalements

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from .models import Review, ReviewImage, ReviewReply, ReportedReview
from accounts.serializers import UserSerializer
from bookings.models import Booking

class ReviewImageSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les images des avis."""
    
    class Meta:
        model = ReviewImage
        fields = ['id', 'image', 'caption', 'created_at']
        read_only_fields = ['created_at']

class ReviewReplySerializer(serializers.ModelSerializer):
    """Sérialiseur pour les réponses aux avis."""
    
    owner_details = UserSerializer(source='owner', read_only=True)
    
    class Meta:
        model = ReviewReply
        fields = ['id', 'owner', 'owner_details', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {'owner': {'write_only': True}}

class ReviewSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les avis."""
    
    reviewer_details = UserSerializer(source='reviewer', read_only=True)
    images = ReviewImageSerializer(many=True, read_only=True)
    owner_reply = ReviewReplySerializer(read_only=True)
    property_title = serializers.CharField(source='property.title', read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id', 'property', 'property_title', 'reviewer', 'reviewer_details',
            'rating', 'cleanliness_rating', 'location_rating', 'value_rating', 'communication_rating',
            'title', 'comment', 'stay_date', 'is_public', 'is_verified_stay',
            'images', 'owner_reply', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reviewer', 'is_verified_stay', 'created_at', 'updated_at']

class ReviewCreateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la création d'avis."""
    
    images = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        write_only=True
    )
    
    booking_id = serializers.UUIDField(write_only=True, required=False)
    
    class Meta:
        model = Review
        fields = [
            'property', 'rating', 'cleanliness_rating', 'location_rating', 
            'value_rating', 'communication_rating', 'title', 'comment', 
            'stay_date', 'images', 'booking_id'
        ]
    
    def validate(self, data):
        """Validation personnalisée."""
        property_obj = data.get('property')
        user = self.context['request'].user
        
        # Vérifier s'il existe déjà un avis de cet utilisateur pour ce logement
        if Review.objects.filter(property=property_obj, reviewer=user).exists():
            raise serializers.ValidationError(_("Vous avez déjà laissé un avis pour ce logement."))
        
        # Si booking_id fourni, vérifier que c'est bien une réservation de l'utilisateur pour ce logement
        booking_id = data.pop('booking_id', None)
        if booking_id:
            try:
                booking = Booking.objects.get(id=booking_id)
                if booking.tenant != user:
                    raise serializers.ValidationError(_("Cette réservation ne vous appartient pas."))
                if booking.property != property_obj:
                    raise serializers.ValidationError(_("Cette réservation ne correspond pas au logement spécifié."))
                if booking.status != 'completed':
                    raise serializers.ValidationError(_("La réservation doit être terminée pour laisser un avis."))
                
                # Marquer l'avis comme séjour vérifié
                data['is_verified_stay'] = True
            except Booking.DoesNotExist:
                raise serializers.ValidationError(_("Réservation introuvable."))
        
        return data
    
    def create(self, validated_data):
        """Création d'un avis avec ses images."""
        images_data = validated_data.pop('images', [])
        user = self.context['request'].user
        
        # Créer l'avis
        review = Review.objects.create(reviewer=user, **validated_data)
        
        # Ajouter les images
        for image_data in images_data:
            ReviewImage.objects.create(review=review, image=image_data)
        
        return review

class ReportedReviewSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les signalements d'avis."""
    
    review_details = ReviewSerializer(source='review', read_only=True)
    reporter_details = UserSerializer(source='reporter', read_only=True)
    
    class Meta:
        model = ReportedReview
        fields = [
            'id', 'review', 'review_details', 'reporter', 'reporter_details',
            'reason', 'details', 'status', 'admin_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reporter', 'status', 'admin_notes', 'created_at', 'updated_at']

class ReviewReplyCreateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la création de réponses aux avis."""
    
    class Meta:
        model = ReviewReply
        fields = ['review', 'content']
    
    def validate_review(self, value):
        """
        Vérifie que l'utilisateur est bien le propriétaire du logement concerné par l'avis.
        """
        user = self.context['request'].user
        
        if value.property.owner != user and not user.is_staff:
            raise serializers.ValidationError(
                _("Vous ne pouvez répondre qu'aux avis concernant vos propres logements.")
            )
        
        # Vérifier qu'il n'existe pas déjà une réponse
        if ReviewReply.objects.filter(review=value).exists():
            raise serializers.ValidationError(
                _("Une réponse a déjà été donnée à cet avis.")
            )
        
        return value
    
    def create(self, validated_data):
        """Création d'une réponse à un avis."""
        user = self.context['request'].user
        return ReviewReply.objects.create(owner=user, **validated_data)

class AdminReportReviewSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la gestion administrative des signalements."""
    
    class Meta:
        model = ReportedReview
        fields = ['status', 'admin_notes']
    
    def validate_status(self, value):
        """Valide que le statut est une valeur autorisée."""
        if value not in ['pending', 'reviewed', 'actioned', 'dismissed']:
            raise serializers.ValidationError(_("Statut non valide."))
        return value
    
    def update(self, instance, validated_data):
        """Mise à jour du signalement."""
        if 'status' in validated_data:
            instance.status = validated_data['status']
            
            # Si le signalement est validé (action prise), rendre l'avis non public
            if validated_data['status'] == 'actioned':
                instance.review.is_public = False
                instance.review.save(update_fields=['is_public'])
        
        if 'admin_notes' in validated_data:
            instance.admin_notes = validated_data['admin_notes']
        
        instance.save()
        return instance