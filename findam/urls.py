# findam/urls.py
# Configuration des URLs principales du projet

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from django.views.generic import TemplateView

# API URLs patterns
api_patterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('accounts/', include('accounts.urls')),
    path('properties/', include('properties.urls')),
    path('bookings/', include('bookings.urls')),
    path('communications/', include('communications.urls')),
    path('payments/', include('payments.urls')),
    path('reviews/', include('reviews.urls')),
]

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # API V1 root
    path('api/v1/', include((api_patterns, 'api'), namespace='v1')),
    
    # Accueil - page par défaut (sera remplacée par le frontend React/Vue.js)
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
]

# Ajout des URLs pour les fichiers média en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Configuration de l'interface d'administration
admin.site.site_header = "Findam Administration"
admin.site.site_title = "Portail d'administration Findam"
admin.site.index_title = "Bienvenue sur le portail d'administration de Findam"