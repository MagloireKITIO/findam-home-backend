# properties/filters.py
# Filtres personnalisés pour les logements

import django_filters
from django.db.models import Q
from django.utils import timezone
from .models import Property, Availability

class PropertyFilter(django_filters.FilterSet):
    """
    Filtre personnalisé pour les logements avec des options avancées de recherche.
    """
    # Filtres de base
    min_price = django_filters.NumberFilter(field_name="price_per_night", lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name="price_per_night", lookup_expr='lte')
    city = django_filters.NumberFilter(field_name="city__id")
    neighborhood = django_filters.NumberFilter(field_name="neighborhood__id")
    
    # Filtres pour les capacités et configurations
    min_capacity = django_filters.NumberFilter(field_name="capacity", lookup_expr='gte')
    min_bedrooms = django_filters.NumberFilter(field_name="bedrooms", lookup_expr='gte')
    min_bathrooms = django_filters.NumberFilter(field_name="bathrooms", lookup_expr='gte')
    
    # Filtre pour le type de logement
    property_type = django_filters.ChoiceFilter(choices=Property.PROPERTY_TYPE_CHOICES)
    
    # Filtre pour les équipements (plusieurs IDs séparés par des virgules)
    amenities = django_filters.CharFilter(method='filter_amenities')
    
    # Filtre pour les dates disponibles
    available_start = django_filters.DateFilter(method='filter_availability_start')
    available_end = django_filters.DateFilter(method='filter_availability_end')
    
    # Filtre pour les rabais autorisés
    allow_discount = django_filters.BooleanFilter()
    
    class Meta:
        model = Property
        fields = [
            'min_price', 'max_price', 'city', 'neighborhood',
            'min_capacity', 'min_bedrooms', 'min_bathrooms',
            'property_type', 'amenities', 
            'available_start', 'available_end',
            'allow_discount'
        ]
    
    def filter_amenities(self, queryset, name, value):
        """
        Filtre les logements qui ont tous les équipements spécifiés.
        Les IDs d'équipements sont passés sous forme de chaîne séparée par des virgules.
        """
        if not value:
            return queryset
        
        amenity_ids = [int(x.strip()) for x in value.split(',') if x.strip().isdigit()]
        
        if not amenity_ids:
            return queryset
        
        # Pour chaque équipement, filtrer les logements qui le possèdent
        for amenity_id in amenity_ids:
            queryset = queryset.filter(amenities__id=amenity_id)
        
        return queryset
    
    def filter_availability_start(self, queryset, name, value):
        """
        Filtre les logements disponibles à partir d'une date de début.
        """
        if not value:
            return queryset
        
        # Exclure les logements qui ont des indisponibilités chevauchant la date de début
        unavailable_properties = Availability.objects.filter(
            end_date__gte=value
        ).values_list('property_id', flat=True)
        
        return queryset.exclude(id__in=unavailable_properties)
    
    def filter_availability_end(self, queryset, name, value):
        """
        Filtre les logements disponibles jusqu'à une date de fin.
        """
        if not value:
            return queryset
        
        # Exclure les logements qui ont des indisponibilités chevauchant la date de fin
        unavailable_properties = Availability.objects.filter(
            start_date__lte=value
        ).values_list('property_id', flat=True)
        
        return queryset.exclude(id__in=unavailable_properties)