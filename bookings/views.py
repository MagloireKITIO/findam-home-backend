# bookings/views.py
# Vues pour la gestion des réservations

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from .models import Booking, PromoCode, BookingReview, PaymentTransaction
from .serializers import (
    BookingCreateSerializer,
    BookingListSerializer,
    BookingDetailSerializer,
    PromoCodeSerializer,
    PromoCodeCreateSerializer,
    BookingReviewSerializer,
    PaymentTransactionSerializer
)
from .permissions import (
    IsBookingParticipant,
    IsPromoCodeOwnerOrReadOnly,
    CanLeaveReview
)
from .filters import BookingFilter

class BookingViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les réservations.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = BookingFilter
    search_fields = ['property__title', 'tenant__email', 'tenant__first_name', 'tenant__last_name']
    ordering_fields = ['created_at', 'check_in_date', 'total_price']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """
        Retourne la classe de sérialiseur appropriée selon l'action.
        """
        if self.action == 'create':
            return BookingCreateSerializer
        elif self.action == 'list':
            return BookingListSerializer
        else:
            return BookingDetailSerializer
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les propriétaires : uniquement leurs logements
        - Pour les locataires : uniquement leurs réservations
        - Pour les administrateurs : toutes les réservations
        """
        user = self.request.user
        
        if user.is_staff:
            return Booking.objects.all().select_related(
                'property', 'tenant', 'property__city', 'property__neighborhood'
            ).prefetch_related('property__images')
        
        if user.is_owner:
            return Booking.objects.filter(property__owner=user).select_related(
                'property', 'tenant', 'property__city', 'property__neighborhood'
            ).prefetch_related('property__images')
        
        # Par défaut, retourner les réservations du locataire
        return Booking.objects.filter(tenant=user).select_related(
            'property', 'property__city', 'property__neighborhood'
        ).prefetch_related('property__images')
    
    def get_permissions(self):
        """
        Définit les permissions selon l'action.
        """
        if self.action in ['create']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy', 'cancel']:
            permission_classes = [permissions.IsAuthenticated, IsBookingParticipant]
        else:
            permission_classes = [permissions.IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Annule une réservation.
        POST /api/v1/bookings/{id}/cancel/
        """
        booking = self.get_object()
        
        # Vérifier que la réservation est en attente ou confirmée
        if booking.status not in ['pending', 'confirmed']:
            return Response({
                "detail": _("Seules les réservations en attente ou confirmées peuvent être annulées.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier que la date d'arrivée n'est pas passée
        if booking.check_in_date < timezone.now().date():
            return Response({
                "detail": _("Vous ne pouvez pas annuler une réservation dont la date d'arrivée est passée.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Annuler la réservation
        booking.cancel(cancelled_by=request.user)
        
        return Response({
            "detail": _("Réservation annulée avec succès.")
        })
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """
        Confirme une réservation (pour les propriétaires ou administrateurs).
        POST /api/v1/bookings/{id}/confirm/
        """
        booking = self.get_object()
        
        # Vérifier que l'utilisateur est le propriétaire ou un administrateur
        if not (request.user.is_staff or request.user == booking.property.owner):
            return Response({
                "detail": _("Seuls les propriétaires ou administrateurs peuvent confirmer une réservation.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que la réservation est en attente
        if booking.status != 'pending':
            return Response({
                "detail": _("Seules les réservations en attente peuvent être confirmées.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier que le paiement est effectué
        if booking.payment_status != 'paid':
            return Response({
                "detail": _("La réservation ne peut être confirmée que si le paiement est effectué.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Confirmer la réservation
        booking.status = 'confirmed'
        booking.save(update_fields=['status'])
        
        return Response({
            "detail": _("Réservation confirmée avec succès.")
        })
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        Marque une réservation comme terminée (pour les propriétaires ou administrateurs).
        POST /api/v1/bookings/{id}/complete/
        """
        booking = self.get_object()
        
        # Vérifier que l'utilisateur est le propriétaire ou un administrateur
        if not (request.user.is_staff or request.user == booking.property.owner):
            return Response({
                "detail": _("Seuls les propriétaires ou administrateurs peuvent marquer une réservation comme terminée.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que la réservation est confirmée
        if booking.status != 'confirmed':
            return Response({
                "detail": _("Seules les réservations confirmées peuvent être marquées comme terminées.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier que la date de départ est passée
        if booking.check_out_date > timezone.now().date():
            return Response({
                "detail": _("La réservation ne peut être marquée comme terminée qu'après la date de départ.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Marquer la réservation comme terminée
        booking.status = 'completed'
        booking.save(update_fields=['status'])
        
        return Response({
            "detail": _("Réservation marquée comme terminée avec succès.")
        })
    
    @action(detail=True, methods=['post'])
    def initiate_payment(self, request, pk=None):
        """
        Initie le paiement d'une réservation.
        POST /api/v1/bookings/{id}/initiate_payment/
        """
        import requests
        import json
        from django.conf import settings
        
        booking = self.get_object()
        
        # Vérifier que l'utilisateur est le locataire
        if request.user != booking.tenant:
            return Response({
                "detail": _("Seul le locataire peut payer une réservation.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que la réservation est en attente
        if booking.status != 'pending':
            return Response({
                "detail": _("Seules les réservations en attente peuvent être payées.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier que le paiement n'a pas déjà été effectué
        if booking.payment_status == 'paid':
            return Response({
                "detail": _("Cette réservation a déjà été payée.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer la méthode de paiement
        payment_method = request.data.get('payment_method')
        if not payment_method or payment_method not in ['mobile_money', 'credit_card', 'bank_transfer']:
            return Response({
                "detail": _("Méthode de paiement non valide.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Créer une transaction de paiement
        transaction = PaymentTransaction.objects.create(
            booking=booking,
            amount=booking.total_price,
            payment_method=payment_method,
            status='pending'
        )
        
        # Intégration avec NotchPay
        api_key = settings.NOTCHPAY_PRIVATE_KEY
        is_sandbox = settings.NOTCHPAY_SANDBOX
        
        # Configuration de l'API NotchPay
        api_url = "https://api.notchpay.co/payments/initialize" if not is_sandbox else "https://api.sandbox.notchpay.co/payments/initialize"
        
        # Préparer les données pour NotchPay
        payment_data = {
            "email": booking.tenant.email,
            "amount": float(booking.total_price),
            "currency": "XAF",  # Franc CFA
            "reference": str(transaction.id),  # ID unique de la transaction
            "callback": request.build_absolute_uri(f'/api/v1/bookings/payment_callback/'),
            "description": f"Paiement réservation {booking.id} - {booking.property.title}",
            "channels": [payment_method],  # Restreindre aux canaux de paiement sélectionnés
            "customer": {
                "name": booking.tenant.get_full_name(),
                "phone": booking.tenant.phone_number
            },
            "metadata": {
                "booking_id": str(booking.id),
                "transaction_id": str(transaction.id)
            }
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            # Envoyer la requête à NotchPay
            response = requests.post(api_url, headers=headers, data=json.dumps(payment_data))
            payment_response = response.json()
            
            # Mettre à jour la transaction avec la réponse de NotchPay
            transaction.payment_response = payment_response
            
            if response.status_code == 200 and payment_response.get('status') == 'success':
                transaction.transaction_id = payment_response.get('data', {}).get('reference', '')
                transaction.status = 'processing'
                transaction.save()
                
                # Retourner l'URL de paiement au client
                return Response({
                    "payment_url": payment_response.get('data', {}).get('authorization_url', ''),
                    "transaction_id": transaction.id
                })
            else:
                transaction.status = 'failed'
                transaction.save()
                
                return Response({
                    "detail": _("Échec de l'initialisation du paiement."),
                    "error": payment_response.get('message', 'Erreur inconnue')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            transaction.status = 'failed'
            transaction.payment_response = {"error": str(e)}
            transaction.save()
            
            return Response({
                "detail": _("Une erreur est survenue lors de l'initialisation du paiement."),
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def payment_callback(self, request):
        """
        Callback pour NotchPay.
        POST /api/v1/bookings/payment_callback/
        """
        import hmac
        import hashlib
        from django.conf import settings
        
        # Vérifier la signature de la requête pour sécuriser le callback
        signature = request.headers.get('X-Notch-Signature', '')
        payload = request.body
        
        # Récupérer la clé secrète
        secret_key = settings.NOTCHPAY_PRIVATE_KEY
        
        # Calculer la signature HMAC SHA256
        expected_signature = hmac.new(
            key=secret_key.encode(),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Vérifier que la signature correspond
        if not hmac.compare_digest(signature, expected_signature):
            return Response({
                "detail": _("Signature non valide.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Récupérer les données de la transaction
        data = request.data
        
        # Vérifier le statut du paiement
        payment_status = data.get('data', {}).get('status')
        transaction_reference = data.get('data', {}).get('reference')
        
        try:
            # Récupérer la transaction
            transaction = PaymentTransaction.objects.get(id=transaction_reference)
            
            # Mettre à jour la transaction
            transaction.payment_response = data
            
            if payment_status == 'success':
                transaction.status = 'completed'
                transaction.save()
                
                # Mettre à jour le statut de paiement de la réservation
                booking = transaction.booking
                booking.payment_status = 'paid'
                booking.save(update_fields=['payment_status'])
                
                return Response({
                    "detail": _("Paiement réussi.")
                })
            elif payment_status == 'failed':
                transaction.status = 'failed'
                transaction.save()
                
                return Response({
                    "detail": _("Paiement échoué.")
                })
            else:
                transaction.status = 'processing'
                transaction.save()
                
                return Response({
                    "detail": _("Paiement en cours de traitement.")
                })
                
        except PaymentTransaction.DoesNotExist:
            return Response({
                "detail": _("Transaction non trouvée.")
            }, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def check_payment_status(self, request, pk=None):
        """
        Vérifie le statut d'un paiement.
        GET /api/v1/bookings/{id}/check_payment_status/
        """
        import requests
        from django.conf import settings
        
        booking = self.get_object()
        
        # Récupérer la dernière transaction
        transaction = booking.transactions.order_by('-created_at').first()
        
        if not transaction:
            return Response({
                "detail": _("Aucune transaction trouvée pour cette réservation.")
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Si la transaction est déjà terminée ou a échoué, retourner son statut
        if transaction.status in ['completed', 'failed']:
            return Response({
                "status": transaction.status,
                "booking_status": booking.status,
                "payment_status": booking.payment_status
            })
        
        # Sinon, vérifier le statut auprès de NotchPay
        api_key = settings.NOTCHPAY_PRIVATE_KEY
        is_sandbox = settings.NOTCHPAY_SANDBOX
        
        api_url = f"https://api{'sandbox.' if is_sandbox else '.'}notchpay.co/payments/verify/{transaction.transaction_id}"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            # Envoyer la requête à NotchPay
            response = requests.get(api_url, headers=headers)
            payment_data = response.json()
            
            # Mettre à jour la transaction avec la réponse de NotchPay
            transaction.payment_response = payment_data
            
            if response.status_code == 200:
                payment_status = payment_data.get('data', {}).get('status')
                
                if payment_status == 'success':
                    transaction.status = 'completed'
                    booking.payment_status = 'paid'
                    booking.save(update_fields=['payment_status'])
                elif payment_status == 'failed':
                    transaction.status = 'failed'
                
                transaction.save()
                
                return Response({
                    "status": transaction.status,
                    "booking_status": booking.status,
                    "payment_status": booking.payment_status,
                    "details": payment_data.get('data', {})
                })
            else:
                return Response({
                    "detail": _("Erreur lors de la vérification du statut du paiement."),
                    "error": payment_data.get('message', 'Erreur inconnue')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                "detail": _("Une erreur est survenue lors de la vérification du statut du paiement."),
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PromoCodeViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les codes promotionnels.
    """
    permission_classes = [permissions.IsAuthenticated, IsPromoCodeOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['code', 'tenant__email', 'property__title']
    filterset_fields = ['property', 'tenant', 'is_active']
    
    def get_serializer_class(self):
        """Retourne la classe de sérialiseur appropriée selon l'action."""
        if self.action == 'create':
            return PromoCodeCreateSerializer
        return PromoCodeSerializer
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les propriétaires : uniquement leurs codes promo
        - Pour les locataires : uniquement les codes promo qui leur sont destinés
        - Pour les administrateurs : tous les codes promo
        """
        user = self.request.user
        
        if user.is_staff:
            return PromoCode.objects.all().select_related('property', 'tenant', 'created_by')
        
        if user.is_owner:
            return PromoCode.objects.filter(property__owner=user).select_related('property', 'tenant', 'created_by')
        
        # Par défaut, retourner les codes promo du locataire
        return PromoCode.objects.filter(tenant=user).select_related('property', 'tenant', 'created_by')
    
    def perform_create(self, serializer):
        """Associe automatiquement le créateur au code promo."""
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def validate_code(self, request):
        """
        Valide un code promo pour un logement.
        GET /api/v1/bookings/promo-codes/validate-code/?code=XXX&property=YYY
        """
        code = request.query_params.get('code')
        property_id = request.query_params.get('property')
        
        if not code or not property_id:
            return Response({
                "detail": _("Code promo et ID de logement requis.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            promo_code = PromoCode.objects.get(
                code=code,
                property_id=property_id,
                is_active=True,
                expiry_date__gt=timezone.now()
            )
            
            # Vérifier que le code promo est bien pour ce locataire
            if promo_code.tenant != request.user and not request.user.is_staff:
                return Response({
                    "valid": False,
                    "detail": _("Ce code promo ne vous est pas destiné.")
                }, status=status.HTTP_403_FORBIDDEN)
            
            return Response({
                "valid": True,
                "promo_code": PromoCodeSerializer(promo_code).data
            })
            
        except PromoCode.DoesNotExist:
            return Response({
                "valid": False,
                "detail": _("Code promo invalide ou expiré.")
            }, status=status.HTTP_404_NOT_FOUND)

class BookingReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les avis sur les réservations.
    """
    serializer_class = BookingReviewSerializer
    permission_classes = [permissions.IsAuthenticated, CanLeaveReview]
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        """
        user = self.request.user
        
        if user.is_staff:
            return BookingReview.objects.all().select_related('booking__property', 'booking__tenant')
        
        # Pour les propriétaires et locataires, retourner les avis liés à leurs réservations
        if user.is_owner:
            return BookingReview.objects.filter(
                Q(booking__property__owner=user) | Q(booking__tenant=user)
            ).select_related('booking__property', 'booking__tenant')
        
        # Par défaut, retourner les avis liés aux réservations du locataire
        return BookingReview.objects.filter(
            booking__tenant=user
        ).select_related('booking__property', 'booking__tenant')
    
    @action(detail=False, methods=['get'])
    def property_reviews(self, request):
        """
        Récupère les avis pour un logement.
        GET /api/v1/bookings/reviews/property-reviews/?property=XXX
        """
        property_id = request.query_params.get('property')
        
        if not property_id:
            return Response({
                "detail": _("ID de logement requis.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        reviews = BookingReview.objects.filter(
            booking__property_id=property_id,
            is_from_owner=False  # Uniquement les avis des locataires
        ).select_related('booking', 'booking__tenant')
        
        serializer = BookingReviewSerializer(reviews, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def tenant_reviews(self, request):
        """
        Récupère les avis pour un locataire.
        GET /api/v1/bookings/reviews/tenant-reviews/?tenant=XXX
        """
        tenant_id = request.query_params.get('tenant')
        
        if not tenant_id:
            return Response({
                "detail": _("ID de locataire requis.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        reviews = BookingReview.objects.filter(
            booking__tenant_id=tenant_id,
            is_from_owner=True  # Uniquement les avis des propriétaires
        ).select_related('booking', 'booking__property', 'booking__property__owner')
        
        serializer = BookingReviewSerializer(reviews, many=True, context={'request': request})
        return Response(serializer.data)