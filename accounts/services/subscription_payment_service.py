# accounts/services/subscription_payment_service.py
# Service pour le paiement des abonnements

import uuid
import logging
from django.conf import settings
from django.utils import timezone
from payments.services.notchpay_service import NotchPayService
from payments.utils import NotchPayUtils, PaymentStatus
from payments.models import Transaction

logger = logging.getLogger('findam')

class SubscriptionPaymentService:
    """
    Service pour gérer les paiements d'abonnement via NotchPay
    """
    
    @staticmethod
    def initiate_payment(subscription, payment_method='mobile_money', mobile_operator='mobile_money', phone_number=None):
        """
        Initialiser un paiement pour un abonnement propriétaire
        
        Args:
            subscription: L'objet OwnerSubscription à payer
            payment_method: Méthode de paiement (mobile_money, credit_card, bank_transfer)
            mobile_operator: Opérateur mobile (orange, mtn, mobile_money)
            phone_number: Numéro de téléphone pour mobile money
            
        Returns:
            dict: Résultat de l'initialisation du paiement avec URL de redirection
        """
        # Vérifier que l'abonnement est en attente de paiement
        if subscription.status not in ['pending', 'expired']:
            logger.warning(f"Tentative de paiement pour un abonnement au statut {subscription.status}")
            return {
                'success': False,
                'error': "L'abonnement n'est pas en attente de paiement"
            }
        
        # Convertir l'opérateur mobile en code NotchPay
        notchpay_channel = NotchPayUtils.get_mobile_operator_code(mobile_operator)
        
        # Formater le numéro de téléphone si fourni, sinon utiliser celui du propriétaire
        formatted_phone = NotchPayUtils.format_phone_number(phone_number) if phone_number else NotchPayUtils.format_phone_number(subscription.owner.phone_number)
        
        # Préparer les informations client
        customer_info = {
            'email': subscription.owner.email,
            'phone': formatted_phone,
            'name': f"{subscription.owner.first_name} {subscription.owner.last_name}"
        }
        
        # Préparer les métadonnées pour NotchPay
        metadata = {
            'transaction_type': 'subscription',
            'object_id': str(subscription.id),
            'owner_id': str(subscription.owner.id),
            'subscription_type': subscription.subscription_type
        }
        
        # Description du paiement
        description = f"Abonnement {subscription.get_subscription_type_display()} - Findam"
        
        try:
            # Initialiser le service NotchPay
            notchpay_service = NotchPayService()
            
            # Générer une référence unique pour ce paiement
            payment_reference = f"sub-{subscription.id}-{uuid.uuid4().hex[:8]}"
            
            # Calcul du montant selon le type d'abonnement
            # Utilisons la méthode calculate_price si elle existe, ou une logique par défaut
            if hasattr(subscription, 'calculate_price') and callable(getattr(subscription, 'calculate_price')):
                amount = subscription.calculate_price()
            else:
                # Logique par défaut basée sur le type d'abonnement
                subscription_prices = {
                    'free': 0,
                    'monthly': 5000,
                    'quarterly': 12000,
                    'yearly': 40000
                }
                amount = subscription_prices.get(subscription.subscription_type, 0)
            
            # Initialiser le paiement avec NotchPay
            payment_result = notchpay_service.initialize_payment(
                amount=amount,
                currency='XAF',
                description=description,
                customer_info=customer_info,
                metadata=metadata,
                reference=payment_reference
            )
            
            # Vérifier le résultat
            if payment_result and 'transaction' in payment_result:
                # Stocker la référence externe pour suivi ultérieur
                subscription.payment_reference = payment_result['transaction'].get('reference', '')
                subscription.save(update_fields=['payment_reference'])
                
                # Créer une transaction financière
                Transaction.objects.create(
                    user=subscription.owner,
                    transaction_type='subscription',
                    status='pending',
                    amount=amount,
                    currency='XAF',
                    external_reference=payment_result['transaction'].get('reference', ''),
                    description=f"Paiement de l'abonnement {subscription.get_subscription_type_display()}"
                )
                
                logger.info(f"Paiement d'abonnement initialisé: {subscription.id} - {payment_result['transaction'].get('reference')}")
                
                # Retourner les détails du paiement avec l'URL pour redirection
                return {
                    'success': True,
                    'payment_url': payment_result.get('authorization_url', ''),
                    'notchpay_reference': payment_result['transaction'].get('reference', ''),
                    'subscription_id': str(subscription.id)
                }
            else:
                logger.error(f"Réponse NotchPay invalide pour l'abonnement {subscription.id}")
                return {
                    'success': False,
                    'error': "Erreur lors de l'initialisation du paiement"
                }
                
        except Exception as e:
            logger.exception(f"Erreur lors de l'initialisation du paiement d'abonnement {subscription.id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def check_payment_status(subscription):
        """
        Vérifier le statut du paiement d'un abonnement
        
        Args:
            subscription: L'objet OwnerSubscription à vérifier
            
        Returns:
            dict: Statut actuel du paiement
        """
        if not subscription.payment_reference:
            return {
                'status': 'pending',
                'message': "Aucune référence de paiement trouvée"
            }
            
        try:
            # Initialiser le service NotchPay
            notchpay_service = NotchPayService()
            
            # Vérifier le statut du paiement
            payment_data = notchpay_service.verify_payment(subscription.payment_reference)
            
            # Extraire le statut
            notchpay_status = payment_data.get('transaction', {}).get('status', 'pending')
            
            # Convertir en statut interne
            internal_status = NotchPayUtils.convert_notchpay_status(notchpay_status)
            
            # Si le paiement est complété, activer l'abonnement
            if internal_status == PaymentStatus.COMPLETED and subscription.status == 'pending':
                subscription.status = 'active'
                
                # Calculer la date de fin si ce n'est pas un abonnement gratuit et qu'elle n'est pas déjà définie
                if subscription.subscription_type != 'free' and not subscription.end_date:
                    subscription.end_date = subscription.calculate_end_date()
                    
                subscription.save(update_fields=['status', 'end_date'])
                
                # Mettre à jour la transaction correspondante
                Transaction.objects.filter(
                    external_reference=subscription.payment_reference,
                    transaction_type='subscription'
                ).update(
                    status='completed',
                    processed_at=timezone.now()
                )
                
                logger.info(f"Abonnement {subscription.id} activé après vérification du paiement")
            
            # Si le paiement a échoué, mettre à jour le statut
            elif internal_status == PaymentStatus.FAILED and subscription.status == 'pending':
                subscription.status = 'pending'  # On garde pending pour permettre une nouvelle tentative
                subscription.save(update_fields=['status'])
                
                # Mettre à jour la transaction correspondante
                Transaction.objects.filter(
                    external_reference=subscription.payment_reference,
                    transaction_type='subscription'
                ).update(
                    status='failed'
                )
                
                logger.info(f"Paiement échoué pour l'abonnement {subscription.id}")
            
            return {
                'status': internal_status,
                'subscription_status': subscription.status,
                'details': payment_data.get('transaction', {})
            }
            
        except Exception as e:
            logger.exception(f"Erreur lors de la vérification du paiement d'abonnement {subscription.id}: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }