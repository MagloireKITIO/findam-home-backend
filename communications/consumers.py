# communications/consumers.py
# Consumers WebSocket pour les communications en temps réel

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Conversation, Message, Notification

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    """
    Consumer pour les conversations en temps réel.
    """
    
    async def connect(self):
        """
        Appelé lorsqu'un client WebSocket tente de se connecter.
        """
        self.user = self.scope["user"]
        
        # Vérifier que l'utilisateur est authentifié
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Récupérer l'ID de la conversation depuis les paramètres de l'URL
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        
        # Vérifier que l'utilisateur a accès à cette conversation
        if not await self.can_access_conversation(self.conversation_id, self.user.id):
            await self.close()
            return
        
        # Définir le nom du groupe de discussion
        self.room_group_name = f'chat_{self.conversation_id}'
        
        # Rejoindre le groupe de discussion
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Accepter la connexion WebSocket
        await self.accept()
    
    async def disconnect(self, close_code):
        """
        Appelé lorsque le client WebSocket se déconnecte.
        """
        # Quitter le groupe de discussion
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """
        Appelé lorsque le client WebSocket envoie un message.
        """
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type', 'message')
        
        # Traiter différents types de messages
        if message_type == 'message':
            content = text_data_json.get('content')
            
            # Sauvegarder le message dans la base de données
            message = await self.save_message(content)
            
            # Envoyer le message au groupe de discussion
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': {
                        'id': str(message.id),
                        'sender_id': str(self.user.id),
                        'sender_name': self.user.get_full_name() or self.user.email,
                        'content': content,
                        'created_at': message.created_at.isoformat(),
                        'message_type': 'text'
                    }
                }
            )
        
        elif message_type == 'typing':
            # Informer les autres utilisateurs que quelqu'un est en train d'écrire
            is_typing = text_data_json.get('is_typing', False)
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_typing',
                    'user_id': str(self.user.id),
                    'user_name': self.user.get_full_name() or self.user.email,
                    'is_typing': is_typing
                }
            )
        
        elif message_type == 'read':
            # Marquer les messages comme lus
            await self.mark_messages_as_read()
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'messages_read',
                    'user_id': str(self.user.id)
                }
            )
    
    async def chat_message(self, event):
        """
        Appelé lorsqu'un message est reçu du groupe de discussion.
        """
        message = event['message']
        
        # Envoyer le message au client WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': message
        }))
    
    async def user_typing(self, event):
        """
        Appelé lorsqu'un utilisateur est en train d'écrire.
        """
        # Envoyer l'information au client WebSocket
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user_id': event['user_id'],
            'user_name': event['user_name'],
            'is_typing': event['is_typing']
        }))
    
    async def messages_read(self, event):
        """
        Appelé lorsque des messages sont marqués comme lus.
        """
        # Envoyer l'information au client WebSocket
        await self.send(text_data=json.dumps({
            'type': 'read',
            'user_id': event['user_id']
        }))
    
    @database_sync_to_async
    def can_access_conversation(self, conversation_id, user_id):
        """
        Vérifie si l'utilisateur a accès à la conversation.
        """
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            return conversation.participants.filter(id=user_id).exists()
        except Conversation.DoesNotExist:
            return False
    
    @database_sync_to_async
    def save_message(self, content):
        """
        Sauvegarde un message dans la base de données.
        """
        conversation = Conversation.objects.get(id=self.conversation_id)
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=content,
            message_type='text'
        )
        
        # Mettre à jour la date de dernière mise à jour de la conversation
        conversation.updated_at = message.created_at
        conversation.save(update_fields=['updated_at'])
        
        # Créer des notifications pour les autres participants
        Notification.create_for_new_message(message)
        
        return message
    
    @database_sync_to_async
    def mark_messages_as_read(self):
        """
        Marque tous les messages non lus de la conversation comme lus pour l'utilisateur.
        """
        conversation = Conversation.objects.get(id=self.conversation_id)
        conversation.mark_as_read(self.user)

class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Consumer pour les notifications en temps réel.
    """
    
    async def connect(self):
        """
        Appelé lorsqu'un client WebSocket tente de se connecter.
        """
        self.user = self.scope["user"]
        
        # Vérifier que l'utilisateur est authentifié
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Définir le nom du groupe de notification
        self.notification_group_name = f'user_{self.user.id}_notifications'
        
        # Rejoindre le groupe de notification
        await self.channel_layer.group_add(
            self.notification_group_name,
            self.channel_name
        )
        
        # Accepter la connexion WebSocket
        await self.accept()
    
    async def disconnect(self, close_code):
        """
        Appelé lorsque le client WebSocket se déconnecte.
        """
        # Quitter le groupe de notification
        await self.channel_layer.group_discard(
            self.notification_group_name,
            self.channel_name
        )
    
    async def new_notification(self, event):
        """
        Appelé lorsqu'une nouvelle notification est disponible.
        """
        notification = event['notification']
        
        # Envoyer la notification au client WebSocket
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification': notification
        }))
    
    async def notification_read(self, event):
        """
        Appelé lorsqu'une notification est marquée comme lue.
        """
        notification_id = event['notification_id']
        
        # Envoyer l'information au client WebSocket
        await self.send(text_data=json.dumps({
            'type': 'notification_read',
            'notification_id': notification_id
        }))