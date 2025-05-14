# accounts/services/profile_filter_service.py

from typing import Dict, Any
from .models import User

class ProfileFilterService:
    """
    Service pour masquer les informations personnelles dans les profils
    jusqu'à ce que les conditions soient remplies.
    """
    
    @classmethod
    def filter_user_profile(cls, user: User, requesting_user: User, 
                          has_confirmed_booking: bool = False) -> Dict[str, Any]:
        """
        Filtre les informations d'un profil utilisateur.
        
        Args:
            user: Utilisateur dont on veut voir le profil
            requesting_user: Utilisateur qui fait la demande
            has_confirmed_booking: True s'il y a une réservation confirmée entre eux
        """
        # Informations de base toujours visibles
        filtered_data = {
            'id': str(user.id),
            'first_name': user.first_name,
            'user_type': user.user_type,
            'is_verified': user.is_verified,
            'date_joined': user.date_joined,
        }
        
        # Masquer les informations sensibles si pas de réservation confirmée
        if has_confirmed_booking or requesting_user.is_staff:
            filtered_data.update({
                'email': user.email,
                'phone_number': user.phone_number,
                'last_name': user.last_name,
            })
        else:
            # Masquer partiellement
            filtered_data.update({
                'email': cls._mask_email(user.email) if user.email else None,
                'phone_number': cls._mask_phone(user.phone_number) if user.phone_number else None,
                'last_name': user.last_name[0] + '***' if user.last_name else None,
            })
        
        return filtered_data
    
    @classmethod
    def _mask_email(cls, email: str) -> str:
        """Masque partiellement un email."""
        if '@' not in email:
            return '***@***.***'
        
        local, domain = email.split('@', 1)
        masked_local = local[0] + '*' * (len(local) - 1) if len(local) > 1 else '*'
        masked_domain = '***.***'
        
        return f"{masked_local}@{masked_domain}"
    
    @classmethod
    def _mask_phone(cls, phone: str) -> str:
        """Masque partiellement un numéro de téléphone."""
        if not phone:
            return None
        
        # Garder les 3 premiers et 2 derniers chiffres
        if len(phone) > 5:
            return phone[:3] + '*' * (len(phone) - 5) + phone[-2:]
        return '*' * len(phone)