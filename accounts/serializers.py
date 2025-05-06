# accounts/serializers.py
# Sérialiseurs pour les modèles utilisateur et profil

from django.utils import timezone

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import Profile, OwnerSubscription

User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    """Sérialiseur pour le modèle Profile."""
    
    class Meta:
        model = Profile
        exclude = ['user', 'id_card_image', 'selfie_image', 'verification_date', 'verification_notes']
        read_only_fields = ['verification_status', 'avg_rating', 'rating_count', 'created_at', 'updated_at']

class UserSerializer(serializers.ModelSerializer):
    """Sérialiseur pour le modèle User."""
    
    profile = ProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'phone_number', 'first_name', 'last_name', 
                  'user_type', 'is_verified', 'date_joined', 'profile']
        read_only_fields = ['id', 'is_verified', 'date_joined']

class UserRegistrationSerializer(serializers.ModelSerializer):
    """Sérialiseur pour l'inscription des utilisateurs."""
    
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = ['email', 'phone_number', 'first_name', 'last_name', 'user_type', 'password', 'password2']
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'user_type': {'required': True}
        }
    
    def validate(self, attrs):
        """Valide que les deux mots de passe correspondent."""
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Les mots de passe ne correspondent pas."})
        return attrs
    
    def create(self, validated_data):
        """Crée et retourne un nouvel utilisateur."""
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user

class PasswordChangeSerializer(serializers.Serializer):
    """Sérialiseur pour le changement de mot de passe."""
    
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True)
    
    def validate(self, attrs):
        """Valide que les deux nouveaux mots de passe correspondent."""
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Les nouveaux mots de passe ne correspondent pas."})
        return attrs

class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la mise à jour du profil utilisateur."""
    
    class Meta:
        model = Profile
        fields = ['avatar', 'bio', 'birth_date', 'city', 'country']

class VerificationSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la vérification d'identité."""
    
    id_card_image = serializers.ImageField(required=True)
    selfie_image = serializers.ImageField(required=True)
    id_card_number = serializers.CharField(required=True)
    
    class Meta:
        model = Profile
        fields = ['id_card_number', 'id_card_image', 'selfie_image']
        
    def update(self, instance, validated_data):
        """Mise à jour du profil avec les données de vérification."""
        if 'id_card_number' in validated_data:
            instance.id_card_number = validated_data['id_card_number']
        if 'id_card_image' in validated_data:
            instance.id_card_image = validated_data['id_card_image']
        if 'selfie_image' in validated_data:
            instance.selfie_image = validated_data['selfie_image']
        
        # Réinitialiser le statut de vérification
        instance.verification_status = 'pending'
        instance.save()
        return instance

class OwnerSubscriptionSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les abonnements des propriétaires."""
    
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    subscription_type_display = serializers.CharField(source='get_subscription_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = OwnerSubscription
        fields = ['id', 'owner', 'owner_email', 'subscription_type', 'subscription_type_display', 
                  'status', 'status_display', 'start_date', 'end_date', 'is_active', 
                  'payment_reference', 'created_at', 'updated_at']
        read_only_fields = ['id', 'owner', 'start_date', 'end_date', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        """Crée un nouvel abonnement pour un propriétaire."""
        user = self.context['request'].user
        
        # Vérifier que l'utilisateur est un propriétaire
        if not user.is_owner:
            raise serializers.ValidationError("Seuls les propriétaires peuvent souscrire à un abonnement.")
        
        # Créer l'abonnement
        subscription = OwnerSubscription.objects.create(
            owner=user,
            subscription_type=validated_data.get('subscription_type'),
            status='pending'  # À modifier après confirmation du paiement
        )
        
        return subscription

class SubscriptionCreateSerializer(serializers.Serializer):
    """Sérialiseur pour la création d'un nouvel abonnement."""
    
    subscription_type = serializers.ChoiceField(choices=OwnerSubscription.SUBSCRIPTION_TYPE_CHOICES)
    
    def validate_subscription_type(self, value):
        """Validation du type d'abonnement."""
        if value not in [choice[0] for choice in OwnerSubscription.SUBSCRIPTION_TYPE_CHOICES]:
            raise serializers.ValidationError("Type d'abonnement non valide.")
        return value
    
    def create(self, validated_data):
        user = self.context['request'].user
        
        # Vérifier que l'utilisateur est un propriétaire
        if not user.is_owner:
            raise serializers.ValidationError("Seuls les propriétaires peuvent souscrire à un abonnement.")
        
        # Vérifier s'il existe déjà un abonnement actif
        active_subscription = OwnerSubscription.objects.filter(
            owner=user, 
            status='active', 
            end_date__gt=timezone.now()
        ).first()
        
        if active_subscription:
            raise serializers.ValidationError("Vous avez déjà un abonnement actif.")
        
        # Créer l'abonnement
        subscription = OwnerSubscription.objects.create(
            owner=user,
            subscription_type=validated_data.get('subscription_type'),
            status='pending'  # À modifier après confirmation du paiement
        )
        
        return subscription

class AdminVerificationSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la vérification administrateur."""
    
    class Meta:
        model = Profile
        fields = ['verification_status', 'verification_notes']
        
    def validate_verification_status(self, value):
        """Validation du statut de vérification."""
        if value not in ['pending', 'verified', 'rejected']:
            raise serializers.ValidationError("Statut de vérification non valide.")
        return value
    
    def update(self, instance, validated_data):
        """Met à jour le statut de vérification et enregistre la date."""
        if 'verification_status' in validated_data:
            instance.verification_status = validated_data['verification_status']
            # Si le statut est "verified", mettre à jour également l'utilisateur
            if validated_data['verification_status'] == 'verified':
                instance.verification_date = timezone.now()
                instance.user.is_verified = True
                instance.user.save()
        
        if 'verification_notes' in validated_data:
            instance.verification_notes = validated_data['verification_notes']
        
        instance.save()
        return instance

class UserDetailSerializer(serializers.ModelSerializer):
    """Sérialiseur détaillé pour les utilisateurs."""
    
    profile = ProfileSerializer()
    active_subscription = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'phone_number', 'first_name', 'last_name', 
                  'user_type', 'is_verified', 'date_joined', 'profile', 'active_subscription']
        read_only_fields = ['id', 'email', 'is_verified', 'date_joined']
    
    def get_active_subscription(self, obj):
        """Renvoie l'abonnement actif de l'utilisateur s'il est propriétaire."""
        if not obj.is_owner:
            return None
        
        active_sub = OwnerSubscription.objects.filter(
            owner=obj,
            status='active',
            end_date__gt=timezone.now()
        ).first()
        
        if not active_sub:
            return None
        
        return {
            'id': active_sub.id,
            'type': active_sub.subscription_type,
            'display': active_sub.get_subscription_type_display(),
            'end_date': active_sub.end_date
        }