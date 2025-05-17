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
from .middleware import SubscriptionLimitValidator
from .permissions import IsOwnerOrReadOnly, IsOwnerOfProperty, IsVerifiedOwner
from .filters import PropertyFilter
from decimal import Decimal
from common.permissions import IsOwnerRole, IsTenantRole


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
    GET /api/v1/properties/cities/featured/ - Villes en vedette
    """
    queryset = City.objects.all()
    serializer_class = CitySerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """
        Retourne les villes en vedette.
        GET /api/v1/properties/cities/featured/
        """
        featured_cities = City.objects.filter(is_featured=True).order_by('name')
        serializer = self.get_serializer(featured_cities, many=True)
        return Response(serializer.data)

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
        is_owner_view = self.request.query_params.get('is_owner', 'false').lower() == 'true'
        
        # Cas 1: Administrateur - voit tout
        if user.is_authenticated and user.is_staff:
            return queryset
        
        # Cas 2: Propriétaire consultant ses propres logements
        # ou effectuant des actions sur ses propres logements
        if user.is_authenticated and hasattr(user, 'is_owner') and user.is_owner:
            if is_owner_view or self.action in ['publish', 'unpublish', 'update', 'partial_update', 'destroy']:
                return queryset.filter(owner=user)
        
        # Cas 3: Tout autre utilisateur (authentifié ou non) - ne voit que les logements publiés ET vérifiés
        return queryset.filter(is_published=True, is_verified=True)
        
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
        Définit les permissions selon l'action et le rôle.
        """
        if self.action in ['create']:
            # Création réservée aux propriétaires vérifiés
            permission_classes = [IsOwnerRole, IsVerifiedOwner]
        elif self.action in ['update', 'partial_update', 'destroy']:
            # Modification/suppression par le propriétaire du logement
            permission_classes = [IsOwnerRole, IsOwnerOfProperty]
        elif self.action in ['publish', 'unpublish']:
            # Gestion de publication par le propriétaire
            permission_classes = [IsOwnerRole, IsOwnerOfProperty]
        elif self.action in ['verify']:
            # Vérification uniquement par les admins
            permission_classes = [permissions.IsAdminUser]
        elif self.action in ['my_properties']:
            # Mes logements pour les propriétaires
            permission_classes = [IsOwnerRole]
        else:
            # Actions de lecture publiques
            permission_classes = [permissions.AllowAny]
        
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """
        Associe automatiquement le propriétaire à la création d'un logement
        """
        # Modification: Ne plus vérifier les limites d'abonnement
        # La ligne ci-dessous est commentée/supprimée
        # SubscriptionLimitValidator.validate_property_creation(self.request.user)
        
        # Créer le logement directement
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
        Publie un logement.
        POST /api/v1/properties/{id}/publish/
        """
        try:
            print(f"DEBUG: Tentative de récupération de la propriété avec l'ID: {pk}")
            print(f"DEBUG: Type de pk: {type(pk)}")
            
            property_obj = self.get_object()
            print(f"DEBUG: Propriété récupérée avec succès. ID: {property_obj.id}, Titre: {property_obj.title}")
            
            # Vérifier que l'utilisateur est le propriétaire
            print(f"DEBUG: Utilisateur requête: {request.user.id}, Propriétaire: {property_obj.owner.id}")
            if property_obj.owner != request.user and not request.user.is_staff:
                print("DEBUG: L'utilisateur n'est pas autorisé")
                return Response(
                    {"detail": "Vous n'êtes pas autorisé à effectuer cette action."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Vérifier si des images sont présentes
            image_count = property_obj.images.count()
            print(f"DEBUG: Nombre d'images: {image_count}")
            if not property_obj.images.exists():
                print("DEBUG: Aucune image trouvée")
                return Response(
                    {"detail": "Vous devez ajouter au moins une image avant de publier."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Définir comme publié
            print(f"DEBUG: Statut actuel de publication: {property_obj.is_published}")
            property_obj.is_published = True
            property_obj.save(update_fields=['is_published'])
            print("DEBUG: Enregistrement réussi, propriété publiée")
            
            # Retourner le logement mis à jour
            print("DEBUG: Création du sérialiseur")
            serializer = PropertyDetailSerializer(property_obj, context={'request': request})
            print("DEBUG: Sérialisation réussie")
            
            return Response({
                "detail": "Le logement a été publié avec succès.",
                "property": serializer.data
            })
    
        except Exception as e:
            print(f"ERREUR: Exception lors de la publication: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"detail": f"Une erreur est survenue: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
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
        
        # Retourner le logement mis à jour
        serializer = PropertyDetailSerializer(property_obj, context={'request': request})
        
        return Response({
            "detail": "Le logement a été dépublié avec succès.",
            "property": serializer.data
        })
    
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
        GET /api/v1/properties/{id}/check_availability/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
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
        
        # Ajouter les réservations externes comme indisponibilités
        from bookings.models import Booking
        external_bookings = Booking.objects.filter(
            property=property_obj,
            is_external=True,
            status__in=['confirmed', 'completed'],
            check_in_date__lte=end_date,
            check_out_date__gte=start_date
        )
        
        # Combiner unavailabilities et external bookings
        is_available = not (unavailabilities.exists() or external_bookings.exists())
        
        # Calculer le prix total pour la période
        days = (end_date - start_date).days
        total_price = property_obj.calculate_price_for_days(days)
        
        # Ajouter les frais de ménage
        if property_obj.cleaning_fee:
            total_price += property_obj.cleaning_fee
        
        # Calculer les frais de service (7%)
        service_fee = total_price * Decimal('0.07')
        
        # Récupérer toutes les indisponibilités futures
        today = timezone.now().date()
        all_unavailabilities = property_obj.unavailabilities.filter(
            end_date__gte=today
        ).values('start_date', 'end_date', 'booking_type')
        
        # Récupérer toutes les réservations externes futures
        all_external_bookings = Booking.objects.filter(
            property=property_obj,
            is_external=True,
            status__in=['confirmed', 'completed'],
            check_out_date__gte=today
        ).values('check_in_date', 'check_out_date')
        
        # Combiner toutes les indisponibilités
        all_unavailable = list(all_unavailabilities)
        for booking in all_external_bookings:
            all_unavailable.append({
                'start_date': booking['check_in_date'],
                'end_date': booking['check_out_date'],
                'booking_type': 'external'
            })
        
        return Response({
            "available": is_available,
            "property_id": property_obj.id,
            "start_date": start_date,
            "end_date": end_date,
            "nights": days,
            "base_price": total_price,
            "cleaning_fee": property_obj.cleaning_fee,
            "security_deposit": property_obj.security_deposit,
            "service_fee": service_fee,
            "total_price": total_price + property_obj.security_deposit + service_fee,
            "unavailable_dates": list(unavailabilities.values('start_date', 'end_date', 'booking_type')) + 
                                [{'start_date': b.check_in_date, 'end_date': b.check_out_date, 'booking_type': 'external'} 
                                for b in external_bookings],
            "all_unavailable_dates": all_unavailable
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
    
    def get_permissions(self):
        """
        Seuls les propriétaires peuvent gérer les images de leurs logements.
        """
        return [IsOwnerRole(), IsOwnerOfProperty()]
    
    def get_queryset(self):
        """
        Propriétaires ne voient que les images de leurs logements.
        """
        if not self.request.user.is_authenticated or not self.request.user.is_owner:
            return PropertyImage.objects.none()
        
        return PropertyImage.objects.filter(
            property__owner=self.request.user
        ).select_related('property')

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
    def get_permissions(self):
        """
        Seuls les propriétaires peuvent gérer les disponibilités.
        """
        if self.action in ['by_property'] and self.request.method == 'GET':
            return [permissions.AllowAny()]
        return [IsOwnerRole(), IsOwnerOfProperty()]
    
    def get_queryset(self):
        """
        Filtre selon le rôle de l'utilisateur.
        """
        user = self.request.user
        
        if not user.is_authenticated:
            return Availability.objects.none()
        
        if user.is_staff:
            return Availability.objects.all().select_related('property')
        
        if user.is_owner:
            return Availability.objects.filter(
                property__owner=user
            ).select_related('property')
        
        return Availability.objects.none()