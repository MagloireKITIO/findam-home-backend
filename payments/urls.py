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

# Création du routeur pour les viewsets
router = DefaultRouter()
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'payouts', PayoutViewSet, basename='payout')
router.register(r'commissions', CommissionViewSet, basename='commission')

# Configuration des URLs
urlpatterns = [
    path('', include(router.urls)),
]