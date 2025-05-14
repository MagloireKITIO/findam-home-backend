# communications/services/message_filter_service.py - Version améliorée

import re
from typing import Tuple, List, Dict
from django.conf import settings

class MessageFilterService:
    """
    Service pour filtrer les informations de contact dans les messages
    afin d'éviter la désintermédiation sur la plateforme.
    """
    
    # Patterns pour détecter les numéros camerounais (plus complets)
    CAMEROON_PHONE_PATTERNS = [
        r'\+?237\s?[2-9]\d{7,8}',              # +237 2XXXXXXX ou +237 6XXXXXXX
        r'\b[69]\d{8}\b',                      # 6XXXXXXXX ou 9XXXXXXXX
        r'\b2[2-9]\d{7}\b',                    # 22XXXXXXX, 23XXXXXXX, etc.
        r'\b\d{3}\s?\d{3}\s?\d{3}\b',          # Format XXX XXX XXX
        r'\b\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\b',  # Format XX XX XX XXX
    ]
    
    # Patterns pour emails (améliorés)
    EMAIL_PATTERNS = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        r'\b[A-Za-z0-9._%+-]+\s*at\s*[A-Za-z0-9.-]+\s*dot\s*[A-Z|a-z]{2,}\b',  # "email at domain dot com"
        r'\b[A-Za-z0-9._%+-]+\[@\][A-Za-z0-9.-]+\[.\][A-Z|a-z]{2,}\b',  # "email[@]domain[.]com"
    ]
    
    # Patterns pour WhatsApp et autres messageries
    WHATSAPP_PATTERNS = [
        r'\bwhatsapp\b',
        r'\bwhats\s?app\b',
        r'\bwa\.me\b',
        r'\bwatsap\b',
        r'\btelegram\b',
        r'\bviber\b',
        r'\bimo\b',
        r'\bmessenger\b',
    ]
    
    # Patterns pour réseaux sociaux
    SOCIAL_PATTERNS = [
        r'\bfacebook\b',
        r'\bfb\.com\b',
        r'\bfb\.me\b',
        r'\binstagram\b',
        r'\btwitter\b',
        r'\btiktok\b',
        r'\blinkedin\b',
    ]
    
    WARNING_MESSAGES = {
        'phone': '[📱 Numéro masqué - Disponible après confirmation]',
        'email': '[📧 Email masqué - Disponible après confirmation]',
        'whatsapp': '[💬 Contact WhatsApp masqué - Restez sur la plateforme]',
        'social': '[📱 Réseau social masqué - Utilisez la messagerie Findam]'
    }
    
    @classmethod
    def filter_message_content(cls, content: str, booking_confirmed: bool = False) -> Tuple[str, List[str]]:
        """
        Filtre le contenu d'un message en masquant les informations de contact.
        """
        if booking_confirmed:
            return content, []
        
        filtered_content = content
        masked_items = []
        
        # Filtrer les numéros de téléphone camerounais
        for pattern in cls.CAMEROON_PHONE_PATTERNS:
            matches = re.findall(pattern, filtered_content, re.IGNORECASE)
            if matches:
                for match in matches:
                    filtered_content = filtered_content.replace(match, cls.WARNING_MESSAGES['phone'])
                masked_items.append('phone')
        
        # Filtrer les emails
        for pattern in cls.EMAIL_PATTERNS:
            matches = re.findall(pattern, filtered_content, re.IGNORECASE)
            if matches:
                for match in matches:
                    filtered_content = filtered_content.replace(match, cls.WARNING_MESSAGES['email'])
                masked_items.append('email')
        
        # Filtrer WhatsApp (case insensitive)
        for pattern in cls.WHATSAPP_PATTERNS:
            if re.search(pattern, filtered_content, re.IGNORECASE):
                filtered_content = re.sub(pattern, cls.WARNING_MESSAGES['whatsapp'], 
                                        filtered_content, flags=re.IGNORECASE)
                masked_items.append('whatsapp')
        
        # Filtrer réseaux sociaux
        for pattern in cls.SOCIAL_PATTERNS:
            if re.search(pattern, filtered_content, re.IGNORECASE):
                filtered_content = re.sub(pattern, cls.WARNING_MESSAGES['social'], 
                                        filtered_content, flags=re.IGNORECASE)
                masked_items.append('social')
        
        return filtered_content, list(set(masked_items))
    
    @classmethod
    def should_reveal_contacts(cls, conversation) -> bool:
        """
        Détermine si les contacts doivent être révélés dans une conversation.
        """
        if not conversation.property:
            return False
        
        # Vérifier s'il y a une réservation confirmée et payée
        from bookings.models import Booking
        confirmed_booking = Booking.objects.filter(
            property=conversation.property,
            tenant__in=conversation.participants.all(),
            status='confirmed',
            payment_status='paid'
        ).exists()
        
        return confirmed_booking
    
    @classmethod
    def get_anti_disintermediation_warning(cls) -> str:
        """
        Retourne le message d'avertissement anti-désintermédiation.
        """
        return (
            "🔒 Pour votre sécurité et celle de tous les utilisateurs, "
            "restez sur la plateforme Findam pour toutes vos communications. "
            "Les coordonnées seront disponibles après confirmation de votre réservation."
        )