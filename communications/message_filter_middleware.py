# communications/message_filter_middleware.py

from django.utils.deprecation import MiddlewareMixin
from .services.message_filter_service import MessageFilterService

class MessageFilterMiddleware(MiddlewareMixin):
    """
    Middleware pour filtrer automatiquement les messages
    avant qu'ils soient sauvegardés ou envoyés.
    """
    
    def process_request(self, request):
        # Intercepter les requêtes de création de messages
        if (request.path.startswith('/api/v1/communications/messages/') 
            and request.method == 'POST'):
            
            # Marquer la requête pour filtrage
            request._should_filter_message = True
        
        return None