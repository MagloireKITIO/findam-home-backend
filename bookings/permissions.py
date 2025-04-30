# bookings/permissions.py
# Permissions personnalisées pour l'application bookings

from rest_framework import permissions

class IsBookingParticipant(permissions.BasePermission):
    """
    Permission qui autorise uniquement le locataire ou le propriétaire du logement 
    à accéder à une réservation.
    """
    
    def has_object_permission(self, request, view, obj):
        # Les administrateurs ont tous les droits
        if request.user.is_staff:
            return True
        
        # L'utilisateur doit être soit le locataire, soit le propriétaire du logement
        return (obj.tenant == request.user) or (obj.property.owner == request.user)

class IsPromoCodeOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission qui autorise uniquement le propriétaire d'un code promo à le modifier.
    """
    
    def has_object_permission(self, request, view, obj):
        # Les administrateurs ont tous les droits
        if request.user.is_staff:
            return True
        
        # Les permissions en lecture sont autorisées si l'utilisateur est concerné par le code
        if request.method in permissions.SAFE_METHODS:
            return (obj.property.owner == request.user) or (obj.tenant == request.user)
        
        # Les permissions d'écriture sont réservées au propriétaire du logement
        return obj.property.owner == request.user

class CanLeaveReview(permissions.BasePermission):
    """
    Permission qui autorise uniquement le locataire ou le propriétaire d'une réservation
    à laisser un avis.
    """
    
    def has_permission(self, request, view):
        # Pour la création d'avis, vérifier que l'utilisateur est lié à la réservation
        if request.method == 'POST':
            booking_id = request.data.get('booking')
            if not booking_id:
                return False
            
            from .models import Booking
            try:
                booking = Booking.objects.get(id=booking_id)
                return (booking.tenant == request.user) or (booking.property.owner == request.user)
            except Booking.DoesNotExist:
                return False
        
        return True
    
    def has_object_permission(self, request, view, obj):
        # Les administrateurs ont tous les droits
        if request.user.is_staff:
            return True
        
        # Seuls le locataire et le propriétaire peuvent voir ou modifier l'avis
        return (obj.booking.tenant == request.user) or (obj.booking.property.owner == request.user)