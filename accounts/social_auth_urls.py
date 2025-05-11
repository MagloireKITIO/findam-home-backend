from django.urls import path
from .social_auth_views import GoogleLoginView, GoogleCallbackView

urlpatterns = [
    path('', GoogleLoginView.as_view(), name='google-login'),
    path('callback/', GoogleCallbackView.as_view(), name='google-callback'),
]