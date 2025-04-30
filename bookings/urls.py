# bookings/urls.py
# Configuration des URLs pour l'application bookings

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BookingViewSet,
    PromoCodeViewSet,
    BookingReviewViewSet
)

# Création du routeur pour les viewsets
router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'promo-codes', PromoCodeViewSet, basename='promo-code')
router.register(r'reviews', BookingReviewViewSet, basename='booking-review')

# Configuration des URLs
urlpatterns = [
    path('', include(router.urls)),
]