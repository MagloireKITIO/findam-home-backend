
# common/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SystemConfigurationViewSet

router = DefaultRouter()
router.register(r'system', SystemConfigurationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]