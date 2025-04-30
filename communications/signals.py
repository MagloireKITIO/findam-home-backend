# communications/signals.py
# Signaux pour les communications en temps réel

from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification, Message
from .serializers import NotificationSerializer

@receiver(post_save, sender=Notification)
def notification_created(sender, instance, created, **kwargs):
    """
    Signal envoyé lorsqu'une notification est créée.
    Envoie la notification au groupe WebSocket de l'utilisateur.
    """
    if created:
        channel_layer = get_channel_layer()
        
        # Sérialiser la notification
        serializer = NotificationSerializer(instance)
        
        # Envoyer la notification au groupe de l'utilisateur
        notification_group_name = f'user_{instance.recipient.id}_notifications'
        
        async_to_sync(channel_layer.group_send)(
            notification_group_name,
            {
                'type': 'new_notification',
                'notification': serializer.data
            }
        )

@receiver(post_save, sender=Message)
def message_created(sender, instance, created, **kwargs):
    """
    Signal envoyé lorsqu'un message est créé par une autre méthode que WebSocket.
    Envoie le message au groupe WebSocket de la conversation.
    """
    if created:
        # Vérifier si le message a été créé par l'API REST et non par WebSocket
        # On peut ajouter un attribut temporaire via le contexte de la requête
        if not getattr(instance, '_from_websocket', False):
            channel_layer = get_channel_layer()
            
            # Envoyer le message au groupe de la conversation
            room_group_name = f'chat_{instance.conversation.id}'
            
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'chat_message',
                    'message': {
                        'id': str(instance.id),
                        'sender_id': str(instance.sender.id),
                        'sender_name': instance.sender.get_full_name() or instance.sender.email,
                        'content': instance.content,
                        'created_at': instance.created_at.isoformat(),
                        'message_type': instance.message_type
                    }
                }
            )