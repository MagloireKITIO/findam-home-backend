# accounts/views.py
# Vues pour la gestion des utilisateurs, profils et abonnements

from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.shortcuts import get_object_or_404
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
    
    def get_object(self):
        return self.request.user.profile
    
    def update(self, request, *args, **kwargs):
        profile = self.get_object()
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        
        if serializer.is_valid():
            # Réinitialiser le statut de vérification si de nouveaux documents sont soumis
            if 'id_card_image' in request.data or 'selfie_image' in request.data:
                profile.verification_status = 'pending'
            
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
    def confirm_payment(self, request, pk=None):
        """Confirme le paiement d'un abonnement et active l'abonnement."""
        subscription = self.get_object()
        
        # Dans un cas réel, ici on vérifierait la preuve de paiement
        # Pour ce prototype, on active simplement l'abonnement
        
        subscription.status = 'active'
        if not subscription.end_date:
            subscription.end_date = subscription.calculate_end_date()
        subscription.save()
        
        return Response({
            "message": "Paiement confirmé. Votre abonnement est maintenant actif.",
            "subscription": OwnerSubscriptionSerializer(subscription).data
        }, status=status.HTTP_200_OK)
    
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

class PendingVerificationsView(generics.ListAPIView):
    """Vue pour que les administrateurs voient les demandes de vérification en attente."""
    
    serializer_class = UserDetailSerializer
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        return User.objects.filter(profile__verification_status='pending')