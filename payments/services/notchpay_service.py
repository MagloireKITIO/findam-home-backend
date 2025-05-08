# payments/services/notchpay_service.py
# Service pour l'intégration avec l'API NotchPay

import requests
import hmac
import hashlib
import logging
import uuid
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger('findam')

class NotchPayService:
    """
    Service pour interagir avec l'API NotchPay.
    Gère l'initialisation des paiements, la vérification des statuts, et la validation des callbacks.
    """
    
    def __init__(self):
        """Initialisation avec les clés d'API depuis les paramètres de configuration"""
        self.private_key = settings.NOTCHPAY_PRIVATE_KEY
        self.public_key = getattr(settings, 'NOTCHPAY_PUBLIC_KEY', '')
        self.base_url = "https://api.notchpay.co"
        self.is_sandbox = settings.NOTCHPAY_SANDBOX
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": self.public_key  # IMPORTANT: Utilisez la clé publique sans "Bearer"
        }
    
    def initialize_payment(self, amount, currency="XAF", description=None, customer_info=None, 
                         metadata=None, callback_url=None, reference=None, success_url=None, cancel_url=None):
        """
        Initialiser un paiement avec NotchPay
        
        Args:
            amount (Decimal): Montant du paiement
            currency (str): Code de devise (par défaut XAF)
            description (str): Description du paiement
            customer_info (dict): Informations sur le client (email, phone, name)
            metadata (dict): Données supplémentaires à stocker avec le paiement
            callback_url (str): URL de callback pour les notifications
            reference (str): Référence unique pour ce paiement (générée si non fournie)
            success_url (str): URL de redirection en cas de paiement réussi
            cancel_url (str): URL de redirection en cas d'annulation du paiement
            
        Returns:
            dict: Réponse de l'API NotchPay contenant l'URL de redirection pour le paiement
        """
        
        # Générer une référence unique si non fournie
        if not reference:
            reference = f"findam-{uuid.uuid4().hex[:8]}-{int(timezone.now().timestamp())}"
        
        # Préparer le corps de la requête
        payload = {
            "currency": currency,
            "amount": float(amount),  # Convertir Decimal en float pour JSON
            "reference": reference,
            "description": description or "Paiement via Findam",
        }
        
        # Ajouter les informations du client si fournies
        if customer_info:
            payload["customer"] = {
                "email": customer_info.get("email", ""),
                "phone": customer_info.get("phone", ""),
                "name": customer_info.get("name", ""),
            }
        
        # Ajouter les métadonnées si fournies
        if metadata:
            payload["metadata"] = metadata
        
        # Ajouter l'URL de callback si fournie
        if callback_url:
            payload["callback"] = callback_url
        
        # Ajouter les URLs de redirection (IMPORTANT - Nouveaux paramètres)
        if success_url:
            payload["success_url"] = success_url
        
        if cancel_url:
            payload["cancel_url"] = cancel_url
        
        # Envoyer la requête à NotchPay
        logger.info(f"Tentative d'initialisation de paiement NotchPay")
        logger.info(f"URL: {self.base_url}/payments")
        logger.info(f"Headers: {self.headers}")
        logger.info(f"Payload: {payload}")
        
        try:
            logger.info(f"Initialisation de paiement NotchPay pour {amount} {currency}")
            response = requests.post(
            f"{self.base_url}/payments",
            json=payload,
            headers=self.headers
            )
            
            # Log de la réponse complète
            logger.info(f"Réponse API NotchPay - Status: {response.status_code}")
            logger.info(f"Réponse API NotchPay - Headers: {response.headers}")
            try:
                logger.info(f"Réponse API NotchPay - Body: {response.json()}")
            except:
                logger.info(f"Réponse API NotchPay - Body: {response.text}")
            
            # Vérifier la réponse
            response.raise_for_status()
            payment_data = response.json()
            
            logger.info(f"Paiement NotchPay initialisé avec succès: {payment_data.get('transaction', {}).get('reference')}")
            return payment_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de l'initialisation du paiement NotchPay: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails de la réponse en erreur: {e.response.status_code}")
                try:
                    logger.error(f"Contenu de la réponse en erreur: {e.response.json()}")
                except:
                    logger.error(f"Contenu de la réponse en erreur: {e.response.text}")
            raise
    
    def process_payment(self, payment_reference, payment_method, phone=None, email=None):
        """
        Traiter un paiement avec une méthode spécifique
        
        Args:
            payment_reference (str): Référence du paiement initialisé
            payment_method (str): Méthode de paiement (cm.mobile, cm.mtn, cm.orange, etc.)
            phone (str): Numéro de téléphone (pour Mobile Money)
            email (str): Email (pour PayPal)
            
        Returns:
            dict: Résultat du traitement du paiement
        """
        payload = {
            "channel": payment_method
        }
        
        # Ajouter le téléphone pour Mobile Money
        if payment_method in ['cm.mobile', 'cm.mtn', 'cm.orange'] and phone:
            payload["phone"] = phone
        
        # Ajouter l'email pour PayPal
        if payment_method == 'paypal' and email:
            payload["email"] = email
        
        try:
            logger.info(f"Traitement du paiement {payment_reference} via {payment_method}")
            response = requests.post(
                f"{self.base_url}/payments/{payment_reference}",
                json=payload,
                headers=self.headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Paiement {payment_reference} traité: {result.get('status')}")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors du traitement du paiement {payment_reference}: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails: {e.response.text}")
            raise
    
    def verify_payment(self, payment_reference):
        """
        Vérifier le statut d'un paiement
        
        Args:
            payment_reference (str): Référence du paiement à vérifier
            
        Returns:
            dict: Informations sur le statut du paiement
        """
        try:
            logger.info(f"Vérification du statut du paiement {payment_reference}")
            response = requests.get(
                f"{self.base_url}/payments/{payment_reference}",
                headers=self.headers
            )
            
            response.raise_for_status()
            payment_data = response.json()
            
            logger.info(f"Statut du paiement {payment_reference}: {payment_data.get('transaction', {}).get('status')}")
            return payment_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la vérification du paiement {payment_reference}: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails: {e.response.text}")
            raise
    
    def verify_webhook_signature(self, payload, signature_header):
        """
        Vérifier la signature d'un webhook NotchPay
        
        Args:
            payload (str): Le corps de la requête en string
            signature_header (str): La signature dans l'en-tête X-Notch-Signature
            
        Returns:
            bool: True si la signature est valide, False sinon
        """
        if not signature_header or not self.private_key:
            return False
        
        # Calculer la signature locale
        computed_signature = hmac.new(
            self.private_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Comparer avec la signature reçue
        return hmac.compare_digest(computed_signature, signature_header)
    
    def get_payment_channels(self):
        """
        Récupérer les canaux de paiement disponibles
        
        Returns:
            list: Liste des canaux de paiement disponibles
        """
        try:
            response = requests.get(
                f"{self.base_url}/channels",
                headers=self.headers
            )
            
            response.raise_for_status()
            channels_data = response.json()
            
            # Filtrer les canaux actifs
            active_channels = [
                channel for channel in channels_data.get('data', [])
                if channel.get('active') and channel.get('enabled')
            ]
            
            return active_channels
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la récupération des canaux de paiement: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails: {e.response.text}")
            return []
    
    def cancel_payment(self, payment_reference):
        """
        Annuler un paiement
        
        Args:
            payment_reference (str): Référence du paiement à annuler
            
        Returns:
            dict: Résultat de l'annulation
        """
        try:
            logger.info(f"Annulation du paiement {payment_reference}")
            response = requests.delete(
                f"{self.base_url}/payments/{payment_reference}",
                headers=self.headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Paiement {payment_reference} annulé: {result.get('status')}")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de l'annulation du paiement {payment_reference}: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails: {e.response.text}")
            raise