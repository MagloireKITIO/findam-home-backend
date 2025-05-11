# accounts/social_auth_views.py
# Vues pour gérer l'authentification sociale (Google, Facebook)

import os
import json
import requests
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.utils import timezone

from rest_framework import status, generics, views
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import SocialAccount, User, Profile

User = get_user_model()

# Configuration des providers d'authentification sociale
SOCIAL_AUTH_PROVIDERS = {
    'google': {
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'auth_url': 'https://accounts.google.com/o/oauth2/auth',
        'token_url': 'https://oauth2.googleapis.com/token',
        'user_info_url': 'https://www.googleapis.com/oauth2/v3/userinfo',
        'scope': 'email profile openid',
    },
    'facebook': {
        'client_id': settings.FACEBOOK_APP_ID,
        'client_secret': settings.FACEBOOK_APP_SECRET,
        'redirect_uri': settings.FACEBOOK_REDIRECT_URI,
        'auth_url': 'https://www.facebook.com/v12.0/dialog/oauth',
        'token_url': 'https://graph.facebook.com/v12.0/oauth/access_token',
        'user_info_url': 'https://graph.facebook.com/me',
        'scope': 'email public_profile',
    }
}

# Vue pour initialiser l'authentification Google
class GoogleLoginView(views.APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        # Générer l'état pour la vérification CSRF
        state = str(uuid.uuid4())
        
        # Stocker l'état dans la session
        request.session['oauth_state'] = state
        
        # Définir les paramètres de l'URL d'authentification
        params = {
            'client_id': SOCIAL_AUTH_PROVIDERS['google']['client_id'],
            'redirect_uri': SOCIAL_AUTH_PROVIDERS['google']['redirect_uri'],
            'response_type': 'code',
            'scope': SOCIAL_AUTH_PROVIDERS['google']['scope'],
            'state': state,
            'prompt': 'select_account', # Force le choix du compte
            'access_type': 'offline',  # Pour obtenir un refresh token
        }
        
        # Construire l'URL d'authentification
        auth_url = f"{SOCIAL_AUTH_PROVIDERS['google']['auth_url']}?{urlencode(params)}"
        
        # Rediriger vers l'URL d'authentification Google
        return HttpResponseRedirect(auth_url)

# Vue pour gérer le callback de Google
class GoogleCallbackView(views.APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        # Récupérer le code et l'état de la redirection
        code = request.query_params.get('code', None)
        state = request.query_params.get('state', None)
        
        # Vérifier si l'état correspond à celui stocké dans la session (protection CSRF)
        saved_state = request.session.get('oauth_state', None)
        if not saved_state or state != saved_state:
            return Response({'error': 'État invalide'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Supprimer l'état de la session
        request.session.pop('oauth_state', None)
        
         # Échanger le code contre un token d'accès
        token_data = self._exchange_code_for_token(code)
        if not token_data:
            return Response({'error': 'Échec de l\'échange du code contre un token'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer les infos utilisateur
        user_info = self._get_user_info(token_data.get('access_token'))
        if not user_info:
            return Response({'error': 'Échec de la récupération des informations utilisateur'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Créer ou mettre à jour l'utilisateur - ajoutez un drapeau pour savoir si c'est un nouvel utilisateur
        user, is_new_user = self._get_or_create_user(user_info, 'google')
        
        # Générer les tokens JWT
        refresh = RefreshToken.for_user(user)
        tokens = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        
        # Rediriger vers différentes pages selon que l'utilisateur est nouveau ou existant
        if is_new_user:
            # Rediriger vers la page de complétion du profil
            frontend_callback_url = f"{settings.FRONTEND_URL}/auth/complete-profile?provider=google&access_token={tokens['access']}&refresh_token={tokens['refresh']}&is_new=true"
        else:
            # Rediriger vers la page d'accueil/dashboard pour les utilisateurs existants
            frontend_callback_url = f"{settings.FRONTEND_URL}/auth/callback?provider=google&access_token={tokens['access']}&refresh_token={tokens['refresh']}"
        
        return HttpResponseRedirect(frontend_callback_url)
                
    
    def _exchange_code_for_token(self, code):
        """Échange le code d'autorisation contre un token d'accès"""
        token_url = SOCIAL_AUTH_PROVIDERS['google']['token_url']
        data = {
            'client_id': SOCIAL_AUTH_PROVIDERS['google']['client_id'],
            'client_secret': SOCIAL_AUTH_PROVIDERS['google']['client_secret'],
            'redirect_uri': SOCIAL_AUTH_PROVIDERS['google']['redirect_uri'],
            'code': code,
            'grant_type': 'authorization_code'
        }
        
        try:
            response = requests.post(token_url, data=data)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Erreur lors de l'échange du code: {str(e)}")
            return None
    
    def _get_user_info(self, access_token):
        """Récupère les informations utilisateur à partir du token d'accès"""
        user_info_url = SOCIAL_AUTH_PROVIDERS['google']['user_info_url']
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(user_info_url, headers=headers)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Erreur lors de la récupération des infos utilisateur: {str(e)}")
            return None
    
    def _get_or_create_user(self, user_info, provider):
        """Crée ou met à jour un utilisateur à partir des informations Google"""
        email = user_info.get('email')
        if not email:
            raise ValueError("L'email est requis")
        
        # Créer ou récupérer un utilisateur
        try:
            user = User.objects.get(email=email)
            is_new_user = False
        except User.DoesNotExist:
            # Créer un nouvel utilisateur avec des valeurs par défaut minimales
            user = User.objects.create_user(
                email=email,
                phone_number="+0000000000",  # Numéro temporaire
                first_name=user_info.get('given_name', ''),
                last_name=user_info.get('family_name', ''),
                is_active=True,
                # Ne pas fixer le user_type pour l'instant, il sera défini dans le formulaire de complétion
                user_type=''  # Laissez vide ou utilisez une valeur par défaut selon votre modèle
            )
            is_new_user = True
        
        # Créer ou mettre à jour le compte social
        SocialAccount.objects.update_or_create(
            user=user,
            provider=provider,
            defaults={
                'provider_user_id': user_info.get('sub', ''),
                'email': email,
                'name': f"{user_info.get('given_name', '')} {user_info.get('family_name', '')}",
                'extra_data': user_info
            }
        )
        
        return user, is_new_user

# Vue pour initialiser l'authentification Facebook
class FacebookLoginView(views.APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        # Générer l'état pour la vérification CSRF
        state = str(uuid.uuid4())
        
        # Stocker l'état dans la session
        request.session['oauth_state'] = state
        
        # Définir les paramètres de l'URL d'authentification
        params = {
            'client_id': SOCIAL_AUTH_PROVIDERS['facebook']['client_id'],
            'redirect_uri': SOCIAL_AUTH_PROVIDERS['facebook']['redirect_uri'],
            'response_type': 'code',
            'scope': SOCIAL_AUTH_PROVIDERS['facebook']['scope'],
            'state': state,
        }
        
        # Construire l'URL d'authentification
        auth_url = f"{SOCIAL_AUTH_PROVIDERS['facebook']['auth_url']}?{urlencode(params)}"
        
        # Rediriger vers l'URL d'authentification Facebook
        return Response({'auth_url': auth_url})

# Vue pour gérer le callback de Facebook
class FacebookCallbackView(views.APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        # Récupérer le code et l'état de la redirection
        code = request.query_params.get('code', None)
        state = request.query_params.get('state', None)
        
        # Vérifier si l'état correspond à celui stocké dans la session (protection CSRF)
        saved_state = request.session.get('oauth_state', None)
        if not saved_state or state != saved_state:
            return Response({'error': 'État invalide'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Supprimer l'état de la session
        request.session.pop('oauth_state', None)
        
        # Échanger le code contre un token d'accès
        token_data = self._exchange_code_for_token(code)
        if not token_data:
            return Response({'error': 'Échec de l\'échange du code contre un token'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer les infos utilisateur
        user_info = self._get_user_info(token_data.get('access_token'))
        if not user_info:
            return Response({'error': 'Échec de la récupération des informations utilisateur'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Créer ou mettre à jour l'utilisateur
        user = self._get_or_create_user(user_info, 'facebook')
        
        # Générer les tokens JWT
        refresh = RefreshToken.for_user(user)
        tokens = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        
        # Rediriger vers le frontend avec les tokens en paramètres
        frontend_callback_url = f"{settings.FRONTEND_URL}/auth/callback?provider=facebook&access_token={tokens['access']}&refresh_token={tokens['refresh']}"
        
        return HttpResponseRedirect(frontend_callback_url)
    
    def _exchange_code_for_token(self, code):
        """Échange le code d'autorisation contre un token d'accès"""
        token_url = SOCIAL_AUTH_PROVIDERS['facebook']['token_url']
        params = {
            'client_id': SOCIAL_AUTH_PROVIDERS['facebook']['client_id'],
            'client_secret': SOCIAL_AUTH_PROVIDERS['facebook']['client_secret'],
            'redirect_uri': SOCIAL_AUTH_PROVIDERS['facebook']['redirect_uri'],
            'code': code,
        }
        
        try:
            response = requests.get(token_url, params=params)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Erreur lors de l'échange du code: {str(e)}")
            return None
    
    def _get_user_info(self, access_token):
        """Récupère les informations utilisateur à partir du token d'accès"""
        user_info_url = SOCIAL_AUTH_PROVIDERS['facebook']['user_info_url']
        params = {
            'fields': 'id,name,email,first_name,last_name,picture',
            'access_token': access_token
        }
        
        try:
            response = requests.get(user_info_url, params=params)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Erreur lors de la récupération des infos utilisateur: {str(e)}")
            return None
    
    def _get_or_create_user(self, user_info, provider):
        """Crée ou met à jour un utilisateur à partir des informations Facebook"""
        email = user_info.get('email')
        if not email:
            raise ValueError("L'email est requis")
        
        # Créer ou récupérer un utilisateur
        try:
            user = User.objects.get(email=email)
            created = False
        except User.DoesNotExist:
            # Créer un nouvel utilisateur
            user = User.objects.create_user(
                email=email,
                phone_number="+0000000000",  # Numéro temporaire
                first_name=user_info.get('first_name', ''),
                last_name=user_info.get('last_name', ''),
                is_active=True
            )
            created = True
        
        # Créer ou mettre à jour le compte social
        SocialAccount.objects.update_or_create(
            user=user,
            provider=provider,
            defaults={
                'provider_user_id': user_info.get('id', ''),
                'email': email,
                'name': user_info.get('name', ''),
                'extra_data': user_info
            }
        )
        
        return user

# Vue pour lister les comptes sociaux connectés
class SocialAccountsListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        social_accounts = SocialAccount.objects.filter(user=user)
        
        accounts_data = [{
            'provider': account.provider,
            'provider_user_id': account.provider_user_id,
            'email': account.email,
            'name': account.name,
            'first_login': account.first_login,
            'last_login': account.last_login
        } for account in social_accounts]
        
        return Response(accounts_data)

# Vue pour connecter un compte social à un compte existant
class ConnectSocialAccountView(views.APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        provider = request.data.get('provider')
        access_token = request.data.get('access_token')
        
        if not provider or not access_token:
            return Response({'error': 'Provider et access_token sont requis'}, status=status.HTTP_400_BAD_REQUEST)
        
        if provider not in SOCIAL_AUTH_PROVIDERS:
            return Response({'error': 'Provider non supporté'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer les infos utilisateur
        user_info = self._get_user_info(provider, access_token)
        if not user_info:
            return Response({'error': 'Échec de la récupération des informations utilisateur'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier que le compte social n'est pas déjà connecté à un autre utilisateur
        provider_user_id = user_info.get('sub') if provider == 'google' else user_info.get('id')
        email = user_info.get('email')
        
        if not email:
            return Response({'error': "L'email est requis"}, status=status.HTTP_400_BAD_REQUEST)
            
        existing_account = SocialAccount.objects.filter(provider=provider, provider_user_id=provider_user_id).first()
        if existing_account and existing_account.user != request.user:
            return Response({'error': 'Ce compte social est déjà connecté à un autre utilisateur'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Créer ou mettre à jour le compte social
        social_account, created = SocialAccount.objects.update_or_create(
            user=request.user,
            provider=provider,
            defaults={
                'provider_user_id': provider_user_id,
                'email': email,
                'name': f"{user_info.get('given_name', '')} {user_info.get('family_name', '')}" if provider == 'google' else user_info.get('name', ''),
                'first_login': created,
                'last_login': timezone.now()
            }
        )
        
        return Response({
            'provider': social_account.provider,
            'email': social_account.email,
            'name': social_account.name,
            'message': 'Compte social connecté avec succès'
        })
    
    def _get_user_info(self, provider, access_token):
        """Récupère les informations utilisateur à partir du token d'accès"""
        user_info_url = SOCIAL_AUTH_PROVIDERS[provider]['user_info_url']
        
        try:
            if provider == 'google':
                headers = {'Authorization': f'Bearer {access_token}'}
                response = requests.get(user_info_url, headers=headers)
            else:  # facebook
                params = {
                    'fields': 'id,name,email,first_name,last_name,picture',
                    'access_token': access_token
                }
                response = requests.get(user_info_url, params=params)
                
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Erreur lors de la récupération des infos utilisateur: {str(e)}")
            return None

# Vue pour déconnecter un compte social
class DisconnectSocialAccountView(views.APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        provider = request.data.get('provider')
        
        if not provider:
            return Response({'error': 'Provider est requis'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier si le compte social existe
        try:
            social_account = SocialAccount.objects.get(user=request.user, provider=provider)
        except SocialAccount.DoesNotExist:
            return Response({'error': 'Compte social non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        
        # Supprimer le compte social
        social_account.delete()
        
        return Response({'message': 'Compte social déconnecté avec succès'})