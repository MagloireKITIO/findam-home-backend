# common/middleware.py
from django.http import JsonResponse
from django.urls import resolve
from django.utils.deprecation import MiddlewareMixin
import re

class RoleBasedAccessMiddleware(MiddlewareMixin):
   """
   Middleware qui vérifie l'accès aux routes basé sur le rôle utilisateur.
   """
   
   # Routes réservées aux propriétaires
   OWNER_ROUTES = [
       r'^/api/v1/properties/.*/(publish|unpublish)/$',
       r'^/api/v1/properties/my-properties/$',
       r'^/api/v1/properties/.*/(add-external-booking|images)/$',
       r'^/api/v1/properties/images/',
       r'^/api/v1/properties/unavailabilities/',
       r'^/api/v1/bookings/.*/(confirm|complete|immediate_release|complete_booking_and_release_funds)/$',
       r'^/api/v1/bookings/promo-codes/',
       r'^/api/v1/bookings/reviews/',
       r'^/api/v1/accounts/subscriptions/',
       r'^/api/v1/payments/payment-methods/',
       r'^/api/v1/payments/payouts/',
       r'^/api/v1/communications/conversations/.*/(reveal_contacts)/$',
   ]
   
   # Routes réservées aux administrateurs
   ADMIN_ROUTES = [
       r'^/admin/',
       r'^/api/v1/properties/.*/verify/$',
       r'^/api/v1/accounts/.*/admin-verification/$',
       r'^/api/v1/accounts/pending-verifications/$',
       r'^/api/v1/payments/.*/bulk_verify/$',
       r'^/api/v1/payments/payouts/.*/(confirm|mark_completed|mark_failed|pending|schedule)/$',
       r'^/api/v1/payments/payouts/(process_scheduled|process_ready)/$',
       r'^/api/v1/payments/commissions/summary/$',
       r'^/api/v1/payments/transactions/summary/$',
       r'^/api/v1/reviews/reported-reviews/.*/(admin_review|pending)/$',
       r'^/api/v1/bookings/.*/(immediate_release)/$',
   ]
   
   # Routes spécifiques aux locataires
   TENANT_ROUTES = [
       r'^/api/v1/bookings/bookings/(calendar_data|monthly_summary)/$',
       r'^/api/v1/bookings/.*/initiate_payment/$',
       r'^/api/v1/bookings/.*/check_payment_status/$',
       r'^/api/v1/communications/conversations/start_conversation/$',
       r'^/api/v1/communications/conversations/with_property/$',
       r'^/api/v1/reviews/reviews/my_reviews/$',
   ]
   
   def process_request(self, request):
       """
       Vérifie les permissions avant le traitement de la requête.
       """
       # Ignorer les routes non-API et les routes d'authentification
       if not request.path.startswith('/api/') or 'auth' in request.path:
           return None
           
       # Ignorer si l'utilisateur n'est pas authentifié (géré par d'autres middlewares)
       if not hasattr(request, 'user') or not request.user.is_authenticated:
           return None
           
       user = request.user
       
       # Vérifier les routes propriétaires
       if self._matches_routes(request.path, self.OWNER_ROUTES):
           if not user.is_owner and not user.is_staff:
               return JsonResponse({
                   'error': 'Accès refusé',
                   'detail': 'Cette ressource est réservée aux propriétaires.'
               }, status=403)
       
       # Vérifier les routes administrateur
       if self._matches_routes(request.path, self.ADMIN_ROUTES):
           if not user.is_staff:
               return JsonResponse({
                   'error': 'Accès refusé',
                   'detail': 'Cette ressource est réservée aux administrateurs.'
               }, status=403)
       
       # Vérifier les routes spécifiques aux locataires (optionnel)
       if self._matches_routes(request.path, self.TENANT_ROUTES):
           if not user.is_tenant and not user.is_staff:
               return JsonResponse({
                   'error': 'Accès refusé',
                   'detail': 'Cette ressource est réservée aux locataires.'
               }, status=403)
       
       # Vérifier spécifiquement les requêtes vers l'espace propriétaire via query params
       is_owner_request = request.GET.get('is_owner') == 'true'
       if is_owner_request and not user.is_owner and not user.is_staff:
           return JsonResponse({
               'error': 'Accès refusé',
               'detail': 'Vous ne pouvez pas accéder à l\'espace propriétaire.'
           }, status=403)
       
       return None
   
   def _matches_routes(self, path, route_patterns):
       """
       Vérifie si le chemin correspond à l'un des patterns.
       """
       for pattern in route_patterns:
           if re.match(pattern, path):
               return True
       return False