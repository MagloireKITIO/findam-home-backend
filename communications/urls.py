# communications/urls.py
# Configuration des URLs pour l'application communications

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ConversationViewSet,
    MessageViewSet,
    NotificationViewSet,
    DeviceTokenViewSet
)

# Création du routeur pour les viewsets
router = DefaultRouter()
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'device-tokens', DeviceTokenViewSet, basename='device-token')

# Configuration des URLs
urlpatterns = [
    path('', include(router.urls)),
]