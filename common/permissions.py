# common/permissions.py
from rest_framework import permissions

class IsOwnerRole(permissions.BasePermission):
    """
    Permission personnalisée pour vérifier que l'utilisateur est un propriétaire.
    """
    message = "Seuls les propriétaires peuvent accéder à cette ressource."
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_owner or request.user.is_staff)
        )

class IsTenantRole(permissions.BasePermission):
    """
    Permission personnalisée pour vérifier que l'utilisateur est un locataire.
    """
    message = "Seuls les locataires peuvent accéder à cette ressource."
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_tenant or request.user.is_staff)
        )

class RoleBasedPermission(permissions.BasePermission):
    """
    Permission flexible basée sur les rôles.
    """
    def __init__(self, allowed_roles=None):
        self.allowed_roles = allowed_roles or []
    
    def __call__(self):
        return self
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        # Les admins ont toujours accès
        if request.user.is_staff:
            return True
            
        # Vérifier si le rôle de l'utilisateur est autorisé
        return request.user.user_type in self.allowed_roles