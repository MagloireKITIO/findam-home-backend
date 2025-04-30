# findam/routing.py
# Configuration principale des routes WebSocket pour Django Channels

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
import communications.routing

application = ProtocolTypeRouter({
    # WebSocket avec authentification middleware
    'websocket': AuthMiddlewareStack(
        URLRouter(
            communications.routing.websocket_urlpatterns
        )
    ),
})