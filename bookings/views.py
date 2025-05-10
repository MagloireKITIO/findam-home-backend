# bookings/views.py
# Vues pour la gestion des réservations

from rest_framework import viewsets, permissions, status, filters
from django.utils.translation import gettext as _

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
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        
        # Utiliser BookingDetailSerializer pour la réponse
        return Response(
            BookingDetailSerializer(booking, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED
        )
    
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
        from payments.services.notchpay_service import NotchPayService
        from payments.utils import NotchPayUtils
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
        payment_method = request.data.get('payment_method', 'mobile_money')
        
        # Récupérer l'opérateur mobile si fourni (orange, mtn, mobile_money)
        mobile_operator = request.data.get('mobile_operator', 'mobile_money')
        notchpay_channel = NotchPayUtils.get_mobile_operator_code(mobile_operator)
        
        # Récupérer et formater le numéro de téléphone pour mobile money
        phone_number = request.data.get('phone_number', '')
        formatted_phone = NotchPayUtils.format_phone_number(phone_number) if phone_number else NotchPayUtils.format_phone_number(request.user.phone_number)
        
        # Créer une transaction de paiement
        transaction = PaymentTransaction.objects.create(
            booking=booking,
            amount=booking.total_price,
            payment_method=payment_method,
            status='pending'
        )
        
        # Préparer les métadonnées pour NotchPay
        metadata = {
            'transaction_type': 'booking',
            'object_id': str(booking.id),
            'transaction_id': str(transaction.id)
        }
        
        # Préparer les informations client
        customer_info = {
            'email': booking.tenant.email,
            'phone': formatted_phone,
            'name': f"{booking.tenant.first_name} {booking.tenant.last_name}"
        }
        
        # Préparation de la description
        description = f"Réservation {booking.id} - {booking.property.title} du {booking.check_in_date} au {booking.check_out_date}"
        
        # URLs de redirection
        callback_url = f"{settings.PAYMENT_CALLBACK_BASE_URL}/api/v1/payments/webhook/notchpay/"
        success_url = f"{settings.FRONTEND_URL}/bookings/{booking.id}?payment_status=success"
        cancel_url = f"{settings.FRONTEND_URL}/bookings/{booking.id}?payment_status=cancel"
        
        try:
            # Initialiser le service NotchPay
            notchpay_service = NotchPayService()
            
            # Référence unique pour le paiement
            payment_reference = f"booking-{booking.id}-{transaction.id}"
            transaction.transaction_id = payment_reference
            transaction.save(update_fields=['transaction_id'])
            
            # Initialiser le paiement via NotchPay
            payment_result = notchpay_service.initialize_payment(
                amount=booking.total_price,
                currency='XAF',
                description=description,
                customer_info=customer_info,
                metadata=metadata,
                reference=payment_reference,
                callback_url=callback_url,
                success_url=success_url,
                cancel_url=cancel_url
            )
            
            # Mettre à jour la transaction avec les informations de NotchPay
            if payment_result and 'transaction' in payment_result:
                transaction.payment_response = payment_result
    
                # Stocker la référence NotchPay dans la transaction
                notchpay_reference = payment_result['transaction'].get('reference', '')
                transaction.payment_details = {"notchpay_reference": notchpay_reference}
                
                transaction.status = 'processing'
                transaction.save()
                
                # Retourner l'URL de paiement au client
                return Response({
                    "payment_url": payment_result.get('authorization_url', ''),
                    "transaction_id": str(transaction.id),
                    "notchpay_reference": notchpay_reference
                })
            else:
                transaction.status = 'failed'
                transaction.payment_response = {'error': 'Réponse NotchPay invalide'}
                transaction.save()
                
                return Response({
                    "detail": _("Échec de l'initialisation du paiement."),
                    "error": "Réponse invalide du service de paiement"
                }, status=status.HTTP_400_BAD_REQUEST)
                    
        except Exception as e:
            transaction.status = 'failed'
            transaction.payment_response = {"error": str(e)}
            transaction.save()
            
            return Response({
                "detail": _("Une erreur est survenue lors de l'initialisation du paiement."),
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def check_payment_status(self, request, pk=None):
        """
        Vérifie le statut d'un paiement.
        GET /api/v1/bookings/{id}/check_payment_status/
        """
        from payments.services.notchpay_service import NotchPayService
        from payments.utils import NotchPayUtils, PaymentStatus
        import logging
        
        logger = logging.getLogger('findam')
        
        try:
            booking = self.get_object()
            logger.info(f"Vérification du statut de paiement pour la réservation {booking.id}")
            
            # Récupérer la dernière transaction
            transaction = booking.transactions.order_by('-created_at').first()
            
            if not transaction:
                logger.warning(f"Aucune transaction trouvée pour la réservation {booking.id}")
                return Response({
                    "status": "pending",
                    "booking_status": booking.status,
                    "payment_status": booking.payment_status,
                    "message": "Aucune transaction trouvée pour cette réservation."
                })
            
            # Si la transaction est déjà terminée ou a échoué, retourner son statut
            if transaction.status in ['completed', 'failed']:
                return Response({
                    "status": transaction.status,
                    "booking_status": booking.status,
                    "payment_status": booking.payment_status
                })
            
            # Récupérer la référence NotchPay
            notchpay_reference = transaction.transaction_id
            logger.info(f"Vérification du statut du paiement {notchpay_reference}")
            
            if not notchpay_reference:
                # Si pas de référence, retourner le statut en cours
                return Response({
                    "status": "processing",
                    "booking_status": booking.status,
                    "payment_status": booking.payment_status,
                    "message": "Transaction en cours de traitement, aucune référence disponible."
                })
            
            try:
                # Initialiser le service NotchPay
                notchpay_service = NotchPayService()
                
                # Vérifier le statut du paiement
                payment_data = notchpay_service.verify_payment(notchpay_reference)
                
                # Récupérer le statut NotchPay
                notchpay_status = payment_data.get('transaction', {}).get('status', 'pending')
                
                # Convertir le statut NotchPay en statut interne
                internal_status = NotchPayUtils.convert_notchpay_status(notchpay_status)
                
                # Mettre à jour le statut de la transaction
                transaction.status = internal_status
                transaction.payment_response = payment_data
                transaction.save(update_fields=['status', 'payment_response'])
                
                # Si le paiement est confirmé ou échoué, mettre à jour le statut de la réservation
                if internal_status == PaymentStatus.COMPLETED:
                    booking.payment_status = 'paid'
                    booking.save(update_fields=['payment_status'])
                elif internal_status == PaymentStatus.FAILED:
                    booking.payment_status = 'failed'
                    booking.save(update_fields=['payment_status'])
                
                return Response({
                    "status": internal_status,
                    "booking_status": booking.status,
                    "payment_status": booking.payment_status,
                    "details": payment_data.get('transaction', {})
                })
                
            except Exception as e:
                logger.exception(f"Erreur lors de la vérification du paiement: {str(e)}")
                return Response({
                    "status": "error",
                    "error": str(e),
                    "booking_status": booking.status,
                    "payment_status": booking.payment_status
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.exception(f"Erreur globale lors de la vérification du statut: {str(e)}")
            return Response({
                "status": "error",
                "error": "Une erreur interne est survenue lors de la vérification du statut du paiement.",
                "details": str(e)
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
        from payments.services.notchpay_service import NotchPayService
        from payments.utils import NotchPayUtils, PaymentStatus
        
        # Vérifier la signature de la requête pour sécuriser le callback
        signature = request.headers.get('X-Notch-Signature', '')
        payload = request.body
        
        # Initialiser le service NotchPay
        notchpay_service = NotchPayService()
        
        # Vérifier la signature
        if signature and not notchpay_service.verify_webhook_signature(payload.decode('utf-8'), signature):
            return Response({
                "detail": _("Signature non valide.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Récupérer les données de la transaction
        data = request.data
        
        # Log les données reçues pour le débogage
        self.logger.info(f"Callback de paiement reçu: {data}")
        
        # Vérifier le statut du paiement
        payment_status = data.get('data', {}).get('status')
        transaction_reference = data.get('data', {}).get('reference')
        merchant_reference = data.get('data', {}).get('merchant_reference', '')
        
        # Extraire l'ID de la réservation depuis la référence merchant si disponible
        booking_id = None
        if merchant_reference and merchant_reference.startswith('booking-'):
            parts = merchant_reference.split('-')
            if len(parts) > 1:
                booking_id = parts[1]
        
        # Si pas de booking_id dans la référence, essayer de le récupérer des métadonnées
        if not booking_id and 'metadata' in data.get('data', {}):
            metadata = data.get('data', {}).get('metadata', {})
            booking_id = metadata.get('object_id')
        
        try:
            # Récupérer la transaction
            transaction = None
            
            # Essayer de trouver la transaction par référence externe
            if transaction_reference:
                transaction = PaymentTransaction.objects.filter(
                    external_reference=transaction_reference
                ).first()
            
            # Si pas trouvé et booking_id existe, chercher par booking_id
            if not transaction and booking_id:
                transaction = PaymentTransaction.objects.filter(
                    booking__id=booking_id
                ).order_by('-created_at').first()
            
            # Si aucune transaction n'est trouvée, journaliser et retourner une erreur
            if not transaction:
                self.logger.error(f"Transaction non trouvée pour la référence {transaction_reference} ou booking {booking_id}")
                return Response({
                    "detail": _("Transaction non trouvée.")
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Mettre à jour la transaction avec les données de NotchPay
            transaction.payment_response = data
            
            # Convertir le statut NotchPay en statut interne
            internal_status = NotchPayUtils.convert_notchpay_status(payment_status)
            transaction.status = internal_status
            transaction.save()
            
            # Récupérer la réservation associée
            booking = transaction.booking
            
            # Mettre à jour le statut de paiement de la réservation
            if internal_status == PaymentStatus.COMPLETED:
                booking.payment_status = 'paid'
                booking.save(update_fields=['payment_status'])
                
                # Créer une transaction financière
                from payments.models import Transaction
                Transaction.objects.create(
                    user=booking.tenant,
                    transaction_type='payment',
                    status='completed',
                    amount=booking.total_price,
                    currency='XAF',
                    booking=booking,
                    payment_transaction=transaction,
                    external_reference=transaction_reference,
                    description=f"Paiement pour la réservation {booking.id}"
                )
                
                return Response({
                    "detail": _("Paiement réussi.")
                })
                
            elif internal_status == PaymentStatus.FAILED:
                booking.payment_status = 'failed'
                booking.save(update_fields=['payment_status'])
                
                return Response({
                    "detail": _("Paiement échoué.")
                })
                
            else:
                # Pour les autres statuts (pending, processing...)
                return Response({
                    "detail": _("Paiement en cours de traitement.")
                })
                    
        except Exception as e:
            self.logger.exception(f"Erreur lors du traitement du callback: {str(e)}")
            return Response({
                "detail": _("Une erreur est survenue lors du traitement du paiement."),
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    @action(detail=True, methods=['get'])
    def payment_status_escrow(self, request, pk=None):
        """
        Vérifie le statut du paiement et des versements programmés pour cette réservation.
        GET /api/v1/bookings/{id}/payment_status_escrow/
        """
        booking = self.get_object()
        
        # Vérifier que l'utilisateur est autorisé (propriétaire, locataire ou admin)
        if not (request.user.is_staff or request.user == booking.tenant or request.user == booking.property.owner):
            return Response({
                "detail": _("Vous n'êtes pas autorisé à accéder à ces informations.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            # Récupérer la dernière transaction de paiement
            payment_transaction = booking.transactions.order_by('-created_at').first()
            
            # Récupérer le versement programmé associé
            from payments.models import Payout
            payout = Payout.objects.filter(
                bookings__id=booking.id
            ).order_by('-created_at').first()
            
            # Préparer les informations sur le paiement
            payment_info = {
                "booking_status": booking.status,
                "payment_status": booking.payment_status,
                "transaction_id": str(payment_transaction.id) if payment_transaction else None,
                "transaction_status": payment_transaction.status if payment_transaction else None,
                "transaction_date": payment_transaction.created_at.isoformat() if payment_transaction and payment_transaction.created_at else None,
            }
            
            # Ajouter les informations sur le versement si disponible
            if payout:
                payment_info.update({
                    "payout_id": str(payout.id),
                    "payout_status": payout.status,
                    "payout_scheduled_at": payout.scheduled_at.isoformat() if payout.scheduled_at else None,
                    "payout_processed_at": payout.processed_at.isoformat() if payout.processed_at else None,
                    "payout_amount": float(payout.amount) if payout.amount else None,
                    "escrow_status": "in_escrow" if payout.status in ['pending', 'scheduled'] else "released" if payout.status == 'completed' else "processing"
                })
            else:
                payment_info.update({
                    "payout_id": None,
                    "payout_status": None,
                    "payout_scheduled_at": None,
                    "payout_processed_at": None,
                    "payout_amount": None,
                    "escrow_status": "not_scheduled" if booking.payment_status == 'paid' else "not_paid"
                })
            
            # Ajouter des informations spécifiques pour le propriétaire
            if request.user == booking.property.owner:
                payment_info.update({
                    "owner_message": _get_owner_escrow_message(booking, payout)
                })
            
            # Ajouter des informations spécifiques pour le locataire
            if request.user == booking.tenant:
                payment_info.update({
                    "tenant_message": _get_tenant_escrow_message(booking, payout)
                })
            
            return Response(payment_info)
            
        except Exception as e:
            return Response({
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Fonctions d'assistance pour les messages aux utilisateurs
    def _get_owner_escrow_message(booking, payout):
        """Génère un message explicatif sur le statut du versement pour le propriétaire."""
        if not payout:
            if booking.payment_status == 'paid':
                return _("Le paiement a été reçu. Le versement sera programmé après confirmation de l'arrivée du locataire.")
            else:
                return _("Le paiement n'a pas encore été effectué par le locataire.")
        
        if payout.status == 'pending':
            return _("Le paiement est en séquestre. Le versement sera programmé après confirmation de l'arrivée du locataire.")
        
        if payout.status == 'scheduled':
            scheduled_date = payout.scheduled_at.strftime('%d/%m/%Y') if payout.scheduled_at else "prochainement"
            return _("Le versement est programmé pour le {}. Les fonds seront disponibles après cette date.").format(scheduled_date)
        
        if payout.status == 'ready':
            return _("Le versement est en cours de traitement et sera effectué très prochainement.")
        
        if payout.status == 'processing':
            return _("Le versement est en cours de traitement par notre partenaire de paiement.")
        
        if payout.status == 'completed':
            processed_date = payout.processed_at.strftime('%d/%m/%Y') if payout.processed_at else "récemment"
            return _("Le versement a été effectué le {}. Les fonds devraient être disponibles sur votre compte.").format(processed_date)
        
        if payout.status == 'failed':
            return _("Le versement a échoué. Veuillez vérifier vos informations de paiement ou contacter notre service client.")
        
        if payout.status == 'cancelled':
            return _("Le versement a été annulé. Veuillez contacter notre service client pour plus d'informations.")
        
        return _("Le statut de votre versement est actuellement en révision.")

    def _get_tenant_escrow_message(booking, payout):
        """Génère un message explicatif sur le statut du paiement pour le locataire."""
        if booking.payment_status != 'paid':
            return _("Votre paiement n'a pas encore été confirmé. Veuillez vérifier le statut de votre transaction.")
        
        # Si payé mais pas de versement programmé
        if not payout:
            return _("Votre paiement a été reçu. Les fonds seront conservés en séquestre jusqu'à votre arrivée pour garantir la qualité du service.")
        
        # Si le versement est en séquestre
        if payout.status in ['pending', 'scheduled']:
            return _("Votre paiement a été reçu. Les fonds sont actuellement conservés en séquestre pour garantir la qualité du service.")
        
        # Si le versement est en cours
        if payout.status in ['ready', 'processing']:
            return _("Votre paiement a été reçu et confirmé. Le versement au propriétaire est en cours de traitement.")
        
        # Si le versement est terminé
        if payout.status == 'completed':
            return _("Votre paiement a été reçu et le versement au propriétaire a été effectué. Nous vous souhaitons un excellent séjour.")
        
        # Si le versement a échoué ou a été annulé
        if payout.status in ['failed', 'cancelled']:
            return _("Votre paiement a été reçu, mais il y a eu un problème avec le versement au propriétaire. Cela n'affecte pas votre réservation. Notre équipe s'en occupe.")
        
        return _("Votre paiement a été reçu et est actuellement en traitement.")

    # Ajouter cette nouvelle action au BookingViewSet existant
    @action(detail=True, methods=['post'])
    def complete_booking_and_release_funds(self, request, pk=None):
        """
        Marque une réservation comme terminée et déclenche le versement si ce n'est pas déjà fait.
        POST /api/v1/bookings/{id}/complete_booking_and_release_funds/
        """
        booking = self.get_object()
        
        # Vérifier que l'utilisateur est autorisé (admin ou propriétaire)
        if not (request.user.is_staff or request.user == booking.property.owner):
            return Response({
                "detail": _("Vous n'êtes pas autorisé à effectuer cette action.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que la réservation est confirmée
        if booking.status != 'confirmed':
            return Response({
                "detail": _("Seules les réservations confirmées peuvent être marquées comme terminées.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier que le paiement est effectué
        if booking.payment_status != 'paid':
            return Response({
                "detail": _("La réservation ne peut être marquée comme terminée que si le paiement est effectué.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Marquer la réservation comme terminée
            booking.status = 'completed'
            booking.save(update_fields=['status'])
            
            # Récupérer ou créer un versement programmé si nécessaire
            from payments.models import Payout
            from payments.services.payout_service import PayoutService
            
            # Vérifier si un versement existe déjà
            payout = Payout.objects.filter(
                bookings__id=booking.id,
                status__in=['pending', 'scheduled', 'ready', 'processing']
            ).first()
            
            # Si pas de versement, en programmer un
            if not payout:
                payout = PayoutService.schedule_payout_for_booking(booking)
            
            # Si le versement est programmé, le marquer comme prêt
            if payout and payout.status == 'scheduled':
                payout.mark_as_ready()
                payout.admin_notes += f"\nVersement marqué comme prêt suite à complétion de la réservation par {request.user.email}"
                payout.save(update_fields=['admin_notes'])
            
            return Response({
                "detail": _("Réservation marquée comme terminée et versement déclenché avec succès."),
                "booking_status": booking.status,
                "payout_status": payout.status if payout else None,
                "payout_id": str(payout.id) if payout else None
            })
        
        except Exception as e:
            return Response({
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def immediate_release(self, request, pk=None):
        """
        Déclenche un versement immédiat des fonds pour cette réservation (admin uniquement).
        POST /api/v1/bookings/{id}/immediate_release/
        """
        booking = self.get_object()
        
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "detail": _("Seuls les administrateurs peuvent déclencher un versement immédiat.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que la réservation est confirmée ou terminée
        if booking.status not in ['confirmed', 'completed']:
            return Response({
                "detail": _("Seules les réservations confirmées ou terminées peuvent faire l'objet d'un versement immédiat.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier que le paiement est effectué
        if booking.payment_status != 'paid':
            return Response({
                "detail": _("Le versement ne peut être effectué que si le paiement est reçu.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Récupérer les versements existants
            from payments.models import Payout
            
            # Vérifier si un versement existe déjà
            existing_payout = Payout.objects.filter(
                bookings__id=booking.id,
                status__in=['pending', 'scheduled', 'ready', 'processing']
            ).first()
            
            if existing_payout:
                # Si un versement existe, le marquer comme prêt
                existing_payout.mark_as_ready()
                existing_payout.admin_notes += f"\nVersement immédiat déclenché par admin {request.user.email}"
                existing_payout.save(update_fields=['admin_notes'])
                
                payout = existing_payout
            else:
                # Sinon, créer un nouveau versement immédiat
                from payments.services.payout_service import PayoutService
                payout = PayoutService.schedule_payout_for_booking(booking)
                
                if payout:
                    payout.mark_as_ready()
                    payout.admin_notes += f"\nVersement immédiat créé par admin {request.user.email}"
                    payout.save(update_fields=['admin_notes'])
            
            if not payout:
                return Response({
                    "detail": _("Impossible de créer un versement pour cette réservation.")
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Traiter immédiatement le versement (optionnel)
            from payments.tasks import process_ready_payouts
            process_ready_payouts()
            
            # Rafraîchir l'objet pour récupérer les dernières modifications
            payout.refresh_from_db()
            
            return Response({
                "detail": _("Versement immédiat déclenché avec succès."),
                "payout_id": str(payout.id),
                "payout_status": payout.status
            })
        
        except Exception as e:
            return Response({
                "detail": str(e)
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