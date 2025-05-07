# accounts/views.py
# Vues pour la gestion des utilisateurs, profils et abonnements

from rest_framework import generics, permissions, status, viewsets
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.shortcuts import get_object_or_404
from payments.utils import NotchPayUtils, PaymentStatus
from payments.services.notchpay_service import NotchPayService

from .models import Profile, OwnerSubscription
from .serializers import (
    UserSerializer, 
    UserRegistrationSerializer, 
    PasswordChangeSerializer,
    ProfileUpdateSerializer,
    VerificationSerializer,
    OwnerSubscriptionSerializer,
    SubscriptionCreateSerializer,
    AdminVerificationSerializer,
    UserDetailSerializer
)
from .permissions import IsOwnerOrReadOnly, IsOwnerOfProfile, IsAdminUser

User = get_user_model()

class UserRegistrationView(generics.CreateAPIView):
    """Vue pour l'inscription des utilisateurs."""
    
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "user": UserSerializer(user, context=self.get_serializer_context()).data,
                "message": "Utilisateur créé avec succès. Veuillez vérifier votre email pour activer votre compte."
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(generics.RetrieveUpdateAPIView):
    """Vue pour récupérer et mettre à jour le profil de l'utilisateur actuel."""
    
    serializer_class = UserDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        user = self.get_object()
        user_serializer = UserSerializer(user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            
            # Mise à jour du profil
            profile_data = request.data.get('profile', {})
            if profile_data:
                profile_serializer = ProfileUpdateSerializer(user.profile, data=profile_data, partial=True)
                if profile_serializer.is_valid():
                    profile_serializer.save()
                else:
                    return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            return Response(UserDetailSerializer(user).data)
        return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordChangeView(APIView):
    """Vue pour changer le mot de passe."""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        if serializer.is_valid():
            # Vérifier l'ancien mot de passe
            if not request.user.check_password(serializer.validated_data['old_password']):
                return Response({"old_password": ["Mot de passe incorrect."]}, status=status.HTTP_400_BAD_REQUEST)
            
            # Définir le nouveau mot de passe
            request.user.set_password(serializer.validated_data['new_password'])
            request.user.save()
            return Response({"message": "Mot de passe changé avec succès."}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class IdentityVerificationView(generics.UpdateAPIView):
    """Vue pour soumettre les documents de vérification d'identité."""
    
    serializer_class = VerificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]  # Ajout des parsers
    
    def get_object(self):
        return self.request.user.profile
    
    def update(self, request, *args, **kwargs):
        profile = self.get_object()
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Documents de vérification soumis avec succès. Votre demande sera traitée sous peu."
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminVerificationView(generics.UpdateAPIView):
    """Vue pour que les administrateurs traitent les demandes de vérification."""
    
    serializer_class = AdminVerificationSerializer
    permission_classes = [IsAdminUser]
    
    def get_object(self):
        profile_id = self.kwargs.get('pk')
        return get_object_or_404(Profile, id=profile_id)
    
    def update(self, request, *args, **kwargs):
        profile = self.get_object()
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            
            # Mettre à jour le statut vérifié de l'utilisateur si le profil est vérifié
            if profile.verification_status == 'verified':
                profile.user.is_verified = True
                profile.user.save()
            
            return Response({
                "message": f"Statut de vérification mis à jour: {profile.get_verification_status_display()}"
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SubscriptionViewSet(viewsets.ModelViewSet):
    """ViewSet pour gérer les abonnements des propriétaires."""
    
    serializer_class = OwnerSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        """Filtre les abonnements pour ne montrer que ceux de l'utilisateur actuel."""
        if self.request.user.is_staff:
            return OwnerSubscription.objects.all()
        return OwnerSubscription.objects.filter(owner=self.request.user)
    
    def create(self, request, *args, **kwargs):
        """Crée un nouvel abonnement."""
        serializer = SubscriptionCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            subscription = serializer.save()
            return Response(
                OwnerSubscriptionSerializer(subscription).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Annule un abonnement."""
        subscription = self.get_object()
        
        # Vérifier que l'utilisateur est le propriétaire de l'abonnement
        if subscription.owner != request.user and not request.user.is_staff:
            return Response({
                "error": "Vous n'êtes pas autorisé à annuler cet abonnement."
            }, status=status.HTTP_403_FORBIDDEN)
        
        subscription.status = 'cancelled'
        subscription.save()
        
        return Response({
            "message": "Abonnement annulé avec succès."
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Récupère l'abonnement actif de l'utilisateur."""
        active_subscription = OwnerSubscription.objects.filter(
            owner=request.user, 
            status='active', 
            end_date__gt=timezone.now()
        ).first()
        
        if not active_subscription:
            return Response({
                "message": "Aucun abonnement actif trouvé."
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response(OwnerSubscriptionSerializer(active_subscription).data)
    
    @action(detail=True, methods=['post'])
    def initiate_payment(self, request, pk=None):
        """
        Initie le paiement d'un abonnement.
        POST /api/v1/accounts/subscriptions/{id}/initiate_payment/
        """
        subscription = self.get_object()
        
        # Vérifier que l'utilisateur est bien le propriétaire de l'abonnement
        if subscription.owner != request.user and not request.user.is_staff:
            return Response({
                "error": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier que l'abonnement est en attente de paiement
        if subscription.status != 'pending':
            return Response({
                "error": "Cet abonnement n'est pas en attente de paiement."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer la méthode de paiement
        payment_method = request.data.get('payment_method', 'mobile_money')
        
        # Récupérer l'opérateur mobile si fourni (orange, mtn, mobile_money)
        mobile_operator = request.data.get('mobile_operator', 'mobile_money')
        notchpay_channel = NotchPayUtils.get_mobile_operator_code(mobile_operator)
        
        # Récupérer et formater le numéro de téléphone pour mobile money
        phone_number = request.data.get('phone_number', '')
        formatted_phone = NotchPayUtils.format_phone_number(phone_number) if phone_number else NotchPayUtils.format_phone_number(request.user.phone_number)
        
        # Préparer les métadonnées pour NotchPay
        metadata = {
            'transaction_type': 'subscription',
            'object_id': str(subscription.id),
            'owner_id': str(subscription.owner.id),
            'subscription_type': subscription.subscription_type
        }
        
        # Préparer les informations client
        customer_info = {
            'email': subscription.owner.email,
            'phone': formatted_phone,
            'name': f"{subscription.owner.first_name} {subscription.owner.last_name}"
        }
        
        # Préparation de la description
        description = f"Abonnement {subscription.get_subscription_type_display()} - Findam"
        
        # Déterminer le prix selon le type d'abonnement
        subscription_prices = {
            'free': 0,
            'monthly': 5000,
            'quarterly': 12000,
            'yearly': 40000
        }
        amount = subscription_prices.get(subscription.subscription_type, 0)
        
        try:
            # Initialiser le service NotchPay
            notchpay_service = NotchPayService()
            
            # Référence unique pour le paiement
            payment_reference = f"sub-{subscription.id}-{int(timezone.now().timestamp())}"
            
            # Initialiser le paiement via NotchPay
            payment_result = notchpay_service.initialize_payment(
                amount=amount,
                currency='XAF',
                description=description,
                customer_info=customer_info,
                metadata=metadata,
                reference=payment_reference
            )
            
            # Mettre à jour la référence de paiement de l'abonnement
            if payment_result and 'transaction' in payment_result:
                subscription.payment_reference = payment_result['transaction'].get('reference', '')
                subscription.save(update_fields=['payment_reference'])
                
                # Retourner l'URL de paiement au client
                return Response({
                    "payment_url": payment_result.get('authorization_url', ''),
                    "notchpay_reference": payment_result['transaction'].get('reference', ''),
                    "subscription_id": str(subscription.id)
                })
            else:
                return Response({
                    "error": "Échec de l'initialisation du paiement."
                }, status=status.HTTP_400_BAD_REQUEST)
                    
        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Ajoutez la méthode check_payment_status à la classe SubscriptionViewSet:
    @action(detail=True, methods=['get'])
    def check_payment_status(self, request, pk=None):
        """
        Vérifie le statut d'un paiement pour un abonnement.
        GET /api/v1/accounts/subscriptions/{id}/check_payment_status/
        """
        subscription = self.get_object()

        if subscription.status == 'active':
            return Response({
                "status": "completed",
                "subscription_status": "active",
                "message": "L'abonnement est déjà actif"
            })
        
        # Vérifier que l'utilisateur est bien le propriétaire de l'abonnement
        if subscription.owner != request.user and not request.user.is_staff:
            return Response({
                "error": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Vérifier si nous avons une référence de paiement
        if not subscription.payment_reference:
            return Response({
                "status": "pending",
                "subscription_status": subscription.status,
                "message": "Aucune référence de paiement trouvée"
            })
        
        try:
            # Initialiser le service NotchPay
            notchpay_service = NotchPayService()
            
            # Vérifier le statut du paiement
            payment_data = notchpay_service.verify_payment(subscription.payment_reference)
            
            # Récupérer le statut NotchPay
            notchpay_status = payment_data.get('transaction', {}).get('status', 'pending')
            
            # Convertir le statut NotchPay en statut interne
            internal_status = NotchPayUtils.convert_notchpay_status(notchpay_status)
            
            # Si le paiement est confirmé et que l'abonnement est en attente, l'activer
            if internal_status == 'completed' and subscription.status == 'pending':
                subscription.status = 'active'
                
                # Calculer la date de fin si ce n'est pas un abonnement gratuit
                if subscription.subscription_type != 'free' and not subscription.end_date:
                    subscription.end_date = subscription.calculate_end_date()
                    
                subscription.save(update_fields=['status', 'end_date'])
                
                # Ici, vous pourriez créer une transaction financière pour garder une trace du paiement
                from payments.models import Transaction
                Transaction.objects.create(
                    user=subscription.owner,
                    transaction_type='subscription',
                    status='completed',
                    amount=subscription.calculate_price(),
                    currency='XAF',
                    external_reference=subscription.payment_reference,
                    description=f"Paiement de l'abonnement {subscription.get_subscription_type_display()}"
                )
            
            return Response({
                "status": internal_status,
                "subscription_status": subscription.status,
                "details": payment_data.get('transaction', {})
            })
            
        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Ajoutez également cette méthode pour que les administrateurs confirment manuellement un paiement si nécessaire
    @action(detail=True, methods=['post'])
    def confirm_payment(self, request, pk=None):
        """
        Confirmation manuelle du paiement par un administrateur.
        POST /api/v1/accounts/subscriptions/{id}/confirm_payment/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "error": "Seuls les administrateurs peuvent confirmer manuellement un paiement."
            }, status=status.HTTP_403_FORBIDDEN)
        
        subscription = self.get_object()
        
        # Vérifier que l'abonnement est en attente
        if subscription.status != 'pending':
            return Response({
                "error": "Seuls les abonnements en attente peuvent être confirmés."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Activer l'abonnement
        subscription.status = 'active'
        
        # Calculer la date de fin si ce n'est pas un abonnement gratuit
        if subscription.subscription_type != 'free' and not subscription.end_date:
            subscription.end_date = subscription.calculate_end_date()
        
        subscription.save(update_fields=['status', 'end_date'])
        
        # Créer une trace du paiement
        from payments.models import Transaction
        Transaction.objects.create(
            user=subscription.owner,
            transaction_type='subscription',
            status='completed',
            amount=subscription.calculate_price(),
            currency='XAF',
            description=f"Paiement de l'abonnement {subscription.get_subscription_type_display()} (confirmation manuelle)"
        )
        
        return Response({
            "message": "Paiement confirmé avec succès.",
            "subscription": OwnerSubscriptionSerializer(subscription).data
        }, status=status.HTTP_200_OK)


class PendingVerificationsView(generics.ListAPIView):
    """Vue pour que les administrateurs voient les demandes de vérification en attente."""
    
    serializer_class = UserDetailSerializer
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        return User.objects.filter(profile__verification_status='pending')