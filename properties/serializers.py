# properties/serializers.py
# Sérialiseurs pour les logements et leurs caractéristiques

from rest_framework import serializers
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import (
    Amenity,
    City,
    Neighborhood,
    Property,
    PropertyImage,
    Availability,
    LongStayDiscount
)

class AmenitySerializer(serializers.ModelSerializer):
    """Sérialiseur pour les équipements."""
    
    class Meta:
        model = Amenity
        fields = ['id', 'name', 'icon', 'category']

class CitySerializer(serializers.ModelSerializer):
    """Sérialiseur pour les villes."""
    
    class Meta:
        model = City
        fields = ['id', 'name']

class NeighborhoodSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les quartiers."""
    
    city_name = serializers.CharField(source='city.name', read_only=True)
    
    class Meta:
        model = Neighborhood
        fields = ['id', 'name', 'city', 'city_name']

class PropertyImageSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les images des logements."""
    
    class Meta:
        model = PropertyImage
        fields = ['id', 'property', 'image', 'is_main', 'order', 'caption', 'created_at']
        read_only_fields = ['created_at']
        
    def create(self, validated_data):
        """
        Surcharge de create pour gérer l'image principale.
        Si c'est la première image ou qu'elle est définie comme principale, 
        on s'assure qu'elle est bien marquée comme telle.
        """
        property_instance = validated_data.get('property')
        is_main = validated_data.get('is_main', False)
        
        # Si c'est la première image, la définir comme principale
        if not PropertyImage.objects.filter(property=property_instance).exists():
            validated_data['is_main'] = True
        
        # Si cette image est définie comme principale, mettre à jour les autres
        elif is_main:
            PropertyImage.objects.filter(property=property_instance, is_main=True).update(is_main=False)
        
        return super().create(validated_data)

class LongStayDiscountSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les réductions sur les longs séjours."""
    
    class Meta:
        model = LongStayDiscount
        fields = ['id', 'min_days', 'discount_percentage']
        
    def validate_min_days(self, value):
        """Valide que le nombre minimum de jours est positif."""
        if value <= 0:
            raise serializers.ValidationError(_("Le nombre minimum de jours doit être positif."))
        return value
        
    def validate_discount_percentage(self, value):
        """Valide que le pourcentage de réduction est entre 0 et 100."""
        if value < 0 or value > 100:
            raise serializers.ValidationError(_("Le pourcentage de réduction doit être entre 0 et 100."))
        return value

class AvailabilitySerializer(serializers.ModelSerializer):
    """Sérialiseur pour les indisponibilités des logements."""
    
    class Meta:
        model = Availability
        fields = [
            'id', 'property', 'start_date', 'end_date', 'booking_type',
            'booking_id', 'external_client_name', 'external_client_phone',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
        
    def validate(self, data):
        """Validation personnalisée pour les dates et les champs supplémentaires."""
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        booking_type = data.get('booking_type')
        
        # Vérifier que la date de fin est postérieure à la date de début
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(_("La date de fin doit être postérieure à la date de début."))
        
        # Pour les réservations externes, vérifier la présence des infos client
        if booking_type == 'external':
            if not data.get('external_client_name'):
                raise serializers.ValidationError(_("Le nom du client est requis pour les réservations externes."))
            if not data.get('external_client_phone'):
                raise serializers.ValidationError(_("Le téléphone du client est requis pour les réservations externes."))
        
        return data

class PropertyListSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la liste des logements (version allégée)."""
    
    city_name = serializers.CharField(source='city.name', read_only=True)
    neighborhood_name = serializers.CharField(source='neighborhood.name', read_only=True)
    owner_name = serializers.CharField(source='owner.get_full_name', read_only=True)
    main_image = serializers.SerializerMethodField()
    amenities_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'property_type', 'city_name', 'neighborhood_name',
            'price_per_night', 'capacity', 'bedrooms', 'bathrooms',
            'main_image', 'owner_name', 'amenities_count', 'avg_rating', 'rating_count'
        ]
    
    def get_main_image(self, obj):
        """Récupère l'image principale du logement si elle existe."""
        main_image = obj.images.filter(is_main=True).first()
        if main_image:
            return self.context['request'].build_absolute_uri(main_image.image.url)
        return None
    
    def get_amenities_count(self, obj):
        """Compte le nombre d'équipements du logement."""
        return obj.amenities.count()

class PropertyDetailSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les détails d'un logement."""
    
    city_name = serializers.CharField(source='city.name', read_only=True)
    neighborhood_name = serializers.CharField(source='neighborhood.name', read_only=True)
    owner_name = serializers.CharField(source='owner.get_full_name', read_only=True)
    owner_verified = serializers.BooleanField(source='owner.is_verified', read_only=True)
    owner_since = serializers.DateTimeField(source='owner.date_joined', read_only=True)
    owner_rating = serializers.DecimalField(source='owner.profile.avg_rating', max_digits=3, decimal_places=2, read_only=True)
    images = PropertyImageSerializer(many=True, read_only=True)
    amenities = AmenitySerializer(many=True, read_only=True)
    long_stay_discounts = LongStayDiscountSerializer(many=True, read_only=True)
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'description', 'property_type', 
            'capacity', 'bedrooms', 'bathrooms',
            'city', 'city_name', 'neighborhood', 'neighborhood_name', 'address',
            'latitude', 'longitude',
            'price_per_night', 'price_per_week', 'price_per_month',
            'cleaning_fee', 'security_deposit',
            'allow_discount', 'cancellation_policy',
            'amenities', 'images', 'long_stay_discounts',
            'owner_name', 'owner_verified', 'owner_since', 'owner_rating',
            'is_published', 'is_verified',
            'avg_rating', 'rating_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'avg_rating', 'rating_count']

class PropertyCreateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la création d'un logement."""
    
    amenities = serializers.PrimaryKeyRelatedField(
        queryset=Amenity.objects.all(),
        many=True,
        required=False
    )
    
    images = PropertyImageSerializer(many=True, required=False)
    
    long_stay_discounts = LongStayDiscountSerializer(many=True, required=False)
    
    class Meta:
        model = Property
        exclude = ['owner', 'is_verified', 'avg_rating', 'rating_count']
    
    def validate(self, data):
        """Validation des données."""
        # Vérifier que le quartier appartient bien à la ville sélectionnée
        city = data.get('city')
        neighborhood = data.get('neighborhood')
        
        if city and neighborhood and neighborhood.city.id != city.id:
            raise serializers.ValidationError(
                {"neighborhood": _("Ce quartier n'appartient pas à la ville sélectionnée.")}
            )
        
        # Vérifier que le prix par semaine est inférieur à 7 fois le prix par nuit
        price_per_night = data.get('price_per_night')
        price_per_week = data.get('price_per_week')
        
        if price_per_night and price_per_week and price_per_week >= price_per_night * 7:
            raise serializers.ValidationError(
                {"price_per_week": _("Le prix par semaine doit être inférieur à 7 fois le prix par nuit.")}
            )
        
        # Vérifier que le prix par mois est inférieur à 30 fois le prix par nuit
        price_per_month = data.get('price_per_month')
        
        if price_per_night and price_per_month and price_per_month >= price_per_night * 30:
            raise serializers.ValidationError(
                {"price_per_month": _("Le prix par mois doit être inférieur à 30 fois le prix par nuit.")}
            )
        
        return data
    
    @transaction.atomic
    def create(self, validated_data):
        """Crée un logement avec ses relations."""
        amenities_data = validated_data.pop('amenities', [])
        images_data = validated_data.pop('images', [])
        discounts_data = validated_data.pop('long_stay_discounts', [])
        
        # Créer le logement
        validated_data['owner'] = self.context['request'].user
        property_instance = Property.objects.create(**validated_data)
        
        # Ajouter les équipements
        if amenities_data:
            property_instance.amenities.set(amenities_data)
        
        # Ajouter les images
        for image_data in images_data:
            PropertyImage.objects.create(property=property_instance, **image_data)
        
        # Ajouter les réductions pour les longs séjours
        for discount_data in discounts_data:
            LongStayDiscount.objects.create(property=property_instance, **discount_data)
        
        return property_instance
    
    @transaction.atomic
    def update(self, instance, validated_data):
        """Met à jour un logement avec ses relations."""
        amenities_data = validated_data.pop('amenities', None)
        images_data = validated_data.pop('images', None)
        discounts_data = validated_data.pop('long_stay_discounts', None)
        
        # Mettre à jour le logement
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Mettre à jour les équipements si fournis
        if amenities_data is not None:
            instance.amenities.set(amenities_data)
        
        # Mettre à jour les réductions pour les longs séjours si fournies
        if discounts_data is not None:
            # Supprimer les anciennes réductions
            instance.long_stay_discounts.all().delete()
            
            # Créer les nouvelles réductions
            for discount_data in discounts_data:
                LongStayDiscount.objects.create(property=instance, **discount_data)
        
        # Note: Les images sont gérées séparément pour plus de contrôle
        
        return instance

class PropertyAvailabilityCheckSerializer(serializers.Serializer):
    """Sérialiseur pour vérifier la disponibilité d'un logement."""
    
    start_date = serializers.DateField(required=True)
    end_date = serializers.DateField(required=True)
    
    def validate(self, data):
        """Validation des dates."""
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if end_date <= start_date:
            raise serializers.ValidationError(_("La date de fin doit être postérieure à la date de début."))
        
        return data

class ExternalBookingSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les réservations externes (hors application)."""
    
    class Meta:
        model = Availability
        fields = [
            'start_date', 'end_date', 'external_client_name', 
            'external_client_phone', 'notes'
        ]
        
    def create(self, validated_data):
        """Crée une nouvelle période d'indisponibilité pour une réservation externe."""
        property_id = self.context.get('property_id')
        if not property_id:
            raise serializers.ValidationError(_("ID de logement manquant."))
        
        validated_data['property_id'] = property_id
        validated_data['booking_type'] = 'external'
        
        return Availability.objects.create(**validated_data)