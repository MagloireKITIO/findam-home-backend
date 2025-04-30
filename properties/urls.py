# properties/urls.py
# Configuration des URLs pour l'application properties

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AmenityViewSet,
    CityViewSet,
    NeighborhoodViewSet,
    PropertyViewSet,
    PropertyImageViewSet,
    AvailabilityViewSet,
)

# Création du routeur pour les viewsets
router = DefaultRouter()
router.register(r'amenities', AmenityViewSet, basename='amenity')
router.register(r'cities', CityViewSet, basename='city')
router.register(r'neighborhoods', NeighborhoodViewSet, basename='neighborhood')
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'images', PropertyImageViewSet, basename='property-image')
router.register(r'unavailabilities', AvailabilityViewSet, basename='unavailability')

# Configuration des URLs
urlpatterns = [
    path('', include(router.urls)),
]