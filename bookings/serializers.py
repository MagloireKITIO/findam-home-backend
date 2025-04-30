# bookings/serializers.py
# Sérialiseurs pour les réservations et paiements

from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import Booking, PromoCode, BookingReview, PaymentTransaction
from properties.models import Property, Availability
from properties.serializers import PropertyListSerializer
from accounts.serializers import UserSerializer

class PromoCodeSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les codes promotionnels."""
    
    property_title = serializers.CharField(source='property.title', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = PromoCode
        fields = [
            'id', 'code', 'property', 'property_title', 'tenant', 
            'discount_percentage', 'is_active', 'expiry_date', 
            'created_at', 'created_by', 'is_valid'
        ]
        read_only_fields = ['id', 'code', 'created_at', 'created_by']
    
    def validate(self, data):
        """Validation personnalisée."""
        # Vérifier que la date d'expiration est future
        expiry_date = data.get('expiry_date')
        if expiry_date and expiry_date <= timezone.now():
            raise serializers.ValidationError(_("La date d'expiration doit être future."))
        
        # Vérifier que le propriétaire est bien le propriétaire du logement
        property_obj = data.get('property')
        created_by = self.context.get('request').user
        
        if property_obj and created_by:
            if property_obj.owner != created_by and not created_by.is_staff:
                raise serializers.ValidationError(
                    _("Vous ne pouvez créer des codes promo que pour vos propres logements.")
                )
        
        return data

class PromoCodeCreateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la création de codes promotionnels."""
    
    class Meta:
        model = PromoCode
        fields = ['property', 'tenant', 'discount_percentage', 'expiry_date']
    
    def validate(self, data):
        """Validation personnalisée."""
        # Vérifier que la date d'expiration est future
        expiry_date = data.get('expiry_date')
        if expiry_date and expiry_date <= timezone.now():
            raise serializers.ValidationError(_("La date d'expiration doit être future."))
        
        # Vérifier que le propriétaire est bien le propriétaire du logement
        property_obj = data.get('property')
        created_by = self.context.get('request').user
        
        if property_obj and created_by:
            if property_obj.owner != created_by and not created_by.is_staff:
                raise serializers.ValidationError(
                    _("Vous ne pouvez créer des codes promo que pour vos propres logements.")
                )
        
        # Vérifier que le propriétaire est différent du locataire
        tenant = data.get('tenant')
        if property_obj and tenant and property_obj.owner == tenant:
            raise serializers.ValidationError(
                _("Vous ne pouvez pas créer un code promo pour vous-même.")
            )
        
        return data
    
    def create(self, validated_data):
        """Création d'un code promotionnel avec génération automatique du code."""
        # Générer un code aléatoire
        import random
        import string
        
        code_length = 8
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=code_length))
        
        # Ajouter le créateur
        validated_data['created_by'] = self.context.get('request').user
        
        # Créer le code promo
        return PromoCode.objects.create(code=code, **validated_data)

class BookingReviewSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les avis sur les réservations."""
    
    reviewer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = BookingReview
        fields = [
            'id', 'booking', 'rating', 'comment', 
            'is_from_owner', 'created_at', 'reviewer_name'
        ]
        read_only_fields = ['id', 'created_at', 'is_from_owner']
    
    def get_reviewer_name(self, obj):
        """Récupère le nom de l'utilisateur qui a laissé l'avis."""
        if obj.is_from_owner:
            return obj.booking.property.owner.get_full_name()
        return obj.booking.tenant.get_full_name()
    
    def validate(self, data):
        """Validation personnalisée."""
        booking = data.get('booking')
        user = self.context.get('request').user
        
        # Vérifier que la réservation est terminée
        if booking.status != 'completed':
            raise serializers.ValidationError(_("Vous ne pouvez laisser un avis que pour une réservation terminée."))
        
        # Vérifier que l'utilisateur est soit le propriétaire, soit le locataire
        if user != booking.tenant and user != booking.property.owner:
            raise serializers.ValidationError(_("Vous ne pouvez laisser un avis que pour vos propres réservations."))
        
        # Déterminer si l'avis vient du propriétaire ou du locataire
        is_from_owner = (user == booking.property.owner)
        data['is_from_owner'] = is_from_owner
        
        # Vérifier qu'un avis n'a pas déjà été laissé par cet utilisateur
        existing_review = BookingReview.objects.filter(
            booking=booking,
            is_from_owner=is_from_owner
        ).exists()
        
        if existing_review:
            raise serializers.ValidationError(_("Vous avez déjà laissé un avis pour cette réservation."))
        
        return data

class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les transactions de paiement."""
    
    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'booking', 'amount', 'payment_method', 
            'status', 'transaction_id', 'payment_response', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class BookingCreateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la création de réservations."""
    
    promo_code_value = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = Booking
        fields = [
            'property', 'check_in_date', 'check_out_date', 
            'guests_count', 'special_requests', 'promo_code_value'
        ]
    
    def validate(self, data):
        """Validation personnalisée pour les réservations."""
        property_obj = data.get('property')
        check_in_date = data.get('check_in_date')
        check_out_date = data.get('check_out_date')
        guests_count = data.get('guests_count')
        
        # Vérifier que la date de départ est postérieure à la date d'arrivée
        if check_in_date and check_out_date and check_out_date <= check_in_date:
            raise serializers.ValidationError(_("La date de départ doit être postérieure à la date d'arrivée."))
        
        # Vérifier que la date d'arrivée est future
        if check_in_date and check_in_date < timezone.now().date():
            raise serializers.ValidationError(_("La date d'arrivée doit être future."))
        
        # Vérifier que le nombre de personnes ne dépasse pas la capacité du logement
        if property_obj and guests_count and guests_count > property_obj.capacity:
            raise serializers.ValidationError(
                _("Le nombre de personnes ({}) dépasse la capacité du logement ({}).").format(
                    guests_count, property_obj.capacity
                )
            )
        
        # Vérifier la disponibilité du logement pour ces dates
        if property_obj and check_in_date and check_out_date:
            unavailabilities = Availability.objects.filter(
                property=property_obj,
                start_date__lt=check_out_date,
                end_date__gt=check_in_date
            ).exists()
            
            if unavailabilities:
                raise serializers.ValidationError(_("Le logement n'est pas disponible pour ces dates."))
        
        # Traiter le code promo s'il est fourni
        promo_code_value = data.pop('promo_code_value', None)
        if promo_code_value:
            try:
                promo_code = PromoCode.objects.get(
                    code=promo_code_value,
                    property=property_obj,
                    is_active=True,
                    expiry_date__gt=timezone.now()
                )
                
                # Vérifier que le code promo est bien pour ce locataire
                if promo_code.tenant != self.context.get('request').user:
                    raise serializers.ValidationError(_("Ce code promo ne vous est pas destiné."))
                
                data['promo_code'] = promo_code
            except PromoCode.DoesNotExist:
                raise serializers.ValidationError(_("Code promo invalide ou expiré."))
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        """Création d'une réservation avec calcul des prix."""
        # Extraire le code promo s'il existe
        promo_code = validated_data.pop('promo_code', None)
        
        # Définir le locataire comme l'utilisateur actuel
        validated_data['tenant'] = self.context.get('request').user
        
        # Créer la réservation sans sauvegarder immédiatement
        booking = Booking(**validated_data)
        
        # Appliquer le code promo s'il existe
        if promo_code:
            booking.promo_code = promo_code
        
        # Calculer le prix total
        booking.calculate_total_price()
        
        # Sauvegarder la réservation
        booking.save()
        
        # Désactiver le code promo s'il a été utilisé
        if promo_code:
            promo_code.mark_as_used()
        
        return booking

class BookingListSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la liste des réservations (version allégée)."""
    
    property_title = serializers.CharField(source='property.title', read_only=True)
    property_image = serializers.SerializerMethodField()
    city = serializers.CharField(source='property.city.name', read_only=True)
    neighborhood = serializers.CharField(source='property.neighborhood.name', read_only=True)
    owner_name = serializers.CharField(source='property.owner.get_full_name', read_only=True)
    tenant_name = serializers.CharField(source='tenant.get_full_name', read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id', 'property_title', 'property_image', 'city', 'neighborhood',
            'check_in_date', 'check_out_date', 'guests_count',
            'total_price', 'status', 'payment_status',
            'owner_name', 'tenant_name', 'created_at'
        ]
    
    def get_property_image(self, obj):
        """Récupère l'image principale du logement si elle existe."""
        main_image = obj.property.images.filter(is_main=True).first()
        if main_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(main_image.image.url)
        return None

class BookingDetailSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les détails d'une réservation."""
    
    property = PropertyListSerializer(read_only=True)
    tenant = UserSerializer(read_only=True)
    review = BookingReviewSerializer(read_only=True)
    promo_code_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id', 'property', 'tenant', 
            'check_in_date', 'check_out_date', 'guests_count',
            'base_price', 'cleaning_fee', 'security_deposit',
            'discount_amount', 'service_fee', 'total_price',
            'promo_code_details', 'status', 'payment_status',
            'special_requests', 'notes', 'review',
            'created_at', 'updated_at', 'cancelled_at'
        ]
    
    def get_promo_code_details(self, obj):
        """Récupère les détails du code promo s'il existe."""
        if obj.promo_code:
            return {
                'code': obj.promo_code.code,
                'discount_percentage': obj.promo_code.discount_percentage,
                'amount': obj.discount_amount
            }
        return None