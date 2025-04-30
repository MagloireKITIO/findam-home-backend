# bookings/filters.py
# Filtres personnalisés pour les réservations

import django_filters
from django.db.models import Q
from django.utils import timezone
from .models import Booking

class BookingFilter(django_filters.FilterSet):
    """
    Filtre personnalisé pour les réservations avec des options avancées de recherche.
    """
    # Filtres de date
    start_date = django_filters.DateFilter(field_name="check_in_date", lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name="check_out_date", lookup_expr='lte')
    created_after = django_filters.DateFilter(field_name="created_at", lookup_expr='gte')
    created_before = django_filters.DateFilter(field_name="created_at", lookup_expr='lte')
    
    # Filtres de prix
    min_price = django_filters.NumberFilter(field_name="total_price", lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name="total_price", lookup_expr='lte')
    
    # Filtres de statut
    status = django_filters.ChoiceFilter(choices=Booking.STATUS_CHOICES)
    payment_status = django_filters.ChoiceFilter(choices=Booking.PAYMENT_STATUS_CHOICES)
    
    # Filtres pour la propriété et le locataire
    property = django_filters.UUIDFilter(field_name="property__id")
    property_city = django_filters.NumberFilter(field_name="property__city__id")
    property_neighborhood = django_filters.NumberFilter(field_name="property__neighborhood__id")
    tenant = django_filters.UUIDFilter(field_name="tenant__id")
    
    # Filtre pour les réservations actives (actuelles)
    is_active = django_filters.BooleanFilter(method='filter_active')
    
    # Filtre pour les réservations passées
    is_past = django_filters.BooleanFilter(method='filter_past')
    
    # Filtre pour les réservations futures
    is_future = django_filters.BooleanFilter(method='filter_future')
    
    class Meta:
        model = Booking
        fields = [
            'start_date', 'end_date', 'created_after', 'created_before',
            'min_price', 'max_price', 'status', 'payment_status',
            'property', 'property_city', 'property_neighborhood', 'tenant',
            'is_active', 'is_past', 'is_future'
        ]
    
    def filter_active(self, queryset, name, value):
        """
        Filtre les réservations actuelles (check_in_date <= aujourd'hui <= check_out_date).
        """
        today = timezone.now().date()
        
        if value:  # Si True, on filtre les réservations actives
            return queryset.filter(
                check_in_date__lte=today,
                check_out_date__gte=today,
                status='confirmed'
            )
        else:  # Si False, on exclut les réservations actives
            return queryset.exclude(
                check_in_date__lte=today,
                check_out_date__gte=today,
                status='confirmed'
            )
    
    def filter_past(self, queryset, name, value):
        """
        Filtre les réservations passées (check_out_date < aujourd'hui).
        """
        today = timezone.now().date()
        
        if value:  # Si True, on filtre les réservations passées
            return queryset.filter(check_out_date__lt=today)
        else:  # Si False, on exclut les réservations passées
            return queryset.exclude(check_out_date__lt=today)
    
    def filter_future(self, queryset, name, value):
        """
        Filtre les réservations futures (check_in_date > aujourd'hui).
        """
        today = timezone.now().date()
        
        if value:  # Si True, on filtre les réservations futures
            return queryset.filter(check_in_date__gt=today)
        else:  # Si False, on exclut les réservations futures
            return queryset.exclude(check_in_date__gt=today)