# payments/views_webhook.py
# Vues pour gérer les webhooks de paiement

import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import Transaction, PaymentMethod
from bookings.models import Booking, PaymentTransaction
from accounts.models import OwnerSubscription
from .services.notchpay_service import NotchPayService
from .utils import NotchPayUtils, PaymentStatus

logger = logging.getLogger('findam')

@csrf_exempt
@require_POST
def notchpay_webhook(request):
    """
    Endpoint pour recevoir les notifications de paiement de NotchPay.
    Ce webhook est appelé par NotchPay lorsque le statut d'un paiement change.
    """
    # Récupérer la signature dans l'en-tête
    signature = request.headers.get('X-Notch-Signature')
    
    # Récupérer le corps de la requête comme une chaîne
    payload_str = request.body.decode('utf-8')
    
    # Initialiser le service NotchPay
    notchpay_service = NotchPayService()
    
    # Vérifier la signature si elle existe
    if signature and not notchpay_service.verify_webhook_signature(payload_str, signature):
        logger.warning("Signature de webhook NotchPay invalide")
        return HttpResponse("Invalid signature", status=400)
    
    try:
        # Analyser le payload JSON
        payload = json.loads(payload_str)
        event_type = payload.get('event')
        event_data = payload.get('data', {})
        
        logger.info(f"Webhook NotchPay reçu: {event_type} - Référence: {event_data.get('reference')}")
        
        # Traiter l'événement selon son type
        if event_type == 'payment.success':
            handle_payment_success(event_data)
        elif event_type == 'payment.failed':
            handle_payment_failed(event_data)
        elif event_type == 'payment.pending':
            handle_payment_pending(event_data)
        else:
            logger.info(f"Type d'événement webhook non géré: {event_type}")
        
        return JsonResponse({"status": "success"})
        
    except json.JSONDecodeError:
        logger.error("Impossible de décoder le payload JSON du webhook")
        return HttpResponse("Invalid JSON", status=400)
    except Exception as e:
        logger.exception(f"Erreur lors du traitement du webhook NotchPay: {str(e)}")
        return HttpResponse("Internal server error", status=500)

@transaction.atomic
def handle_payment_success(data):
    """
    Traiter un paiement réussi notifié par NotchPay
    """
    notchpay_reference = data.get('reference')
    external_reference = data.get('merchant_reference')
    metadata = data.get('metadata', {})
    
    # Identifier le type de transaction basé sur les métadonnées
    transaction_type = metadata.get('transaction_type')
    object_id = metadata.get('object_id')
    
    logger.info(f"Traitement du paiement réussi: {notchpay_reference}, type: {transaction_type}")
    
    if transaction_type == 'booking':
        # Mettre à jour la réservation et créer la transaction financière
        try:
            booking = Booking.objects.get(id=object_id)
            
            # Mettre à jour le statut de paiement de la réservation
            booking.payment_status = 'paid'
            booking.save(update_fields=['payment_status'])
            
            # Mettre à jour la transaction de paiement
            payment_transaction = PaymentTransaction.objects.filter(
                booking=booking, 
                external_reference=external_reference
            ).first()
            
            if payment_transaction:
                payment_transaction.status = 'completed'
                payment_transaction.payment_details = json.dumps(data)
                payment_transaction.save(update_fields=['status', 'payment_details'])
            
            # Créer ou mettre à jour la transaction financière
            transaction, created = Transaction.objects.update_or_create(
                booking=booking,
                transaction_type='payment',
                defaults={
                    'user': booking.tenant,
                    'status': 'completed',
                    'amount': booking.total_price,
                    'currency': 'XAF',
                    'external_reference': notchpay_reference,
                    'description': f"Paiement pour la réservation {booking.id}",
                    'processed_at': booking.updated_at
                }
            )
            
            logger.info(f"Réservation {booking.id} marquée comme payée, transaction {transaction.id} créée/mise à jour")
            
        except Booking.DoesNotExist:
            logger.error(f"Booking introuvable pour la référence {object_id}")
    
    elif transaction_type == 'subscription':
        # Mettre à jour l'abonnement et créer la transaction financière
        try:
            subscription = OwnerSubscription.objects.get(id=object_id)
            
            # Mettre à jour le statut de l'abonnement
            subscription.status = 'active'
            # Calculer la date de fin si ce n'est pas déjà fait
            if not subscription.end_date and subscription.subscription_type != 'free':
                subscription.end_date = subscription.calculate_end_date()
                
            subscription.save(update_fields=['status', 'end_date'])
            
            # Créer ou mettre à jour la transaction financière
            transaction, created = Transaction.objects.update_or_create(
                external_reference=notchpay_reference,
                transaction_type='subscription',
                defaults={
                    'user': subscription.owner,
                    'status': 'completed',
                    'amount': subscription.calculate_price() if hasattr(subscription, 'calculate_price') else 0,
                    'currency': 'XAF',
                    'description': f"Paiement de l'abonnement {subscription.get_subscription_type_display()}",
                    'processed_at': subscription.updated_at
                }
            )
            
            logger.info(f"Abonnement {subscription.id} activé, transaction {transaction.id} créée/mise à jour")
            
        except OwnerSubscription.DoesNotExist:
            logger.error(f"Abonnement introuvable pour la référence {object_id}")
    
    else:
        logger.warning(f"Type de transaction non reconnu: {transaction_type}")

