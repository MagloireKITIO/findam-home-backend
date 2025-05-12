# payments/views.py
# Vues pour la gestion des paiements et versements

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from accounts.permissions import IsOwnerOfProfile, IsAdminUser
from bookings.models import Booking
from .models import PaymentMethod, Transaction, Payout, Commission
from .serializers import (
    PaymentMethodSerializer,
    TransactionSerializer,
    PayoutSerializer,
    CommissionSerializer,
    PaymentMethodCreateSerializer,
    PaymentMethodDetailSerializer
)
from django.utils.translation import gettext as _


class PaymentMethodViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les méthodes de paiement avec activation et vérification.
    """
    serializer_class = PaymentMethodSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nickname', 'phone_number']
    ordering_fields = ['created_at', 'is_active', 'status']
    ordering = ['-is_active', '-created_at']
    
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
    
    def get_serializer_class(self):
        """Retourne la classe de sérialiseur appropriée selon l'action"""
        if self.action == 'create':
            return PaymentMethodCreateSerializer
        elif self.action in ['retrieve', 'list']:
            return PaymentMethodDetailSerializer
        return PaymentMethodSerializer
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'utilisateur actuel à la méthode de paiement.
        """
        payment_method = serializer.save(user=self.request.user)
        
        # Démarrer automatiquement la vérification
        payment_method.verify_with_notchpay()
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """
        Récupère la méthode de paiement active de l'utilisateur.
        GET /api/v1/payments/payment-methods/active/
        """
        active_method = PaymentMethod.get_active_for_user(request.user)
        
        if not active_method:
            return Response({
                "detail": "Aucune méthode de paiement active trouvée."
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = PaymentMethodDetailSerializer(active_method, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def verified(self, request):
        """
        Récupère toutes les méthodes de paiement vérifiées de l'utilisateur.
        GET /api/v1/payments/payment-methods/verified/
        """
        verified_methods = PaymentMethod.get_verified_for_user(request.user)
        serializer = PaymentMethodDetailSerializer(verified_methods, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        Active une méthode de paiement.
        POST /api/v1/payments/payment-methods/{id}/activate/
        """
        payment_method = self.get_object()
        
        # Vérifier que la méthode de paiement appartient à l'utilisateur
        if payment_method.user != request.user and not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            payment_method.activate(user=request.user)
            return Response({
                "detail": "Méthode de paiement activée avec succès.",
                "is_active": True
            })
        except ValueError as e:
            return Response({
                "detail": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """
        Désactive une méthode de paiement.
        POST /api/v1/payments/payment-methods/{id}/deactivate/
        """
        payment_method = self.get_object()
        
        # Vérifier que la méthode de paiement appartient à l'utilisateur
        if payment_method.user != request.user and not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        payment_method.deactivate(user=request.user)
        return Response({
            "detail": "Méthode de paiement désactivée avec succès.",
            "is_active": False
        })
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """
        Déclenche une nouvelle vérification de la méthode de paiement.
        POST /api/v1/payments/payment-methods/{id}/verify/
        """
        payment_method = self.get_object()
        
        # Vérifier que la méthode de paiement appartient à l'utilisateur
        if payment_method.user != request.user and not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Limiter les tentatives de vérification
        if payment_method.verification_attempts >= 3:
            return Response({
                "detail": "Nombre maximum de tentatives de vérification atteint. Contactez le support."
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        # Déclencher la vérification
        success = payment_method.verify_with_notchpay()
        
        serializer = PaymentMethodDetailSerializer(payment_method, context={'request': request})
        
        return Response({
            "detail": "Vérification réussie" if success else "Échec de la vérification",
            "verification_success": success,
            "payment_method": serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """
        Définit une méthode de paiement comme méthode par défaut.
        POST /api/v1/payments/payment-methods/{id}/set_default/
        
        Note: Cette action est différente d'activate. 
        Une méthode par défaut est privilégiée lors de la sélection,
        mais seule la méthode active sera utilisée pour les transactions.
        """
        payment_method = self.get_object()
        
        # Vérifier que la méthode de paiement appartient à l'utilisateur
        if payment_method.user != request.user and not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Retirer le statut par défaut des autres méthodes
        PaymentMethod.objects.filter(
            user=request.user,
            is_default=True
        ).exclude(id=payment_method.id).update(is_default=False)
        
        # Définir comme méthode par défaut
        payment_method.is_default = True
        payment_method.save(update_fields=['is_default'])
        
        return Response({
            "detail": "Méthode de paiement définie comme méthode par défaut avec succès."
        })
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Récupère un résumé des méthodes de paiement de l'utilisateur.
        GET /api/v1/payments/payment-methods/summary/
        """
        user = request.user
        
        # Compter les méthodes par statut
        total_methods = PaymentMethod.objects.filter(user=user).count()
        verified_methods = PaymentMethod.objects.filter(user=user, status='verified').count()
        pending_methods = PaymentMethod.objects.filter(user=user, status='pending').count()
        failed_methods = PaymentMethod.objects.filter(user=user, status='failed').count()
        
        # Compter les méthodes par type
        mobile_money_count = PaymentMethod.objects.filter(
            user=user, 
            payment_type='mobile_money',
            status='verified'
        ).count()
        bank_account_count = PaymentMethod.objects.filter(
            user=user, 
            payment_type='bank_account',
            status='verified'
        ).count()
        
        # Méthode active
        active_method = PaymentMethod.get_active_for_user(user)
        
        return Response({
            'total_methods': total_methods,
            'verified_methods': verified_methods,
            'pending_methods': pending_methods,
            'failed_methods': failed_methods,
            'mobile_money_count': mobile_money_count,
            'bank_account_count': bank_account_count,
            'has_active_method': active_method is not None,
            'active_method': PaymentMethodDetailSerializer(active_method, context={'request': request}).data if active_method else None
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def bulk_verify(self, request):
        """
        Vérification en lot pour les administrateurs.
        POST /api/v1/payments/payment-methods/bulk_verify/
        """
        method_ids = request.data.get('method_ids', [])
        
        if not method_ids:
            return Response({
                "detail": "Aucun ID de méthode fourni."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        methods = PaymentMethod.objects.filter(id__in=method_ids)
        results = []
        
        for method in methods:
            success = method.verify_with_notchpay()
            results.append({
                'id': method.id,
                'success': success,
                'status': method.status
            })
        
        return Response({
            'results': results,
            'success_count': sum(1 for r in results if r['success']),
            'total_count': len(results)
        })
    
    def destroy(self, request, *args, **kwargs):
        """
        Supprime une méthode de paiement avec vérifications de sécurité.
        """
        payment_method = self.get_object()
        
        # Vérifier que la méthode de paiement appartient à l'utilisateur
        if payment_method.user != request.user and not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier s'il y a des transactions en cours utilisant cette méthode
        pending_payouts = Payout.objects.filter(
            payment_method=payment_method,
            status__in=['pending', 'scheduled', 'ready', 'processing']
        )
        
        if pending_payouts.exists():
            return Response({
                "detail": "Impossible de supprimer cette méthode. Des versements sont en cours avec cette méthode."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Si c'est la méthode active, proposer de la remplacer
        if payment_method.is_active:
            other_verified = PaymentMethod.objects.filter(
                user=payment_method.user,
                status='verified'
            ).exclude(id=payment_method.id).first()
            
            if other_verified:
                other_verified.activate()
                return Response({
                    "detail": f"Méthode supprimée. {other_verified} a été activée automatiquement."
                })
        
        payment_method.delete()
        return Response({
            "detail": "Méthode de paiement supprimée avec succès."
        })
    
    @action(detail=True, methods=['get'])
    def verify_status(self, request, pk=None):
        """
        Vérifie le statut d'une méthode de paiement dans NotchPay.
        GET /api/v1/payments/payment-methods/{id}/verify_status/
        """
        payment_method = self.get_object()
        
        # Vérifier que la méthode de paiement appartient à l'utilisateur
        if payment_method.user != request.user and not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Si on a un ID destinataire NotchPay, vérifier son statut
        if payment_method.notchpay_recipient_id:
            try:
                from .services.notchpay_service import NotchPayService
                notchpay_service = NotchPayService()
                
                # Récupérer les informations du destinataire depuis NotchPay
                # Note: Cette méthode pourrait ne pas exister dans l'API NotchPay
                # À adapter selon la documentation
                
                return Response({
                    "status": payment_method.status,
                    "is_active": payment_method.is_active,
                    "notchpay_recipient_id": payment_method.notchpay_recipient_id,
                    "verification_attempts": payment_method.verification_attempts,
                    "last_verification_at": payment_method.last_verification_at
                })
            except Exception as e:
                return Response({
                    "detail": f"Erreur lors de la vérification du statut: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            "status": payment_method.status,
            "is_active": payment_method.is_active,
            "notification": "Aucun ID destinataire NotchPay trouvé"
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
    
    @action(detail=True, methods=['post'])
    def schedule(self, request, pk=None):
        """
        Programme un versement pour une date future.
        POST /api/v1/payments/payouts/{id}/schedule/
        """
        payout = self.get_object()
        
        # Vérifier les permissions
        if payout.owner != request.user and not request.user.is_staff:
            return Response({
                "detail": _("Vous n'êtes pas autorisé à programmer ce versement.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que le versement est en attente ou annulé
        if payout.status not in ['pending', 'cancelled']:
            return Response({
                "detail": _("Seuls les versements en attente ou annulés peuvent être programmés.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer la date programmée
        scheduled_date = request.data.get('scheduled_date')
        if not scheduled_date:
            return Response({
                "detail": _("Date de programmation requise.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Convertir la date string en objet datetime
            scheduled_date = timezone.datetime.fromisoformat(scheduled_date.replace('Z', '+00:00'))
            
            # Vérifier que la date est future
            if scheduled_date <= timezone.now():
                return Response({
                    "detail": _("La date de programmation doit être future.")
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Programmer le versement
            payout.schedule(scheduled_date)
            
            # Ajouter une note pour suivre l'action
            payout.admin_notes += f"\nVersement programmé pour le {scheduled_date.strftime('%Y-%m-%d %H:%M')} par {request.user.email}"
            payout.save(update_fields=['admin_notes'])
            
            return Response({
                "detail": _("Versement programmé avec succès."),
                "scheduled_date": scheduled_date.isoformat()
            })
            
        except (ValueError, TypeError):
            return Response({
                "detail": _("Format de date invalide. Utilisez ISO 8601 (e.g. 2023-04-25T14:30:00Z).")
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def cancel_schedule(self, request, pk=None):
        """
        Annule la programmation d'un versement.
        POST /api/v1/payments/payouts/{id}/cancel_schedule/
        """
        payout = self.get_object()
        
        # Vérifier les permissions
        if not request.user.is_staff:
            return Response({
                "detail": _("Seuls les administrateurs peuvent annuler la programmation d'un versement.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que le versement est programmé ou prêt
        if payout.status not in ['scheduled', 'ready']:
            return Response({
                "detail": _("Seuls les versements programmés ou prêts peuvent être annulés.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer la raison
        reason = request.data.get('reason', '')
        
        # Annuler le versement
        payout.cancel(cancelled_by=request.user, reason=reason)
        
        return Response({
            "detail": _("Programmation du versement annulée avec succès.")
        })

    @action(detail=True, methods=['post'])
    def mark_ready(self, request, pk=None):
        """
        Marque un versement programmé comme prêt à être traité.
        POST /api/v1/payments/payouts/{id}/mark_ready/
        """
        payout = self.get_object()
        
        # Vérifier les permissions
        if not request.user.is_staff:
            return Response({
                "detail": _("Seuls les administrateurs peuvent marquer un versement comme prêt.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que le versement est programmé
        if payout.status != 'scheduled':
            return Response({
                "detail": _("Seuls les versements programmés peuvent être marqués comme prêts.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Marquer comme prêt
        payout.mark_as_ready()
        
        # Ajouter une note pour suivre l'action
        payout.admin_notes += f"\nVersement marqué comme prêt par {request.user.email} le {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        payout.save(update_fields=['admin_notes'])
        
        return Response({
            "detail": _("Versement marqué comme prêt à être traité.")
        })

    @action(detail=False, methods=['get'])
    def scheduled(self, request):
        """
        Liste tous les versements programmés.
        GET /api/v1/payments/payouts/scheduled/
        """
        # Vérifier les permissions
        if not request.user.is_staff:
            return Response({
                "detail": _("Seuls les administrateurs peuvent voir tous les versements programmés.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Récupérer les versements programmés
        scheduled_payouts = Payout.objects.filter(status='scheduled').select_related(
            'owner', 'payment_method'
        ).prefetch_related('bookings')
        
        # Filtrer par date programmée si spécifiée
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        
        if from_date:
            try:
                from_datetime = timezone.datetime.fromisoformat(from_date.replace('Z', '+00:00'))
                scheduled_payouts = scheduled_payouts.filter(scheduled_at__gte=from_datetime)
            except (ValueError, TypeError):
                pass
        
        if to_date:
            try:
                to_datetime = timezone.datetime.fromisoformat(to_date.replace('Z', '+00:00'))
                scheduled_payouts = scheduled_payouts.filter(scheduled_at__lte=to_datetime)
            except (ValueError, TypeError):
                pass
        
        # Sérialiser et retourner les résultats
        paginator = self.paginator
        page = paginator.paginate_queryset(scheduled_payouts, request)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(scheduled_payouts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def ready(self, request):
        """
        Liste tous les versements prêts à être traités.
        GET /api/v1/payments/payouts/ready/
        """
        # Vérifier les permissions
        if not request.user.is_staff:
            return Response({
                "detail": _("Seuls les administrateurs peuvent voir tous les versements prêts.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Récupérer les versements prêts
        ready_payouts = Payout.objects.filter(status='ready').select_related(
            'owner', 'payment_method'
        ).prefetch_related('bookings')
        
        # Sérialiser et retourner les résultats
        paginator = self.paginator
        page = paginator.paginate_queryset(ready_payouts, request)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(ready_payouts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def process_scheduled(self, request):
        """
        Traite tous les versements programmés qui sont maintenant dus.
        POST /api/v1/payments/payouts/process_scheduled/
        """
        # Vérifier les permissions
        if not request.user.is_staff:
            return Response({
                "detail": _("Seuls les administrateurs peuvent traiter les versements programmés.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Appeler la tâche de traitement
        from .tasks import process_scheduled_payouts
        count = process_scheduled_payouts()
        
        return Response({
            "detail": _("Traitement des versements programmés terminé."),
            "count": count
        })

    @action(detail=False, methods=['post'])
    def process_ready(self, request):
        """
        Traite tous les versements prêts à être versés.
        POST /api/v1/payments/payouts/process_ready/
        """
        # Vérifier les permissions
        if not request.user.is_staff:
            return Response({
                "detail": _("Seuls les administrateurs peuvent traiter les versements prêts.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Appeler la tâche de traitement
        from .tasks import process_ready_payouts
        result = process_ready_payouts()
        
        return Response({
            "detail": _("Traitement des versements prêts terminé."),
            "success": result.get('success', 0),
            "failed": result.get('failed', 0),
            "total": result.get('total', 0)
        })

    @action(detail=False, methods=['post'])
    def schedule_for_booking(self, request):
        """
        Programme un versement pour une réservation spécifique.
        POST /api/v1/payments/payouts/schedule_for_booking/
        """
        # Vérifier les permissions
        if not request.user.is_staff:
            return Response({
                "detail": _("Seuls les administrateurs peuvent programmer un versement pour une réservation.")
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Récupérer l'ID de la réservation
        booking_id = request.data.get('booking_id')
        if not booking_id:
            return Response({
                "detail": _("ID de réservation requis.")
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer la date programmée
        scheduled_date = request.data.get('scheduled_date')
        
        try:
            # Récupérer la réservation
            booking = Booking.objects.get(id=booking_id)
            
            # Vérifier que la réservation est confirmée et payée
            if booking.status != 'confirmed' or booking.payment_status != 'paid':
                return Response({
                    "detail": _("La réservation doit être confirmée et payée pour programmer un versement.")
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Convertir la date programmée si fournie
            scheduled_datetime = None
            if scheduled_date:
                scheduled_datetime = timezone.datetime.fromisoformat(scheduled_date.replace('Z', '+00:00'))
            
            # Programmer le versement
            from .services.payout_service import PayoutService
            payout = PayoutService.schedule_payout_for_booking(booking, scheduled_date=scheduled_datetime)
            
            if not payout:
                return Response({
                    "detail": _("Impossible de programmer le versement pour cette réservation.")
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                "detail": _("Versement programmé avec succès."),
                "payout_id": payout.id,
                "scheduled_date": payout.scheduled_at.isoformat() if payout.scheduled_at else None
            })
            
        except Booking.DoesNotExist:
            return Response({
                "detail": _("Réservation introuvable.")
            }, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError):
            return Response({
                "detail": _("Format de date invalide. Utilisez ISO 8601 (e.g. 2023-04-25T14:30:00Z).")
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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