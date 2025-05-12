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
        
        # Ajouter les URLs de redirection
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
            
            # 1. D'abord, rechercher dans la base de données par transaction_id exact
            from bookings.models import PaymentTransaction
            transaction = PaymentTransaction.objects.filter(transaction_id=payment_reference).first()
            
            notchpay_ref = None
            if transaction and transaction.payment_response:
                # Extraire la référence NotchPay de payment_response
                if isinstance(transaction.payment_response, dict) and 'transaction' in transaction.payment_response:
                    notchpay_ref = transaction.payment_response['transaction'].get('reference')
            
            # 2. Si aucune référence trouvée et c'est une référence booking-xxx
            if not notchpay_ref and payment_reference.startswith('booking-'):
                # Remplacer TOUS les types d'espaces et nettoyer la chaîne
                clean_reference = payment_reference.replace('\xa0', '').replace(' ', '').strip()
                parts = clean_reference.split('-')
                
                # Extraire l'ID de réservation
                if len(parts) >= 5:
                    booking_id = f"{parts[1]}-{parts[2]}-{parts[3]}-{parts[4]}"
                    
                    # Chercher dans la base de données avec cet ID
                    from bookings.models import Booking
                    try:
                        booking = Booking.objects.get(id=booking_id)
                        # Trouver la transaction associée
                        tx = booking.transactions.order_by('-created_at').first()
                        if tx and tx.payment_response:
                            if isinstance(tx.payment_response, dict) and 'transaction' in tx.payment_response:
                                notchpay_ref = tx.payment_response['transaction'].get('reference')
                    except Exception as e:
                        logger.warning(f"Erreur lors de la recherche avec l'ID nettoyé: {str(e)}")
            
            # 3. Chercher directement dans la base de données toutes les transactions récentes
            if not notchpay_ref:
                recent_txs = PaymentTransaction.objects.filter(
                    status__in=['pending', 'processing']
                ).order_by('-created_at')[:10]
                
                for tx in recent_txs:
                    if tx.payment_response and isinstance(tx.payment_response, dict) and 'transaction' in tx.payment_response:
                        ref = tx.payment_response['transaction'].get('reference')
                        if ref and ref.startswith('trx.'):
                            notchpay_ref = ref
                            logger.info(f"Référence NotchPay trouvée dans les transactions récentes: {notchpay_ref}")
                            break
            
            # 4. Si on a trouvé une référence valide, faire la requête à NotchPay
            if notchpay_ref:
                logger.info(f"Utilisation de la référence NotchPay: {notchpay_ref}")
                response = requests.get(
                    f"{self.base_url}/payments/{notchpay_ref}",
                    headers=self.headers
                )
                
                response.raise_for_status()
                payment_data = response.json()
                
                # Si le statut est "complete", mettre à jour la transaction et la réservation
                status = payment_data.get('transaction', {}).get('status')
                logger.info(f"Statut du paiement {notchpay_ref}: {status}")
                
                if status == 'complete' or status == 'successful':
                    # Mettre à jour la transaction originale et la réservation
                    if transaction:
                        transaction.status = 'completed'
                        transaction.save(update_fields=['status'])
                        
                        # Mettre à jour la réservation associée
                        if transaction.booking:
                            transaction.booking.payment_status = 'paid'
                            transaction.booking.save(update_fields=['payment_status'])
                            logger.info(f"Réservation {transaction.booking.id} marquée comme payée")
                
                return payment_data
            
            # 5. Si aucune référence NotchPay valide n'a été trouvée, retourner un statut par défaut
            logger.warning(f"Aucune référence NotchPay valide trouvée pour {payment_reference}")
            return {
                "transaction": {
                    "reference": payment_reference,
                    "status": "pending"
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur dans verify_payment: {str(e)}")
            return {
                "transaction": {
                    "reference": payment_reference,
                    "status": "pending"
                }
            }
    
    def verify_webhook_signature(self, payload, signature_header):
        """
        Vérifier la signature d'un webhook NotchPay
        
        Args:
            payload (str): Le corps de la requête en string
            signature_header (str): La signature dans l'en-tête X-Notch-Signature
            
        Returns:
            bool: True si la signature est valide, False sinon
        """
        if not signature_header or not settings.NOTCHPAY_HASH_KEY:
            return False
        
        # Calculer la signature locale
        computed_signature = hmac.new(
            settings.NOTCHPAY_HASH_KEY.encode('utf-8'),
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
    
    def get_recipients(self):
        """
        Récupérer la liste des destinataires enregistrés dans NotchPay
        
        Returns:
            dict: Liste des destinataires ou objet d'erreur
        """
        try:
            logger.info(f"Récupération des destinataires NotchPay")
            
            # Mettre à jour les en-têtes pour utiliser la clé privée
            headers = self.headers.copy()
            headers['X-Grant'] = self.private_key  # Nécessaire pour les opérations de transfert
            
            response = requests.get(
                f"{self.base_url}/recipients",
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Destinataires NotchPay récupérés avec succès")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la récupération des destinataires NotchPay: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails: {e.response.text}")
            raise

    def create_recipient(self, recipient_data):
        """
        Créer un nouveau destinataire dans NotchPay pour les versements
        
        Args:
            recipient_data (dict): Données du destinataire selon l'API réelle NotchPay
                - channel: Canal de paiement (cm.mobile, cm.orange, cm.mtn) - obligatoire
                - account_number: Numéro pour recevoir les fonds (format +237656019261) - obligatoire
                - phone: Numéro de téléphone de contact - optionnel
                - email: Email du destinataire - obligatoire
                - country: Code pays ISO (CM) - obligatoire
                - name: Nom du destinataire - obligatoire
                - description: Description - optionnel
                - reference: Référence unique - optionnel
                
        Returns:
            dict: Informations sur le destinataire créé
        """
        try:
            logger.info(f"Création d'un destinataire NotchPay")
            logger.info(f"Données envoyées: {recipient_data}")
            
            # Mettre à jour les en-têtes pour utiliser la clé privée
            headers = self.headers.copy()
            headers['X-Grant'] = self.private_key  # Nécessaire pour les opérations de transfert
            
            # Vérifier que les champs obligatoires sont présents
            # Selon l'API réelle NotchPay: channel, account_number, email, country, name
            required_fields = ['channel', 'account_number', 'email', 'country', 'name']
            missing_fields = [field for field in required_fields if field not in recipient_data or not recipient_data[field]]
            
            if missing_fields:
                logger.error(f"Champs obligatoires manquants: {missing_fields}")
                raise ValueError(f"Les champs suivants sont obligatoires : {', '.join(missing_fields)}")
            
            response = requests.post(
                f"{self.base_url}/recipients",
                json=recipient_data,
                headers=headers
            )
            
            # Log de la réponse complète
            logger.info(f"Réponse NotchPay - Status: {response.status_code}")
            try:
                response_data = response.json()
                logger.info(f"Réponse NotchPay - Body: {response_data}")
            except:
                logger.info(f"Réponse NotchPay - Body: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            if 'data' in result:
                logger.info(f"Destinataire NotchPay créé avec succès: {result.get('data', {}).get('id')}")
                return result.get('data')
            else:
                logger.warning(f"Format de réponse inattendu: {result}")
                return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la création du destinataire NotchPay: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails: {e.response.text}")
            raise

    def initiate_transfer(self, amount, currency, recipient, description=None, metadata=None, reference=None):
        """
        Initier un transfert vers un destinataire via NotchPay
        
        Args:
            amount (float): Montant à transférer
            currency (str): Code de devise (ex: XAF)
            recipient (str): ID du destinataire NotchPay
            description (str, optional): Description du transfert
            metadata (dict, optional): Métadonnées supplémentaires
            reference (str, optional): Référence externe
                
        Returns:
            dict: Réponse de l'API NotchPay contenant les détails du transfert
        """
        try:
            # Générer une référence unique si non fournie
            if not reference:
                reference = f"findam-transfer-{uuid.uuid4().hex[:8]}-{int(timezone.now().timestamp())}"
            
            # Préparer le corps de la requête
            payload = {
                "currency": currency,
                "amount": float(amount),
                "recipient": recipient,
                "description": description or "Versement via Findam",
                "statement": "Versement Findam",  # Texte court pour les relevés bancaires
                "reference": reference
            }
            
            # Ajouter les métadonnées si fournies
            if metadata:
                payload["metadata"] = metadata
            
            logger.info(f"Initiation de transfert NotchPay: {amount} {currency} à {recipient}")
            
            # Mettre à jour les en-têtes pour utiliser la clé privée
            headers = self.headers.copy()
            headers['X-Grant'] = self.private_key  # Nécessaire pour les opérations de transfert
            
            response = requests.post(
                f"{self.base_url}/transfers",
                json=payload,
                headers=headers
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
            transfer_data = response.json()
            
            logger.info(f"Transfert NotchPay initié avec succès: {transfer_data.get('transaction', {}).get('reference')}")
            return transfer_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de l'initiation du transfert NotchPay: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails: {e.response.text}")
            raise

    def get_transfer(self, transfer_reference):
        """
        Récupérer les détails d'un transfert
        
        Args:
            transfer_reference (str): Référence du transfert
                
        Returns:
            dict: Informations sur le transfert
        """
        try:
            logger.info(f"Récupération des détails du transfert: {transfer_reference}")
            
            # Mettre à jour les en-têtes pour utiliser la clé privée
            headers = self.headers.copy()
            headers['X-Grant'] = self.private_key  # Nécessaire pour les opérations de transfert
            
            response = requests.get(
                f"{self.base_url}/transfers/{transfer_reference}",
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Détails du transfert récupérés avec succès: {transfer_reference}")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la récupération des détails du transfert {transfer_reference}: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails: {e.response.text}")
            raise
    
    def process_refund(self, payment_reference, amount, description=None, metadata=None, customer_info=None):
        """
        Traite un remboursement pour un paiement existant via NotchPay
        
        Args:
            payment_reference (str): Référence du paiement original
            amount (float): Montant à rembourser
            description (str, optional): Description du remboursement
            metadata (dict, optional): Métadonnées supplémentaires
            customer_info (dict, optional): Informations sur le client (email, phone, name)
            
        Returns:
            dict: Résultat du remboursement
        """
        try:
            logger.info(f"Initiation du remboursement pour la transaction {payment_reference} - Montant: {amount}")
            
            # Préparer le corps de la requête
            payload = {
                "currency": "XAF",         # Devise (obligatoire)
                "amount": float(amount),   # Montant à rembourser
                "reference": f"refund-{payment_reference}-{int(timezone.now().timestamp())}", # Référence unique
                "description": description or "Remboursement",
                "transaction_type": "refund", # Indiquer qu'il s'agit d'un remboursement
                "refund_reference": payment_reference, # Référence du paiement original
            }
            
            # CORRECTION: Ajouter les informations client (obligatoires selon l'erreur 422)
            if customer_info:
                if 'email' in customer_info and customer_info['email']:
                    payload["email"] = customer_info['email']
                if 'phone' in customer_info and customer_info['phone']:
                    payload["phone"] = customer_info['phone']
                if 'name' in customer_info and customer_info['name']:
                    payload["customer_name"] = customer_info['name']
                
                # Ajouter également le client complet si disponible
                payload["customer"] = {
                    "email": customer_info.get('email', ''),
                    "phone": customer_info.get('phone', ''),
                    "name": customer_info.get('name', '')
                }
            
            # Ajouter les métadonnées si fournies
            if metadata:
                payload["metadata"] = metadata
            
            # Log de la requête
            logger.info(f"Requête de remboursement NotchPay: {payload}")
            
            # Effectuer la requête de création de paiement (remboursement)
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
            refund_data = response.json()
            
            logger.info(f"Remboursement NotchPay initié avec succès: {refund_data.get('transaction', {}).get('reference')}")
            return refund_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors du remboursement NotchPay: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Détails de la réponse en erreur: {e.response.status_code}")
                try:
                    logger.error(f"Contenu de la réponse en erreur: {e.response.json()}")
                except:
                    logger.error(f"Contenu de la réponse en erreur: {e.response.text}")
            raise