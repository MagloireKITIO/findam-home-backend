# common/decorators.py
from functools import wraps
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied

def require_role(*allowed_roles):
    """
    Décorateur qui vérifie que l'utilisateur a l'un des rôles autorisés.
    
    Usage:
    @require_role('owner')
    @require_role('owner', 'admin')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'error': 'Authentication required'
                }, status=401)
                
            # Les admins ont toujours accès
            if request.user.is_staff:
                return view_func(request, *args, **kwargs)
                
            # Vérifier le rôle
            if request.user.user_type not in allowed_roles:
                return JsonResponse({
                    'error': 'Insufficient permissions',
                    'detail': f'Cette ressource nécessite l\'un des rôles suivants: {", ".join(allowed_roles)}'
                }, status=403)
                
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator