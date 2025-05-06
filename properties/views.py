# properties/views.py
# Vues pour la gestion des logements et leurs caractéristiques

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Prefetch
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime
from .models import (
    Amenity,
    City,
    Neighborhood,
    Property,
    PropertyImage,
    Availability,
    LongStayDiscount
)
from .serializers import (
    AmenitySerializer,
    CitySerializer,
    NeighborhoodSerializer,
    PropertyListSerializer,
    PropertyDetailSerializer,
    PropertyCreateSerializer,
    PropertyImageSerializer,
    AvailabilitySerializer,
    LongStayDiscountSerializer,
    PropertyAvailabilityCheckSerializer,
    ExternalBookingSerializer
)
from .permissions import IsOwnerOrReadOnly, IsOwnerOfProperty, IsVerifiedOwner
from .filters import PropertyFilter

class AmenityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour afficher les équipements disponibles.
    GET /api/v1/properties/amenities/ - Liste tous les équipements
    GET /api/v1/properties/amenities/{id}/ - Détail d'un équipement
    """
    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['name', 'category']
    filterset_fields = ['category']

class CityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour afficher les villes disponibles.
    GET /api/v1/properties/cities/ - Liste toutes les villes
    GET /api/v1/properties/cities/{id}/ - Détail d'une ville
    """
    queryset = City.objects.all()
    serializer_class = CitySerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

class NeighborhoodViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour afficher les quartiers disponibles.
    GET /api/v1/properties/neighborhoods/ - Liste tous les quartiers
    GET /api/v1/properties/neighborhoods/{id}/ - Détail d'un quartier
    GET /api/v1/properties/neighborhoods/?city={city_id} - Filtre par ville
    """
    queryset = Neighborhood.objects.all()
    serializer_class = NeighborhoodSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['name']
    filterset_fields = ['city']

class PropertyViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les logements.
    """
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PropertyFilter
    search_fields = ['title', 'description', 'city__name', 'neighborhood__name']
    ordering_fields = ['price_per_night', 'created_at', 'avg_rating']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Retourne le queryset approprié selon le contexte.
        - Pour les actions de liste ou de détail, précharge les relations.
        - Pour les propriétaires, inclut leurs propres logements non publiés.
        - Pour les autres, uniquement les logements publiés et vérifiés.
        """
        queryset = Property.objects.all()
        
        # Ajouter les préchargements pour optimiser les requêtes
        if self.action in ['list', 'retrieve']:
            queryset = queryset.select_related('city', 'neighborhood', 'owner')
            
            # Pour le détail, précharger plus de relations
            if self.action == 'retrieve':
                queryset = queryset.prefetch_related(
                    'amenities',
                    'images',
                    'long_stay_discounts',
                    Prefetch('unavailabilities', queryset=Availability.objects.filter(
                        end_date__gte=timezone.now()
                    ))
                )
        
        # Filtrer selon le contexte d'utilisateur
        user = self.request.user
        
        # Les propriétaires voient tous leurs logements
        if user.is_authenticated and (user.is_owner or user.is_staff):
            if not user.is_staff and self.action == 'list':
                queryset = queryset.filter(owner=user)
        # Les autres ne voient que les logements publiés et vérifiés
        else:
            queryset = queryset.filter(is_published=True, is_verified=True)
        
        return queryset
    
    def get_serializer_class(self):
        """
        Retourne la classe de sérialiseur appropriée selon l'action.
        """
        if self.action == 'list':
            return PropertyListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return PropertyCreateSerializer
        else:
            return PropertyDetailSerializer
    
    def get_permissions(self):
        """
        Définit les permissions selon l'action.
        """
        if self.action in ['create']:
            permission_classes = [permissions.IsAuthenticated, IsVerifiedOwner]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOfProperty]
        elif self.action in ['my_properties']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            # IMPORTANT: Actions list et retrieve sont publiques
            permission_classes = [permissions.AllowAny]
        
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """
        Associe automatiquement le propriétaire à la création d'un logement.
        """
        serializer.save(owner=self.request.user)
    
    @action(detail=False, methods=['get'])
    def my_properties(self, request):
        """
        Liste les logements du propriétaire connecté.
        GET /api/v1/properties/my-properties/
        """
        queryset = Property.objects.filter(owner=request.user).select_related(
            'city', 'neighborhood'
        ).prefetch_related('images')
        
        serializer = PropertyListSerializer(
            queryset, many=True, context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """
        Publie ou dépublie un logement.
        POST /api/v1/properties/{id}/publish/
        """
        property_obj = self.get_object()
        
        # Vérifier que l'utilisateur est le propriétaire
        if property_obj.owner != request.user and not request.user.is_staff:
            return Response(
                {"detail": "Vous n'êtes pas autorisé à effectuer cette action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Vérifier si des images sont présentes
        if not property_obj.images.exists():
            return Response(
                {"detail": "Vous devez ajouter au moins une image avant de publier."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Inverser l'état de publication
        property_obj.is_published = True
        property_obj.save(update_fields=['is_published'])
        
        action = "publié" if property_obj.is_published else "dépublié"
        return Response({"detail": f"Le logement a été {action} avec succès."})
    
    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """
        Dépublie un logement.
        POST /api/v1/properties/{id}/unpublish/
        """
        property_obj = self.get_object()
        
        # Vérifier que l'utilisateur est le propriétaire
        if property_obj.owner != request.user and not request.user.is_staff:
            return Response(
                {"detail": "Vous n'êtes pas autorisé à effectuer cette action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        property_obj.is_published = False
        property_obj.save(update_fields=['is_published'])
        
        return Response({"detail": "Le logement a été dépublié avec succès."})
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """
        Vérifie ou dévérifie un logement (réservé aux administrateurs).
        POST /api/v1/properties/{id}/verify/
        """
        # Vérifier que l'utilisateur est un administrateur
        if not request.user.is_staff:
            return Response(
                {"detail": "Seuls les administrateurs peuvent vérifier les logements."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        property_obj = self.get_object()
        
        # Inverser l'état de vérification
        property_obj.is_verified = not property_obj.is_verified
        property_obj.save(update_fields=['is_verified'])
        
        action = "vérifié" if property_obj.is_verified else "non vérifié"
        return Response({"detail": f"Le logement est maintenant {action}."})
    
    @action(detail=True, methods=['get'])
    def check_availability(self, request, pk=None):
        """
        Vérifie la disponibilité d'un logement pour des dates données.
        GET /api/v1/properties/{id}/check-availability/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
        """
        property_obj = self.get_object()
        
        # Valider les dates
        serializer = PropertyAvailabilityCheckSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        start_date = serializer.validated_data['start_date']
        end_date = serializer.validated_data['end_date']
        
        # Vérifier s'il y a des indisponibilités qui chevauchent la période
        unavailabilities = property_obj.unavailabilities.filter(
            Q(start_date__lte=end_date) & Q(end_date__gte=start_date)
        )
        
        is_available = not unavailabilities.exists()
        
        # Calculer le prix total pour la période
        days = (end_date - start_date).days
        total_price = property_obj.calculate_price_for_days(days)
        
        # Ajouter les frais de ménage
        if property_obj.cleaning_fee:
            total_price += property_obj.cleaning_fee
        
        return Response({
            "available": is_available,
            "property_id": property_obj.id,
            "start_date": start_date,
            "end_date": end_date,
            "nights": days,
            "base_price": total_price,
            "cleaning_fee": property_obj.cleaning_fee,
            "security_deposit": property_obj.security_deposit,
            "total_price": total_price + property_obj.security_deposit,
            "unavailable_dates": list(unavailabilities.values('start_date', 'end_date', 'booking_type')) if unavailabilities.exists() else []
        })
    
    @action(detail=True, methods=['post'])
    def add_external_booking(self, request, pk=None):
        """
        Ajoute une réservation externe (hors application) pour un logement.
        POST /api/v1/properties/{id}/add-external-booking/
        """
        property_obj = self.get_object()
        
        # Vérifier que l'utilisateur est le propriétaire
        if property_obj.owner != request.user and not request.user.is_staff:
            return Response(
                {"detail": "Vous n'êtes pas autorisé à effectuer cette action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ExternalBookingSerializer(
            data=request.data,
            context={'property_id': property_obj.id}
        )
        
        if serializer.is_valid():
            availability = serializer.save()
            return Response({
                "detail": "Réservation externe ajoutée avec succès.",
                "start_date": availability.start_date,
                "end_date": availability.end_date,
                "client_name": availability.external_client_name
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
class PropertyImageViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les images des logements.
    """
    serializer_class = PropertyImageSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOfProperty]
    
    def get_queryset(self):
        return PropertyImage.objects.filter(
            property__owner=self.request.user
        ).select_related('property')
    
    def perform_create(self, serializer):
        # Vérifier que le logement appartient à l'utilisateur
        property_id = self.request.data.get('property')
        property_obj = Property.objects.get(id=property_id)
        
        if property_obj.owner != self.request.user and not self.request.user.is_staff:
            raise permissions.PermissionDenied("Vous n'êtes pas autorisé à ajouter des images à ce logement.")
        
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def set_as_main(self, request, pk=None):
        """
        Définit l'image comme image principale du logement.
        POST /api/v1/properties/images/{id}/set-as-main/
        """
        image = self.get_object()
        
        # Vérifier que l'utilisateur est le propriétaire du logement
        if image.property.owner != request.user and not request.user.is_staff:
            return Response(
                {"detail": "Vous n'êtes pas autorisé à effectuer cette action."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Mettre à jour l'image
        image.is_main = True
        image.save()
        
        return Response({"detail": "Image définie comme principale avec succès."})

class AvailabilityViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les disponibilités des logements.
    """
    serializer_class = AvailabilitySerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOfProperty]
    
    def get_queryset(self):
        # Les propriétaires ne voient que les disponibilités de leurs logements
        if self.request.user.is_owner:
            return Availability.objects.filter(
                property__owner=self.request.user
            ).select_related('property')
        # Les administrateurs voient tout
        elif self.request.user.is_staff:
            return Availability.objects.all().select_related('property')
        # Les autres ne voient rien
        else:
            return Availability.objects.none()
    
    def perform_create(self, serializer):
        # Vérifier que le logement appartient à l'utilisateur
        property_id = self.request.data.get('property')
        property_obj = Property.objects.get(id=property_id)
        
        if property_obj.owner != self.request.user and not self.request.user.is_staff:
            raise permissions.PermissionDenied("Vous n'êtes pas autorisé à gérer les disponibilités de ce logement.")
        
        serializer.save()
    
    @action(detail=False, methods=['get'])
    def by_property(self, request):
        """
        Liste les indisponibilités pour un logement spécifique.
        GET /api/v1/properties/unavailabilities/by-property/?property_id={id}
        """
        property_id = request.query_params.get('property_id')
        
        if not property_id:
            return Response(
                {"detail": "ID de logement requis."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Pour les propriétaires, vérifier qu'ils sont propriétaires du logement
        if request.user.is_authenticated and request.user.is_owner:
            try:
                property_obj = Property.objects.get(id=property_id)
                if property_obj.owner != request.user and not request.user.is_staff:
                    return Response(
                        {"detail": "Vous n'avez pas accès à ce logement."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except Property.DoesNotExist:
                return Response(
                    {"detail": "Logement non trouvé."},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Récupérer uniquement les indisponibilités futures
        today = timezone.now().date()
        unavailabilities = Availability.objects.filter(
            property_id=property_id,
            end_date__gte=today
        ).order_by('start_date')
        
        serializer = AvailabilitySerializer(unavailabilities, many=True)
        return Response(serializer.data)