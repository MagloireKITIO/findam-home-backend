# accounts/permissions.py
# Permissions personnalisées pour l'application accounts

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

class IsOwnerOfProfile(permissions.BasePermission):
    """
    Permission personnalisée pour permettre aux utilisateurs de modifier uniquement leur propre profil.
    """
    
    def has_object_permission(self, request, view, obj):
        # Les permissions en lecture sont autorisées pour toute requête,
        # donc on autorise les méthodes GET, HEAD et OPTIONS.
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Les permissions d'écriture sont réservées au propriétaire du profil.
        return obj.user == request.user

class IsAdminUser(permissions.BasePermission):
    """
    Permission personnalisée pour permettre uniquement aux administrateurs d'accéder à la vue.
    """
    
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)