# communications/serializers.py
# Sérialiseurs pour les conversations, messages et notifications

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from .models import Conversation, Message, Notification, DeviceToken
from accounts.serializers import UserSerializer
from properties.models import Property
from properties.serializers import PropertyListSerializer

User = get_user_model()

class MessageSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les messages."""
    
    sender_details = UserSerializer(source='sender', read_only=True)
    is_read = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    has_filtered_content = serializers.SerializerMethodField()
    anti_disintermediation_warning = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'sender_details', 
            'content', 'message_type', 'attachment', 
            'is_read', 'created_at', 'updated_at',
            'has_filtered_content', 'anti_disintermediation_warning'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_content(self, obj):
        """Retourne le contenu approprié selon les autorisations."""
        return obj.get_unfiltered_content()
    
    def get_has_filtered_content(self, obj):
        """Indique si le message contient du contenu filtré."""
        return obj.is_filtered and obj.masked_items
    
    def get_anti_disintermediation_warning(self, obj):
        """Retourne l'avertissement si nécessaire."""
        from .services.message_filter_service import MessageFilterService
        
        if obj.is_filtered and obj.masked_items:
            if not MessageFilterService.should_reveal_contacts(obj.conversation):
                return MessageFilterService.get_anti_disintermediation_warning()
        return None
    
    def get_is_read(self, obj):
        """Vérifie si le message a été lu par l'utilisateur actuel."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.is_read_by(request.user)
        return False

class MessageCreateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la création de messages."""
    
    class Meta:
        model = Message
        fields = ['conversation', 'content', 'message_type', 'attachment']
    
    def validate_conversation(self, value):
        """Vérifie que l'utilisateur est bien un participant de la conversation."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if not value.participants.filter(id=request.user.id).exists():
                raise serializers.ValidationError(_("Vous n'êtes pas un participant de cette conversation."))
        return value
    
    def create(self, validated_data):
        """Crée un message avec filtrage automatique du contenu."""
        from .services.message_filter_service import MessageFilterService
        
        sender = self.context.get('request').user
        conversation = validated_data.get('conversation')
        original_content = validated_data.get('content')
        
        # Vérifier si on doit révéler les contacts
        booking_confirmed = MessageFilterService.should_reveal_contacts(conversation)
        
        # Appliquer le filtrage si nécessaire
        if not booking_confirmed:
            filtered_content, masked_items = MessageFilterService.filter_message_content(
                original_content, booking_confirmed
            )
        else:
            filtered_content = original_content
            masked_items = []
        
        # Créer le message avec le contenu filtré
        message = Message.objects.create(
            conversation=conversation,
            sender=sender,
            content=filtered_content,
            original_content=original_content,
            message_type=validated_data.get('message_type', 'text'),
            attachment=validated_data.get('attachment'),
            is_filtered=bool(masked_items),
            masked_items=masked_items
        )
        
        # Mettre à jour la date de dernière mise à jour de la conversation
        conversation.updated_at = message.created_at
        conversation.save(update_fields=['updated_at'])
        
        # Créer des notifications pour les autres participants
        Notification.create_for_new_message(message)
        
        return message

class ConversationSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les conversations."""
    
    participants = UserSerializer(many=True, read_only=True)
    property_details = PropertyListSerializer(source='property', read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'participants', 'property', 'property_details',
            'is_active', 'created_at', 'updated_at',
            'last_message', 'unread_count', 'other_participant'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_last_message(self, obj):
        """Récupère le dernier message de la conversation."""
        last_message = obj.messages.order_by('-created_at').first()
        if last_message:
            return {
                'id': last_message.id,
                'content': last_message.content,
                'sender_id': last_message.sender.id,
                'sender_name': last_message.sender.get_full_name() or last_message.sender.email,
                'created_at': last_message.created_at,
                'message_type': last_message.message_type
            }
        return None
    
    def get_unread_count(self, obj):
        """Compte le nombre de messages non lus pour l'utilisateur actuel."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.messages.exclude(sender=request.user).exclude(read_by=request.user).count()
        return 0
    
    def get_other_participant(self, obj):
        """Récupère l'autre participant de la conversation (pour les conversations à deux)."""
        request = self.context.get('request')
        if request and request.user.is_authenticated and obj.participants.count() == 2:
            other_user = obj.participants.exclude(id=request.user.id).first()
            if other_user:
                return {
                    'id': other_user.id,
                    'email': other_user.email,
                    'full_name': other_user.get_full_name(),
                    'user_type': other_user.user_type,
                    'is_verified': other_user.is_verified
                }
        return None

class ConversationCreateSerializer(serializers.Serializer):
    """Sérialiseur pour la création de conversations."""
    
    property_id = serializers.UUIDField(required=True)
    message = serializers.CharField(required=True)
    
    def validate_property_id(self, value):
        """Vérifie que le logement existe."""
        try:
            property_obj = Property.objects.get(id=value)
            return property_obj
        except Property.DoesNotExist:
            raise serializers.ValidationError(_("Le logement spécifié n'existe pas."))
    
    def create(self, validated_data):
        """Crée une conversation avec un premier message."""
        property_obj = validated_data.get('property_id')
        message_content = validated_data.get('message')
        sender = self.context.get('request').user
        
        # Vérifier que l'utilisateur n'est pas le propriétaire du logement
        if property_obj.owner == sender:
            raise serializers.ValidationError(_("Vous ne pouvez pas créer une conversation pour votre propre logement."))
        
        # Créer la conversation avec le propriétaire et le locataire
        conversation = Conversation.objects.create(property=property_obj)
        conversation.participants.add(sender, property_obj.owner)
        
        # Ajouter le premier message
        message = Message.objects.create(
            conversation=conversation,
            sender=sender,
            content=message_content
        )
        
        # Créer une notification pour le propriétaire
        Notification.create_for_new_message(message)
        
        return conversation

class NotificationSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les notifications."""
    
    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'notification_type', 'title', 'content',
            'related_conversation', 'related_object_id', 'related_object_type',
            'is_read', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class DeviceTokenSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les tokens d'appareils."""
    
    class Meta:
        model = DeviceToken
        fields = [
            'id', 'token', 'platform', 'device_name',
            'is_active', 'last_used', 'created_at'
        ]
        read_only_fields = ['id', 'last_used', 'created_at']
    
    def validate_token(self, value):
        """Vérifie que le token est unique ou appartient déjà à l'utilisateur."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            existing_token = DeviceToken.objects.filter(token=value).first()
            if existing_token and existing_token.user != request.user:
                raise serializers.ValidationError(_("Ce token est déjà utilisé par un autre utilisateur."))
        return value
    
    def create(self, validated_data):
        """Crée ou met à jour un token d'appareil."""
        request = self.context.get('request')
        user = request.user
        token = validated_data.get('token')
        
        # Vérifier si le token existe déjà pour cet utilisateur
        existing_token = DeviceToken.objects.filter(token=token).first()
        if existing_token:
            # Si le token appartient à cet utilisateur, le mettre à jour
            if existing_token.user == user:
                existing_token.platform = validated_data.get('platform', existing_token.platform)
                existing_token.device_name = validated_data.get('device_name', existing_token.device_name)
                existing_token.is_active = True
                existing_token.save()
                return existing_token
        
        # Sinon, créer un nouveau token
        return DeviceToken.objects.create(user=user, **validated_data)