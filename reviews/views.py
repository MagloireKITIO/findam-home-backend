# reviews/views.py
# Vues pour la gestion des avis et signalements

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from .models import Review, ReviewReply, ReportedReview
from .serializers import (
    ReviewSerializer,
    ReviewCreateSerializer,
    ReportedReviewSerializer,
    ReviewReplyCreateSerializer,
    ReviewReplySerializer,
    AdminReportReviewSerializer
)
from properties.permissions import IsOwnerOfProperty

class ReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les avis.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'comment', 'reviewer__email', 'reviewer__first_name', 'reviewer__last_name', 'property__title']
    filterset_fields = ['property', 'rating', 'is_verified_stay', 'is_public']
    ordering_fields = ['created_at', 'rating']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les requêtes en lecture seule : les avis publics
        - Pour les autres actions : restreint aux avis de l'utilisateur ou du propriétaire des logements
        """
        user = self.request.user
        
        if self.action in ['list', 'retrieve'] and not user.is_authenticated:
            # Pour les non authentifiés, uniquement les avis publics
            return Review.objects.filter(is_public=True).select_related(
                'property', 'reviewer', 'property__owner'
            ).prefetch_related('images', 'owner_reply')
        
        if user.is_staff:
            # Les admins voient tout
            return Review.objects.all().select_related(
                'property', 'reviewer', 'property__owner'
            ).prefetch_related('images', 'owner_reply')
        
        if user.is_owner:
            # Les propriétaires voient leurs avis et les avis publics sur leurs logements
            return Review.objects.filter(
                Q(reviewer=user) | Q(property__owner=user) | (Q(is_public=True) & ~Q(reviewer=user))
            ).select_related(
                'property', 'reviewer', 'property__owner'
            ).prefetch_related('images', 'owner_reply')
        
        # Les locataires voient leurs avis et les avis publics
        return Review.objects.filter(
            Q(reviewer=user) | Q(is_public=True)
        ).select_related(
            'property', 'reviewer', 'property__owner'
        ).prefetch_related('images', 'owner_reply')
    
    def get_serializer_class(self):
        """
        Retourne la classe de sérialiseur appropriée selon l'action.
        """
        if self.action == 'create':
            return ReviewCreateSerializer
        return ReviewSerializer
    
    def get_permissions(self):
        """
        Définit les permissions selon l'action.
        """
        if self.action in ['update', 'partial_update', 'destroy']:
            # Seul le créateur de l'avis peut le modifier/supprimer
            permission_classes = [permissions.IsAuthenticated]
        elif self.action == 'create':
            # Il faut être authentifié pour créer un avis
            permission_classes = [permissions.IsAuthenticated]
        else:
            # Les actions de lecture sont publiques
            permission_classes = [permissions.AllowAny]
        
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'utilisateur actuel comme auteur de l'avis.
        """
        serializer.save(reviewer=self.request.user)
    
    def perform_update(self, serializer):
        """
        Vérifie que l'utilisateur est bien l'auteur de l'avis.
        """
        if serializer.instance.reviewer != self.request.user and not self.request.user.is_staff:
            self.permission_denied(self.request, message="Vous ne pouvez modifier que vos propres avis.")
        serializer.save()
    
    def perform_destroy(self, instance):
        """
        Vérifie que l'utilisateur est bien l'auteur de l'avis avant suppression.
        """
        if instance.reviewer != self.request.user and not self.request.user.is_staff:
            self.permission_denied(self.request, message="Vous ne pouvez supprimer que vos propres avis.")
        instance.delete()
    
    @action(detail=False, methods=['get'])
    def my_reviews(self, request):
        """
        Récupère les avis créés par l'utilisateur connecté.
        GET /api/v1/reviews/reviews/my_reviews/
        """
        reviews = Review.objects.filter(reviewer=request.user).select_related(
            'property', 'property__owner'
        ).prefetch_related('images', 'owner_reply')
        
        page = self.paginate_queryset(reviews)
        if page is not None:
            serializer = ReviewSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = ReviewSerializer(reviews, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def property_reviews(self, request):
        """
        Récupère les avis pour un logement spécifique.
        GET /api/v1/reviews/reviews/property_reviews/?property_id={id}
        """
        property_id = request.query_params.get('property_id')
        
        if not property_id:
            return Response({
                "detail": "ID de logement requis."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Pour les non authentifiés ou non propriétaires, uniquement les avis publics
        if not request.user.is_authenticated or (request.user.is_owner and not self.is_property_owner(property_id, request.user)):
            reviews = Review.objects.filter(
                property_id=property_id,
                is_public=True
            ).select_related('reviewer').prefetch_related('images', 'owner_reply')
        else:
            # Pour le propriétaire du logement ou les admins, tous les avis
            reviews = Review.objects.filter(
                property_id=property_id
            ).select_related('reviewer').prefetch_related('images', 'owner_reply')
        
        page = self.paginate_queryset(reviews)
        if page is not None:
            serializer = ReviewSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = ReviewSerializer(reviews, many=True, context={'request': request})
        return Response(serializer.data)
    
    def is_property_owner(self, property_id, user):
        """Vérifie si l'utilisateur est le propriétaire du logement."""
        from properties.models import Property
        try:
            property_obj = Property.objects.get(id=property_id)
            return property_obj.owner == user
        except Property.DoesNotExist:
            return False


class ReviewReplyViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les réponses aux avis.
    """
    serializer_class = ReviewReplySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Retourne le queryset approprié.
        - Pour les administrateurs : toutes les réponses
        - Pour les autres : uniquement les réponses visibles
        """
        user = self.request.user
        
        if user.is_staff:
            return ReviewReply.objects.all().select_related('review', 'owner', 'review__property')
        
        if user.is_owner:
            # Les propriétaires voient leurs réponses
            return ReviewReply.objects.filter(
                Q(owner=user) | Q(review__property__owner=user)
            ).select_related('review', 'owner', 'review__property')
        
        # Les locataires voient les réponses aux avis publics
        return ReviewReply.objects.filter(
            review__is_public=True
        ).select_related('review', 'owner', 'review__property')
    
    def get_serializer_class(self):
        """
        Retourne la classe de sérialiseur appropriée selon l'action.
        """
        if self.action == 'create':
            return ReviewReplyCreateSerializer
        return ReviewReplySerializer
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'utilisateur actuel comme auteur de la réponse.
        """
        serializer.save(owner=self.request.user)
    
    def perform_update(self, serializer):
        """
        Vérifie que l'utilisateur est bien l'auteur de la réponse ou le propriétaire du logement.
        """
        if (serializer.instance.owner != self.request.user and 
            serializer.instance.review.property.owner != self.request.user and 
            not self.request.user.is_staff):
            self.permission_denied(self.request, message="Vous ne pouvez modifier que vos propres réponses.")
        serializer.save()
    
    def perform_destroy(self, instance):
        """
        Vérifie que l'utilisateur est bien l'auteur de la réponse avant suppression.
        """
        if (instance.owner != self.request.user and 
            instance.review.property.owner != self.request.user and 
            not self.request.user.is_staff):
            self.permission_denied(self.request, message="Vous ne pouvez supprimer que vos propres réponses.")
        instance.delete()


class ReportedReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les signalements d'avis.
    """
    serializer_class = ReportedReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les administrateurs : tous les signalements
        - Pour les autres : uniquement leurs signalements
        """
        user = self.request.user
        
        if user.is_staff:
            return ReportedReview.objects.all().select_related('review', 'reporter', 'review__property')
        
        # Pour les utilisateurs normaux, uniquement leurs signalements
        return ReportedReview.objects.filter(reporter=user).select_related('review', 'review__property')
    
    def perform_create(self, serializer):
        """
        Associe automatiquement l'utilisateur actuel comme auteur du signalement.
        """
        serializer.save(reporter=self.request.user)
    
    @action(detail=True, methods=['post'])
    def admin_review(self, request, pk=None):
        """
        Permet à un administrateur de traiter un signalement.
        POST /api/v1/reviews/reported-reviews/{id}/admin_review/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        reported_review = self.get_object()
        serializer = AdminReportReviewSerializer(reported_review, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                "detail": "Signalement traité avec succès.",
                "status": reported_review.get_status_display()
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """
        Récupère les signalements en attente (pour les administrateurs).
        GET /api/v1/reviews/reported-reviews/pending/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response({
                "detail": "Vous n'êtes pas autorisé à effectuer cette action."
            }, status=status.HTTP_403_FORBIDDEN)
        
        pending_reports = ReportedReview.objects.filter(status='pending').select_related(
            'review', 'reporter', 'review__property', 'review__reviewer'
        )
        
        page = self.paginate_queryset(pending_reports)
        if page is not None:
            serializer = ReportedReviewSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = ReportedReviewSerializer(pending_reports, many=True, context={'request': request})
        return Response(serializer.data)