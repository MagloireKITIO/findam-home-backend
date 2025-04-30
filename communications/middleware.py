# communications/middleware.py
# Middleware pour les WebSockets

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

User = get_user_model()

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
        params = dict(q.split('=') for q in query_string.split('&') if q)
        
        token = params.get('token', None)
        
        if token:
            try:
                # Valider le token JWT
                access_token = AccessToken(token)
                user_id = access_token.payload.get('user_id')
                
                # Récupérer l'utilisateur
                scope['user'] = await get_user(user_id)
            except (InvalidToken, TokenError):
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()
        
        return await self.app(scope, receive, send)