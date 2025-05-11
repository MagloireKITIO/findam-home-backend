# accounts/urls.py
# Configuration des URLs pour l'application accounts

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserRegistrationView,
    UserProfileView,
    PasswordChangeView,
    IdentityVerificationView,
    AdminVerificationView,
    SubscriptionViewSet,
    PendingVerificationsView,
)

# Création du routeur pour les abonnements
router = DefaultRouter()
# router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')

urlpatterns = [
    # Urls d'authentification
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('change-password/', PasswordChangeView.as_view(), name='change-password'),
    
    # Urls de vérification d'identité
    path('verify-identity/', IdentityVerificationView.as_view(), name='verify-identity'),
    path('admin/verify/<int:pk>/', AdminVerificationView.as_view(), name='admin-verify'),
    path('admin/pending-verifications/', PendingVerificationsView.as_view(), name='pending-verifications'),
    
    # Urls d'abonnement
    path('', include(router.urls)),
]