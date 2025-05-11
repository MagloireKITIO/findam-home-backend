# accounts/urls.py
# Configuration des URLs pour l'application accounts avec authentification sociale

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
    CompleteProfileView,
)
# Importation des vues d'authentification sociale
from .social_auth_views import (
    GoogleLoginView,
    GoogleCallbackView,
    FacebookLoginView,
    FacebookCallbackView,
    SocialAccountsListView,
    ConnectSocialAccountView,
    DisconnectSocialAccountView
)
# Importation des vues de réinitialisation de mot de passe
from .password_views import (
    PasswordResetView,
    PasswordResetConfirmView,
    ValidateResetTokenView
)

# Création du routeur pour les abonnements
router = DefaultRouter()
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')

urlpatterns = [
    # Urls d'authentification
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('change-password/', PasswordChangeView.as_view(), name='change-password'),
    
    # Urls d'authentification sociale
    path('auth/google/', GoogleLoginView.as_view(), name='google-login'),
    path('auth/google/callback/', GoogleCallbackView.as_view(), name='google-callback'),
    path('auth/facebook/', FacebookLoginView.as_view(), name='facebook-login'),
    path('auth/facebook/callback/', FacebookCallbackView.as_view(), name='facebook-callback'),
    path('social-accounts/', SocialAccountsListView.as_view(), name='social-accounts-list'),
    path('connect-social/', ConnectSocialAccountView.as_view(), name='connect-social'),
    path('disconnect-social/', DisconnectSocialAccountView.as_view(), name='disconnect-social'),
    path('profile/complete/', CompleteProfileView.as_view(), name='complete-profile'),

    # Urls de réinitialisation de mot de passe
    path('password-reset/', PasswordResetView.as_view(), name='password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('password-reset/validate-token/', ValidateResetTokenView.as_view(), name='validate-reset-token'),
    
    # Urls de vérification d'identité
    path('verify-identity/', IdentityVerificationView.as_view(), name='verify-identity'),
    path('admin/verify/<int:pk>/', AdminVerificationView.as_view(), name='admin-verify'),
    path('admin/pending-verifications/', PendingVerificationsView.as_view(), name='pending-verifications'),
    
    # Urls d'abonnement
    path('', include(router.urls)),
]