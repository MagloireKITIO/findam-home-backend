# payments/utils.py
# Utilitaires pour la gestion des paiements

import logging
import re
import hashlib
import hmac

logger = logging.getLogger('findam')

class PaymentStatus:
    """Constantes pour les statuts de paiement"""
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    REFUNDED = 'refunded'
    CANCELLED = 'cancelled'

class NotchPayUtils:
    """Utilitaires pour l'intégration avec NotchPay"""
    
    # Mappage des statuts NotchPay vers nos statuts internes
    PAYMENT_STATUS_MAP = {
        'pending': PaymentStatus.PENDING,
        'processing': PaymentStatus.PROCESSING,
        'success': PaymentStatus.COMPLETED,
        'completed': PaymentStatus.COMPLETED,
        'failed': PaymentStatus.FAILED,
        'refunded': PaymentStatus.REFUNDED,
        'expired': PaymentStatus.FAILED,
        'cancelled': PaymentStatus.CANCELLED,
        'error': PaymentStatus.FAILED,
    }
    
    # Mappage des types d'opérateurs Mobile Money
    MOBILE_OPERATORS = {
        'orange': 'cm.orange',
        'mtn': 'cm.mtn',
        'mobile_money': 'cm.mobile',  # Combiné, NotchPay s'occupe de la détection
    }
    
    @staticmethod
    def convert_notchpay_status(notchpay_status):
        """Convertit un statut NotchPay en statut interne"""
        status_mapping = {
            'new': PaymentStatus.PENDING,
            'pending': PaymentStatus.PENDING,
            'processing': PaymentStatus.PROCESSING,
            'success': PaymentStatus.COMPLETED,
            'successful': PaymentStatus.COMPLETED,
            'complete': PaymentStatus.COMPLETED,  # Ajouter cette ligne
            'completed': PaymentStatus.COMPLETED,
            'failed': PaymentStatus.FAILED,
            'canceled': PaymentStatus.CANCELLED,
            'cancelled': PaymentStatus.CANCELLED,
            'refunded': PaymentStatus.REFUNDED,
        }
        
        notchpay_status_lower = notchpay_status.lower() if notchpay_status else 'pending'
        return status_mapping.get(notchpay_status_lower, PaymentStatus.PENDING)
    
    @staticmethod
    def get_mobile_operator_code(operator):
        """
        Convertit un nom d'opérateur en code NotchPay
        
        Args:
            operator (str): Nom de l'opérateur (orange, mtn ou mobile_money)
            
        Returns:
            str: Code de l'opérateur pour NotchPay
        """
        if not operator:
            return 'cm.mobile'
            
        return NotchPayUtils.MOBILE_OPERATORS.get(operator.lower(), 'cm.mobile')
    
    @staticmethod
    def format_phone_number(phone_number):
        """
        Formatage du numéro de téléphone pour NotchPay
        
        Args:
            phone_number (str): Numéro de téléphone
            
        Returns:
            str: Numéro formaté pour NotchPay
        """
        if not phone_number:
            return ""
            
        # Supprimer les espaces et autres caractères non numériques
        cleaned_number = ''.join(filter(str.isdigit, phone_number))
        
        # Si le numéro commence par un 6, ajouter l'indicatif du Cameroun
        if cleaned_number.startswith('6') and len(cleaned_number) == 9:
            return f"237{cleaned_number}"
        
        # Si le numéro commence déjà par 237, le retourner tel quel
        if cleaned_number.startswith('237') and len(cleaned_number) == 12:
            return cleaned_number
        
        # Si le numéro commence par +237, supprimer le +
        if phone_number.startswith('+237') and len(cleaned_number) == 12:
            return cleaned_number
            
        return cleaned_number
    
    @staticmethod
    def is_valid_cameroon_phone(phone):
        """
        Valide un numéro de téléphone camerounais
        """
        if not phone:
            return False
        
        # Nettoyer le numéro
        clean_phone = re.sub(r'[\s\-\(\)]+', '', phone)
        
        # Patterns de validation
        patterns = [
            r'^\+237[6][5-9]\d{7}$',  # Format international
            r'^237[6][5-9]\d{7}$',    # Sans le +
            r'^[6][5-9]\d{7}$'        # Format local
        ]
        
        return any(re.match(pattern, clean_phone) for pattern in patterns)
    
    @staticmethod
    def detect_mobile_operator(phone):
        """
        Détecte automatiquement l'opérateur Mobile Money
        """
        if not phone:
            return 'mobile_money'
        
        clean_phone = re.sub(r'[\s\-\(\)]+', '', phone)
        
        # Extraire les deux premiers chiffres après 237
        if clean_phone.startswith('+237'):
            prefix = clean_phone[4:6]
        elif clean_phone.startswith('237'):
            prefix = clean_phone[3:5]
        elif clean_phone.startswith('6'):
            prefix = clean_phone[:2]
        else:
            return 'mobile_money'
        
        # Orange Money : 69, 65
        if prefix in ['69', '65']:
            return 'orange'
        # MTN MoMo : 67, 68, 66
        elif prefix in ['67', '68', '66']:
            return 'mtn'
        
        return 'mobile_money'
    
    @staticmethod
    def verify_webhook_signature(payload, signature, secret_key):
        """
        Vérifie la signature d'un webhook NotchPay
        """
        if not secret_key or not signature:
            return False
        
        # Calculer la signature locale
        computed_signature = hmac.new(
            secret_key.encode('utf-8'),
            payload.encode('utf-8') if isinstance(payload, str) else payload,
            hashlib.sha256
        ).hexdigest()
        
        # Comparer les signatures
        return hmac.compare_digest(computed_signature, signature)

class PaymentCalculator:
    """Utilitaires pour les calculs de paiement"""
    
    @staticmethod
    def calculate_booking_fees(price, nights, tenant_fee_percentage=0.07):
        """
        Calcule les frais de service pour une réservation
        
        Args:
            price (float): Prix total de la réservation (sans frais)
            nights (int): Nombre de nuits
            tenant_fee_percentage (float): Pourcentage des frais pour le locataire
            
        Returns:
            float: Montant des frais de service
        """
        if price <= 0 or nights <= 0:
            return 0
            
        # Calculer les frais de service
        service_fee = price * tenant_fee_percentage
        
        # Arrondir à l'entier supérieur
        service_fee = round(service_fee)
        
        return service_fee
    
    @staticmethod
    def calculate_owner_commission(price, subscription_type):
        """
        Calcule la commission du propriétaire selon son type d'abonnement
        
        Args:
            price (float): Prix de base (sans les frais)
            subscription_type (str): Type d'abonnement (free, monthly, quarterly, yearly)
            
        Returns:
            float: Montant de la commission
        """
        # Définir le taux de commission selon le type d'abonnement
        commission_rates = {
            'free': 0.03,     # 3%
            'monthly': 0.02,  # 2%
            'quarterly': 0.015, # 1.5%
            'yearly': 0.01   # 1%
        }
        
        # Récupérer le taux (utiliser 3% par défaut)
        rate = commission_rates.get(subscription_type, 0.03)
        
        # Calculer la commission
        commission = price * rate
        
        # Arrondir à l'entier supérieur
        commission = round(commission)
        
        return commission