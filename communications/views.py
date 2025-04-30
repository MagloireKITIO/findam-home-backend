# communications/views.py
# Vues pour la gestion des communications (conversations, messages, notifications)

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from .models import Conversation, Message, Notification, DeviceToken
from .serializers import (
    ConversationSerializer,
    ConversationCreateSerializer,
    MessageSerializer,
    MessageCreateSerializer,
    NotificationSerializer,
    DeviceTokenSerializer
)
from accounts.permissions import IsOwnerOfProfile


class ConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les conversations.
    """
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['participants__email', 'participants__first_name', 'participants__last_name', 'property__title']
    ordering_fields = ['updated_at', 'created_at']
    ordering = ['-updated_at']
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : toutes les conversations
        - Pour les autres : uniquement leurs conversations
        """
        user = self.request.user
        
        if user.is_staff:
            return Conversation.objects.all().prefetch_related(
                'participants', 'messages'
            ).select_related('property')
        
        # Pour les utilisateurs normaux, uniquement leurs conversations
        return Conversation.objects.filter(
            participants=user
        ).prefetch_related(
            'participants', 'messages'
        ).select_related('property')
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'utilisateur actuel comme participant à la conversation.
        """
        conversation = serializer.save()
        conversation.participants.add(self.request.user)
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """
        Marque tous les messages non lus d'une conversation comme lus.
        POST /api/v1/communications/conversations/{id}/mark_as_read/
        """
        conversation = self.get_object()
        conversation.mark_as_read(request.user)
        return Response({"detail": "Messages marqués comme lus."})
    
    @action(detail=False, methods=['post'])
    def start_conversation(self, request):
        """
        Crée une nouvelle conversation avec un propriétaire au sujet d'un logement.
        POST /api/v1/communications/conversations/start_conversation/
        """
        serializer = ConversationCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            conversation = serializer.save()
            return Response(
                ConversationSerializer(conversation, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def with_property(self, request):
        """
        Récupère la conversation existante pour un logement donné.
        GET /api/v1/communications/conversations/with_property/?property_id={id}
        """
        property_id = request.query_params.get('property_id')
        
        if not property_id:
            return Response({
                "detail": "ID de logement requis."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Chercher une conversation existante pour ce logement avec l'utilisateur actuel
        conversation = Conversation.objects.filter(
            property_id=property_id,
            participants=request.user
        ).first()
        
        if not conversation:
            return Response({
                "detail": "Aucune conversation trouvée pour ce logement."
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response(
            ConversationSerializer(conversation, context={'request': request}).data
        )


class MessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les messages.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        """
        Retourne la classe de sérialiseur appropriée selon l'action.
        """
        if self.action == 'create':
            return MessageCreateSerializer
        return MessageSerializer
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : tous les messages
        - Pour les autres : uniquement les messages de leurs conversations
        """
        user = self.request.user
        
        if user.is_staff:
            return Message.objects.all().select_related(
                'conversation', 'sender'
            )
        
        # Pour les utilisateurs normaux, uniquement les messages de leurs conversations
        return Message.objects.filter(
            conversation__participants=user
        ).select_related(
            'conversation', 'sender'
        )
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'expéditeur au message.
        """
        serializer.save(sender=self.request.user)
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """
        Marque un message comme lu.
        POST /api/v1/communications/messages/{id}/mark_as_read/
        """
        message = self.get_object()
        message.mark_as_read(request.user)
        return Response({"detail": "Message marqué comme lu."})
    
    @action(detail=False, methods=['get'])
    def by_conversation(self, request):
        """
        Récupère les messages d'une conversation.
        GET /api/v1/communications/messages/by_conversation/?conversation_id={id}
        """
        conversation_id = request.query_params.get('conversation_id')
        
        if not conversation_id:
            return Response({
                "detail": "ID de conversation requis."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier que l'utilisateur est bien un participant de la conversation
        is_participant = Conversation.objects.filter(
            id=conversation_id,
            participants=request.user
        ).exists()
        
        if not is_participant and not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à accéder à cette conversation."
            }, status=status.HTTP_403_FORBIDDEN)
        
        messages = Message.objects.filter(
            conversation_id=conversation_id
        ).select_related('sender').order_by('created_at')
        
        # Marquer les messages comme lus
        for message in messages:
            if message.sender != request.user:
                message.mark_as_read(request.user)
        
        page = self.paginate_queryset(messages)
        if page is not None:
            serializer = MessageSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les notifications.
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : toutes les notifications
        - Pour les autres : uniquement leurs notifications
        """
        user = self.request.user
        
        if user.is_staff:
            return Notification.objects.all()
        
        # Pour les utilisateurs normaux, uniquement leurs notifications
        return Notification.objects.filter(recipient=user)
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """
        Marque une notification comme lue.
        POST /api/v1/communications/notifications/{id}/mark_as_read/
        """
        notification = self.get_object()
        notification.mark_as_read()
        return Response({"detail": "Notification marquée comme lue."})
    
    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """
        Marque toutes les notifications de l'utilisateur comme lues.
        POST /api/v1/communications/notifications/mark_all_as_read/
        """
        Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)
        
        return Response({"detail": "Toutes les notifications ont été marquées comme lues."})
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """
        Récupère le nombre de notifications non lues.
        GET /api/v1/communications/notifications/unread_count/
        """
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()
        
        return Response({"unread_count": count})


class DeviceTokenViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les tokens d'appareils pour les notifications push.
    """
    serializer_class = DeviceTokenSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : tous les tokens
        - Pour les autres : uniquement leurs tokens
        """
        user = self.request.user
        
        if user.is_staff:
            return DeviceToken.objects.all()
        
        # Pour les utilisateurs normaux, uniquement leurs tokens
        return DeviceToken.objects.filter(user=user)
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'utilisateur au token.
        """
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Désactive un token d'appareil.
        POST /api/v1/communications/device-tokens/{id}/deactivate/
        """
        token = self.get_object()
        token.is_active = False
        token.save(update_fields=['is_active'])
        
        return Response({"detail": "Token désactivé avec succès."})