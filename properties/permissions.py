# properties/permissions.py
# Permissions personnalisées pour l'application properties

from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission personnalisée pour permettre aux propriétaires d'objets de les modifier.
    """
    
    def has_object_permission(self, request, view, obj):
        # Les permissions en lecture sont autorisées pour toute requête,
        # donc on autorise les méthodes GET, HEAD et OPTIONS.
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Les permissions d'écriture sont réservées au propriétaire.
        return obj.owner == request.user

class IsOwnerOfProperty(permissions.BasePermission):
    """
    Permission personnalisée pour permettre uniquement aux propriétaires
    du logement de modifier ses informations et ressources liées.
    """
    
    def has_permission(self, request, view):
        # Pour la création d'un nouveau logement ou d'une ressource liée,
        # vérifier que l'utilisateur est authentifié
        if request.method == 'POST':
            return request.user.is_authenticated
        return True
    
    def has_object_permission(self, request, view, obj):
        # Les actions en lecture sont permises pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Vérifier si l'objet a directement un attribut owner
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        
        # Vérifier si l'objet est lié à un logement (comme une image)
        if hasattr(obj, 'property'):
            return obj.property.owner == request.user
        
        # Par défaut, refuser l'accès
        return False

class IsVerifiedOwner(permissions.BasePermission):
    """
    Permission personnalisée pour permettre uniquement aux propriétaires
    vérifiés de créer des logements.
    """
    
    def has_permission(self, request, view):
        # Vérifier que l'utilisateur est authentifié
        if not request.user.is_authenticated:
            return False
        
        # Vérifier que l'utilisateur est un propriétaire
        if not request.user.is_owner:
            return False
        
        # Vérifier que l'utilisateur est vérifié
        # Les administrateurs sont toujours considérés comme vérifiés
        if request.user.is_staff or request.user.is_verified:
            return True
        
        return False
    
    def has_object_permission(self, request, view, obj):
        # Pour les opérations sur un objet existant, utiliser la permission IsOwnerOfProperty
        return IsOwnerOfProperty().has_object_permission(request, view, obj)