@transaction.atomic
def handle_payment_failed(data):
    """
    Traiter un paiement échoué notifié par NotchPay
    """
    notchpay_reference = data.get('reference')
    external_reference = data.get('merchant_reference')
    metadata = data.get('metadata', {})
    
    # Identifier le type de transaction basé sur les métadonnées
    transaction_type = metadata.get('transaction_type')
    object_id = metadata.get('object_id')
    
    logger.info(f"Traitement du paiement échoué: {notchpay_reference}, type: {transaction_type}")
    
    if transaction_type == 'booking':
        # Mettre à jour la réservation et créer la transaction financière
        try:
            booking = Booking.objects.get(id=object_id)
            
            # Mettre à jour le statut de paiement de la réservation
            booking.payment_status = 'failed'
            booking.save(update_fields=['payment_status'])
            
            # Mettre à jour la transaction de paiement
            payment_transaction = PaymentTransaction.objects.filter(
                booking=booking, 
                external_reference=external_reference
            ).first()
            
            if payment_transaction:
                payment_transaction.status = 'failed'
                payment_transaction.payment_details = json.dumps(data)
                payment_transaction.save(update_fields=['status', 'payment_details'])
            
            # Créer ou mettre à jour la transaction financière
            transaction, created = Transaction.objects.update_or_create(
                booking=booking,
                transaction_type='payment',
                defaults={
                    'user': booking.tenant,
                    'status': 'failed',
                    'amount': booking.total_price,
                    'currency': 'XAF',
                    'external_reference': notchpay_reference,
                    'description': f"Paiement échoué pour la réservation {booking.id}",
                    'processed_at': booking.updated_at
                }
            )
            
            logger.info(f"Réservation {booking.id} marquée comme paiement échoué")
            
        except Booking.DoesNotExist:
            logger.error(f"Booking introuvable pour la référence {object_id}")
    
    elif transaction_type == 'subscription':
        # Mettre à jour l'abonnement et créer la transaction financière
        try:
            subscription = OwnerSubscription.objects.get(id=object_id)
            
            # Mettre à jour le statut de l'abonnement
            subscription.status = 'pending'
            subscription.save(update_fields=['status'])
            
            # Créer ou mettre à jour la transaction financière
            transaction, created = Transaction.objects.update_or_create(
                external_reference=notchpay_reference,
                transaction_type='subscription',
                defaults={
                    'user': subscription.owner,
                    'status': 'failed',
                    'amount': subscription.calculate_price() if hasattr(subscription, 'calculate_price') else 0,
                    'currency': 'XAF',
                    'description': f"Paiement échoué de l'abonnement {subscription.get_subscription_type_display()}",
                    'processed_at': subscription.updated_at
                }
            )
            
            logger.info(f"Abonnement {subscription.id} - paiement échoué")
            
        except OwnerSubscription.DoesNotExist:
            logger.error(f"Abonnement introuvable pour la référence {object_id}")

@transaction.atomic
def handle_payment_pending(data):
    """
    Traiter un paiement en attente notifié par NotchPay
    """
    notchpay_reference = data.get('reference')
    external_reference = data.get('merchant_reference')
    metadata = data.get('metadata', {})
    
    # Pour les paiements en attente, nous ne faisons que loguer l'événement,
    # car notre système considère déjà le paiement comme en attente par défaut
    logger.info(f"Notification de paiement en attente reçue: {notchpay_reference}")
    
    # Nous pourrions mettre à jour des timestamps ou d'autres détails si nécessaire