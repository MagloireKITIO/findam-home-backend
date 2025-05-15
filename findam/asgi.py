# findam/asgi.py
import os
import django
from django.core.asgi import get_asgi_application

# Configurer Django AVANT d'importer les modules WebSocket
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'findam.settings')
django.setup()

# MAINTENANT importer les modules WebSocket
from channels.routing import ProtocolTypeRouter, URLRouter
from communications.middleware import TokenAuthMiddleware
from communications.routing import websocket_urlpatterns

# Application Django standard
django_asgi_app = get_asgi_application()

# Configuration complète
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TokenAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})