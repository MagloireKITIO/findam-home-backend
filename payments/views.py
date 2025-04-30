# payments/views.py
# Vues pour la gestion des paiements et versements

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from accounts.permissions import IsOwnerOfProfile, IsAdminUser
from .models import PaymentMethod, Transaction, Payout, Commission
from .serializers import (
    PaymentMethodSerializer,
    TransactionSerializer,
    PayoutSerializer,
    CommissionSerializer,
    PayoutCreateSerializer
)

class PaymentMethodViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les méthodes de paiement.
    """
    serializer_class = PaymentMethodSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : toutes les méthodes de paiement
        - Pour les autres : uniquement leurs méthodes de paiement
        """
        user = self.request.user
        
        if user.is_staff:
            return PaymentMethod.objects.all()
        
        # Pour les utilisateurs normaux, uniquement leurs méthodes de paiement
        return PaymentMethod.objects.filter(user=user)
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'utilisateur actuel à la méthode de paiement.
        """
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """
        Définit une méthode de paiement comme méthode par défaut.
        POST /api/v1/payments/payment-methods/{id}/set_default/
        """
        payment_method = self.get_object()
        
        # Vérifier que la méthode de paiement appartient à l'utilisateur
        if payment_method.user != request.user and not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Définir comme méthode par défaut
        payment_method.is_default = True
        payment_method.save()
        
        return Response({
            "detail": "Méthode de paiement définie comme méthode par défaut avec succès."
        })

class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour gérer les transactions (lecture seule).
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['transaction_type', 'status', 'booking']
    search_fields = ['description', 'external_reference']
    ordering_fields = ['created_at', 'processed_at', 'amount']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : toutes les transactions
        - Pour les autres : uniquement leurs transactions
        """
        user = self.request.user
        
        if user.is_staff:
            return Transaction.objects.all().select_related(
                'user', 'booking', 'booking__property', 'booking__tenant',
                'payment_transaction'
            )
        
        # Pour les utilisateurs normaux, uniquement leurs transactions
        return Transaction.objects.filter(user=user).select_related(
            'booking', 'booking__property', 'booking__tenant',
            'payment_transaction'
        )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Récupère un résumé des transactions de l'utilisateur.
        GET /api/v1/payments/transactions/summary/
        """
        user = request.user
        
        # Calculer les statistiques
        total_transactions = Transaction.objects.filter(user=user).count()
        total_amount = Transaction.objects.filter(
            user=user,
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Transactions par type
        transactions_by_type = {}
        for transaction_type, _ in Transaction.TRANSACTION_TYPE_CHOICES:
            count = Transaction.objects.filter(
                user=user,
                transaction_type=transaction_type
            ).count()
            amount = Transaction.objects.filter(
                user=user,
                transaction_type=transaction_type,
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            transactions_by_type[transaction_type] = {
                'count': count,
                'amount': amount
            }
        
        # Transactions par statut
        transactions_by_status = {}
        for status_type, _ in Transaction.STATUS_CHOICES:
            count = Transaction.objects.filter(
                user=user,
                status=status_type
            ).count()
            
            transactions_by_status[status_type] = {
                'count': count
            }
        
        return Response({
            'total_transactions': total_transactions,
            'total_amount': total_amount,
            'by_type': transactions_by_type,
            'by_status': transactions_by_status,
            'currency': 'XAF'  # Franc CFA
        })
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """
        Récupère les transactions récentes de l'utilisateur.
        GET /api/v1/payments/transactions/recent/
        """
        user = request.user
        
        # Récupérer les 10 dernières transactions
        recent_transactions = Transaction.objects.filter(
            user=user
        ).order_by('-created_at')[:10]
        
        serializer = TransactionSerializer(recent_transactions, many=True, context={'request': request})
        return Response(serializer.data)

class PayoutViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les versements.
    """
    serializer_class = PayoutSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['notes', 'external_reference']
    ordering_fields = ['created_at', 'processed_at', 'amount']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : tous les versements
        - Pour les autres : uniquement leurs versements
        """
        user = self.request.user
        
        if user.is_staff:
            return Payout.objects.all().select_related(
                'owner', 'payment_method', 'transaction'
            ).prefetch_related('bookings')
        
        # Pour les utilisateurs normaux, uniquement leurs versements
        return Payout.objects.filter(owner=user).select_related(
            'payment_method', 'transaction'
        ).prefetch_related('bookings')
    
    def get_serializer_class(self):
        """
        Retourne la classe de sérialiseur appropriée selon l'action.
        """
        if self.action == 'create' or self.action == 'create_payout':
            return PayoutCreateSerializer
        return PayoutSerializer
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'utilisateur actuel comme propriétaire du versement.
        """
        serializer.save(owner=self.request.user)
    
    @action(detail=False, methods=['post'])
    def create_payout(self, request):
        """
        Crée un nouveau versement pour un propriétaire.
        POST /api/v1/payments/payouts/create_payout/
        """
        serializer = PayoutCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            payout = serializer.save()
            return Response(
                PayoutSerializer(payout, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """
        Confirme un versement (pour les administrateurs).
        POST /api/v1/payments/payouts/{id}/confirm/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        payout = self.get_object()
        
        # Vérifier que le versement est en attente
        if payout.status != 'pending':
            return Response({
                "detail": "Seuls les versements en attente peuvent être confirmés."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Confirmer le versement
        payout.status = 'processing'
        payout.save(update_fields=['status'])
        
        # Créer une transaction correspondante
        transaction = Transaction.objects.create(
            user=payout.owner,
            transaction_type='payout',
            status='processing',
            amount=payout.amount,
            currency=payout.currency,
            description=f"Versement pour la période du {payout.period_start} au {payout.period_end}"
        )
        
        # Associer la transaction au versement
        payout.transaction = transaction
        payout.save(update_fields=['transaction'])
        
        return Response({
            "detail": "Versement confirmé avec succès."
        })
    
    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        """
        Marque un versement comme terminé (pour les administrateurs).
        POST /api/v1/payments/payouts/{id}/mark_completed/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        payout = self.get_object()
        
        # Vérifier que le versement est en cours de traitement
        if payout.status != 'processing':
            return Response({
                "detail": "Seuls les versements en cours de traitement peuvent être marqués comme terminés."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Marquer le versement comme terminé
        payout.mark_as_completed()
        
        return Response({
            "detail": "Versement marqué comme terminé avec succès."
        })
    
    @action(detail=True, methods=['post'])
    def mark_failed(self, request, pk=None):
        """
        Marque un versement comme échoué (pour les administrateurs).
        POST /api/v1/payments/payouts/{id}/mark_failed/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        payout = self.get_object()
        
        # Vérifier que le versement est en cours de traitement ou en attente
        if payout.status not in ['processing', 'pending']:
            return Response({
                "detail": "Seuls les versements en cours de traitement ou en attente peuvent être marqués comme échoués."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Marquer le versement comme échoué
        payout.status = 'failed'
        payout.save(update_fields=['status'])
        
        # Mettre à jour la transaction associée si elle existe
        if payout.transaction:
            payout.transaction.status = 'failed'
            payout.transaction.save(update_fields=['status'])
        
        return Response({
            "detail": "Versement marqué comme échoué avec succès."
        })
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """
        Récupère les versements en attente (pour les administrateurs).
        GET /api/v1/payments/payouts/pending/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Récupérer les versements en attente
        pending_payouts = Payout.objects.filter(status='pending').select_related(
            'owner', 'payment_method'
        ).prefetch_related('bookings')
        
        serializer = PayoutSerializer(pending_payouts, many=True, context={'request': request})
        return Response(serializer.data)

class CommissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour gérer les commissions (lecture seule).
    """
    serializer_class = CommissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['booking']
    ordering_fields = ['created_at', 'total_amount']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : toutes les commissions
        - Pour les propriétaires : les commissions sur leurs réservations
        - Pour les locataires : les commissions sur leurs réservations
        """
        user = self.request.user
        
        if user.is_staff:
            return Commission.objects.all().select_related(
                'booking', 'booking__property', 'booking__tenant',
                'transaction'
            )
        
        if user.is_owner:
            # Pour les propriétaires, uniquement les commissions sur leurs logements
            return Commission.objects.filter(
                booking__property__owner=user
            ).select_related(
                'booking', 'booking__property', 'booking__tenant',
                'transaction'
            )
        
        # Pour les locataires, uniquement les commissions sur leurs réservations
        return Commission.objects.filter(
            booking__tenant=user
        ).select_related(
            'booking', 'booking__property', 'transaction'
        )
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Récupère un résumé des commissions (pour les administrateurs).
        GET /api/v1/payments/commissions/summary/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Calculer les statistiques
        total_commissions = Commission.objects.count()
        total_amount = Commission.objects.aggregate(total=Sum('total_amount'))['total'] or 0
        owner_amount = Commission.objects.aggregate(total=Sum('owner_amount'))['total'] or 0
        tenant_amount = Commission.objects.aggregate(total=Sum('tenant_amount'))['total'] or 0
        
        # Commissions par mois (3 derniers mois)
        from django.db.models import Count, Sum
        from django.db.models.functions import TruncMonth
        
        commissions_by_month = Commission.objects.annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            count=Count('id'),
            total=Sum('total_amount')
        ).order_by('-month')[:3]
        
        return Response({
            'total_commissions': total_commissions,
            'total_amount': total_amount,
            'owner_amount': owner_amount,
            'tenant_amount': tenant_amount,
            'by_month': commissions_by_month,
            'currency': 'XAF'  # Franc CFA
        })
    
    @action(detail=False, methods=['get'])
    def calculate_for_booking(self, request):
        """
        Calcule la commission pour une réservation.
        GET /api/v1/payments/commissions/calculate_for_booking/?booking_id={id}
        """
        booking_id = request.query_params.get('booking_id')
        
        if not booking_id:
            return Response({
                "detail": "ID de réservation requis."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer la réservation
        from bookings.models import Booking
        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({
                "detail": "Réservation introuvable."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Vérifier les permissions
        if not request.user.is_staff and request.user != booking.property.owner and request.user != booking.tenant:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Calculer la commission
        commission = Commission.calculate_for_booking(booking)
        
        serializer = CommissionSerializer(commission, context={'request': request})
        return Response(serializer.data)