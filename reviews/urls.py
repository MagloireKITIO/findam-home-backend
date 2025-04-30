# reviews/urls.py
# Configuration des URLs pour l'application reviews

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ReviewViewSet,
    ReviewReplyViewSet,
    ReportedReviewViewSet
)

# Création du routeur pour les viewsets
router = DefaultRouter()
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'replies', ReviewReplyViewSet, basename='review-reply')
router.register(r'reported-reviews', ReportedReviewViewSet, basename='reported-review')

# Configuration des URLs
urlpatterns = [
    path('', include(router.urls)),
]