# Dans le fichier payments/urls.py, ajoutez l'URL du webhook NotchPay
# Voici comment modifier ce fichier:

# payments/urls.py
# Configuration des URLs pour l'application payments

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PaymentMethodViewSet,
    TransactionViewSet,
    PayoutViewSet,
    CommissionViewSet
)
from .views_webhook import notchpay_webhook

# Création du routeur pour les viewsets
router = DefaultRouter()
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'payouts', PayoutViewSet, basename='payout')
router.register(r'commissions', CommissionViewSet, basename='commission')

# Configuration des URLs
urlpatterns = [
    path('', include(router.urls)),
    # Ajouter le webhook NotchPay
    path('webhook/notchpay/', notchpay_webhook, name='notchpay-webhook'),
]