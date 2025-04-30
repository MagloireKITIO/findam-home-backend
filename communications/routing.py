# communications/routing.py
# Configuration des routes WebSocket pour l'application communications

from django.urls import path
from .consumers import ChatConsumer, NotificationConsumer

websocket_urlpatterns = [
    # Route pour les conversations
    path('ws/chat/<uuid:conversation_id>/', ChatConsumer.as_asgi()),
    
    # Route pour les notifications
    path('ws/notifications/', NotificationConsumer.as_asgi()),
]