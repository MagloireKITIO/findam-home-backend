# findam/asgi.py
"""
ASGI config for findam project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import communications.routing
from communications.middleware import TokenAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'findam.settings')

# Initialiser l'application Django ASGI
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    # Django gère les requêtes HTTP
    "http": django_asgi_app,
    
    # Configuration WebSocket avec middleware d'authentification JWT personnalisé
    "websocket": AllowedHostsOriginValidator(
        TokenAuthMiddleware(
            URLRouter(
                communications.routing.websocket_urlpatterns
            )
        )
    ),
})