# communications/middleware.py - Version corrigée
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from urllib.parse import parse_qs
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

@database_sync_to_async
def get_user(user_id):
    """
    Récupère un utilisateur à partir de son ID.
    """
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class TokenAuthMiddleware:
    """
    Middleware JWT pour authentifier les utilisateurs dans les WebSockets.
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        # Récupérer le token JWT depuis les paramètres de la requête
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        
        # Extraire le token du query string
        token = query_params.get('token', [None])[0]
        
        if token:
            try:
                # Valider le token JWT
                access_token = AccessToken(token)
                user_id = access_token.payload.get('user_id')
                
                # Récupérer l'utilisateur
                scope['user'] = await get_user(user_id)
                logger.info(f"WebSocket authenticated for user: {user_id}")
            except InvalidToken as e:
                logger.warning(f"Invalid token for WebSocket: {e}")
                scope['user'] = AnonymousUser()
            except TokenError as e:
                logger.warning(f"Token error for WebSocket: {e}")
                scope['user'] = AnonymousUser()
            except Exception as e:
                logger.error(f"Unexpected error in token auth: {e}")
                scope['user'] = AnonymousUser()
        else:
            logger.warning("No token provided for WebSocket authentication")
            scope['user'] = AnonymousUser()
        
        return await self.app(scope, receive, send)