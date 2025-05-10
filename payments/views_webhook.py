# payments/views_webhook.py
# Vues pour gérer les webhooks de paiement

import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.conf import settings
from .models import Transaction, PaymentMethod
from bookings.models import Booking, PaymentTransaction
from accounts.models import OwnerSubscription
from .services.notchpay_service import NotchPayService
from .utils import NotchPayUtils, PaymentStatus
from django.views.decorators.http import require_http_methods
from django.shortcuts import redirect

logger = logging.getLogger('findam')

@csrf_exempt
@require_http_methods(["POST", "GET"]) 
def notchpay_webhook(request):
    """
    Endpoint pour recevoir les notifications de paiement de NotchPay.
    Ce webhook est appelé par NotchPay lorsque le statut d'un paiement change.
    Gère également les redirections après paiement (requêtes GET).
    """
    # Si c'est une requête GET (redirection après paiement)
    if request.method == "GET":
        # Récupérer les paramètres
        reference = request.GET.get('reference')
        status = request.GET.get('status')
        trxref = request.GET.get('trxref')
        
        logger.info(f"Redirection de paiement NotchPay: ref={reference}, status={status}, trxref={trxref}")
        
        # Analyser trxref pour extraire l'ID de réservation ou d'abonnement
        redirect_url = settings.FRONTEND_URL
        
        if trxref and trxref.startswith('booking-'):
            # Format: booking-UUID-transaction_id
            parts = trxref.split('-')
            if len(parts) >= 5:  # S'assurer qu'il y a assez de parties pour un UUID complet
                booking_id = f"{parts[1]}-{parts[2]}-{parts[3]}-{parts[4]}-{parts[5]}"
                # Utilisez le format de l'URL qui inclut l'ID complet
                redirect_url = f"{settings.FRONTEND_URL}/bookings/{booking_id}?payment_status={status}"
        
        # Rediriger vers la page appropriée
        return redirect(redirect_url)
    
    # Pour les requêtes POST (webhook)
    # Récupérer la signature dans l'en-tête
    signature = request.headers.get('X-Notch-Signature', '')
    
    # Récupérer le corps de la requête comme une chaîne
    payload_str = request.body.decode('utf-8')
    
    # Initialiser le service NotchPay
    notchpay_service = NotchPayService()
    
    # Vérifier la signature
    if signature and not notchpay_service.verify_webhook_signature(payload_str, signature):
        logger.warning(f"Signature de webhook NotchPay invalide: {signature}")
        logger.debug(f"Payload reçu (début): {payload_str[:100]}...")
        logger.debug(f"NOTCHPAY_HASH_KEY configurée: {settings.NOTCHPAY_HASH_KEY[:10]}...")
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
        logger.error(f"Impossible de décoder le payload JSON du webhook: {payload_str}")
        return HttpResponse("Invalid JSON", status=400)
    except Exception as e:
        logger.exception(f"Erreur lors du traitement du webhook NotchPay: {str(e)}")
        return HttpResponse("Internal server error", status=500)

@transaction.atomic
def handle_payment_success(data):
    """Traiter un paiement réussi notifié par NotchPay"""
    notchpay_reference = data.get('reference')
    merchant_reference = data.get('merchant_reference', '')
    
    # Mettre à jour directement toutes les transactions correspondantes
    from bookings.models import PaymentTransaction, Booking
    
    # 1. Chercher par référence NotchPay dans payment_response
    transactions_updated = False
    
    # Parcourir toutes les transactions récentes en attente
    for transaction in PaymentTransaction.objects.filter(status__in=['pending', 'processing']).order_by('-created_at')[:50]:
        if transaction.payment_response and isinstance(transaction.payment_response, dict):
            tx_reference = transaction.payment_response.get('transaction', {}).get('reference')
            if tx_reference == notchpay_reference:
                # Mettre à jour le statut
                transaction.status = 'completed'
                transaction.save(update_fields=['status'])
                
                # Mettre à jour la réservation
                if transaction.booking:
                    transaction.booking.payment_status = 'paid'
                    transaction.booking.save(update_fields=['payment_status'])
                    
                transactions_updated = True
                logger.info(f"Transaction {transaction.id} et réservation {transaction.booking.id} mises à jour via webhook")
    
    # Si aucune transaction n'a été mise à jour, essayer d'extraire l'ID de réservation du merchant_reference
    if not transactions_updated and merchant_reference and merchant_reference.startswith('booking-'):
        parts = merchant_reference.split('-')
        if len(parts) >= 5:
            try:
                booking_id = f"{parts[1]}-{parts[2]}-{parts[3]}-{parts[4]}"
                booking = Booking.objects.get(id=booking_id)
                
                # Mettre à jour le statut de paiement
                booking.payment_status = 'paid'
                booking.save(update_fields=['payment_status'])
                
                # Mettre à jour la transaction associée
                tx = booking.transactions.order_by('-created_at').first()
                if tx:
                    tx.status = 'completed'
                    tx.save(update_fields=['status'])
                
                logger.info(f"Réservation {booking.id} mise à jour via merchant_reference")
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour via merchant_reference: {str(e)}")
    
    elif transaction_type == 'subscription':
        # Traitement des abonnements
        try:
            # Rechercher l'abonnement par ID ou référence
            subscription = None
            
            # D'abord, essayer de trouver par ID
            if object_id:
                try:
                    subscription = OwnerSubscription.objects.get(id=object_id)
                except OwnerSubscription.DoesNotExist:
                    logger.warning(f"Abonnement non trouvé avec ID {object_id}")
            
            # Si non trouvé par ID, essayer par référence de paiement
            if not subscription and notchpay_reference:
                subscription = OwnerSubscription.objects.filter(
                    payment_reference=notchpay_reference
                ).first()
            
            # Si toujours pas trouvé, essayer par référence marchande
            if not subscription and merchant_reference:
                subscription = OwnerSubscription.objects.filter(
                    payment_reference=merchant_reference
                ).first()
            
            if not subscription:
                logger.error(f"Impossible de trouver l'abonnement pour l'ID {object_id} ou la référence {notchpay_reference}")
                return
            
            # Vérifier l'état actuel avant de modifier
            current_status = subscription.status
            logger.info(f"État actuel de l'abonnement {subscription.id}: {current_status}")
            
            # Activer l'abonnement seulement s'il n'est pas déjà actif
            if subscription.status != 'active':
                # Mettre à jour le statut et la référence de paiement
                subscription.status = 'active'
                subscription.payment_reference = notchpay_reference
                
                # Calculer la date de fin si ce n'est pas déjà fait
                if not subscription.end_date and subscription.subscription_type != 'free':
                    subscription.end_date = subscription.calculate_end_date()
                    
                subscription.save(update_fields=['status', 'end_date', 'payment_reference'])
                logger.info(f"Abonnement {subscription.id} activé suite au paiement réussi (notchpay_reference: {notchpay_reference})")
                
                # Créer ou mettre à jour la transaction financière
                transaction, created = Transaction.objects.update_or_create(
                    external_reference=notchpay_reference,
                    transaction_type='subscription',
                    defaults={
                        'user': subscription.owner,
                        'status': 'completed',
                        'amount': subscription.calculate_price(),
                        'currency': 'XAF',
                        'description': f"Paiement de l'abonnement {subscription.get_subscription_type_display()}",
                        'processed_at': subscription.updated_at
                    }
                )
                
                logger.info(f"Transaction financière {transaction.id} créée/mise à jour pour l'abonnement {subscription.id}")
            else:
                logger.info(f"L'abonnement {subscription.id} est déjà actif, aucune action nécessaire")
            
        except Exception as e:
            logger.exception(f"Erreur lors du traitement du paiement réussi pour l'abonnement: {str(e)}")
    
    else:
        logger.warning(f"Type de transaction non reconnu: {transaction_type}")

@transaction.atomic
def handle_payment_failed(data):
    """
    Traiter un paiement échoué notifié par NotchPay
    """
    notchpay_reference = data.get('reference')
    merchant_reference = data.get('merchant_reference', '')
    metadata = data.get('metadata', {})
    
    # Identifier le type de transaction
    transaction_type = metadata.get('transaction_type')
    object_id = metadata.get('object_id')
    
    logger.info(f"Traitement du paiement échoué: {notchpay_reference}, type: {transaction_type}")
    
    if transaction_type == 'booking':
        # Traitement des réservations
        try:
            # Trouver la réservation concernée
            booking = None
            if object_id:
                try:
                    booking = Booking.objects.get(id=object_id)
                except Booking.DoesNotExist:
                    logger.warning(f"Réservation non trouvée avec ID {object_id}")
            
            # Si pas trouvé par ID, essayer par référence marchande
            if not booking and merchant_reference and merchant_reference.startswith('booking-'):
                booking_id = merchant_reference.split('-')[1]
                if booking_id:
                    try:
                        booking = Booking.objects.get(id=booking_id)
                    except Booking.DoesNotExist:
                        logger.warning(f"Réservation non trouvée avec ID extrait {booking_id}")
            
            if not booking:
                logger.error(f"Booking introuvable pour la référence {object_id} ou {merchant_reference}")
                return
            
            # Mettre à jour le statut de paiement
            booking.payment_status = 'failed'
            booking.save(update_fields=['payment_status'])
            
            # Mettre à jour la transaction de paiement
            payment_transaction = PaymentTransaction.objects.filter(booking=booking).order_by('-created_at').first()
            
            if payment_transaction:
                payment_transaction.status = 'failed'
                # Stocker la réponse complète du webhook
                payment_response = payment_transaction.payment_response or {}
                payment_response.update({"webhook_notification": data})
                payment_transaction.payment_response = payment_response
                payment_transaction.save(update_fields=['status', 'payment_response'])
            
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
                }
            )
            
            logger.info(f"Réservation {booking.id} marquée comme paiement échoué")
            
        except Exception as e:
            logger.exception(f"Erreur lors du traitement du paiement échoué pour la réservation: {str(e)}")
    
    elif transaction_type == 'subscription':
        # Traitement des abonnements
        try:
            # Rechercher l'abonnement
            subscription = None
            if object_id:
                try:
                    subscription = OwnerSubscription.objects.get(id=object_id)
                except OwnerSubscription.DoesNotExist:
                    logger.warning(f"Abonnement non trouvé avec ID {object_id}")
            
            # Si non trouvé, essayer par référence
            if not subscription and (notchpay_reference or merchant_reference):
                ref_to_use = notchpay_reference or merchant_reference
                subscription = OwnerSubscription.objects.filter(
                    payment_reference=ref_to_use
                ).first()
            
            if not subscription:
                logger.error(f"Abonnement introuvable pour la référence {object_id} ou {notchpay_reference}")
                return
            
            # Mettre à jour le statut de l'abonnement
            subscription.status = 'pending'  # Remettre en attente pour permettre une nouvelle tentative
            subscription.save(update_fields=['status'])
            
            # Créer ou mettre à jour la transaction financière
            transaction, created = Transaction.objects.update_or_create(
                external_reference=notchpay_reference,
                transaction_type='subscription',
                defaults={
                    'user': subscription.owner,
                    'status': 'failed',
                    'amount': subscription.calculate_price(),
                    'currency': 'XAF',
                    'description': f"Paiement échoué de l'abonnement {subscription.get_subscription_type_display()}",
                }
            )
            
            logger.info(f"Abonnement {subscription.id} - paiement échoué")
            
        except Exception as e:
            logger.exception(f"Erreur lors du traitement du paiement échoué pour l'abonnement: {str(e)}")

@transaction.atomic
def handle_payment_pending(data):
    """
    Traiter un paiement en attente notifié par NotchPay
    """
    notchpay_reference = data.get('reference')
    merchant_reference = data.get('merchant_reference', '')
    metadata = data.get('metadata', {})
    
    # Identifier le type de transaction
    transaction_type = metadata.get('transaction_type')
    object_id = metadata.get('object_id')
    
    logger.info(f"Notification de paiement en attente reçue: {notchpay_reference}, type: {transaction_type}")
    
    # Pour les paiements en attente, nous pouvons mettre à jour nos enregistrements avec la référence NotchPay
    # pour faciliter le suivi ultérieur
    
    if transaction_type == 'booking' and object_id:
        try:
            booking = Booking.objects.get(id=object_id)
            payment_transaction = PaymentTransaction.objects.filter(booking=booking).order_by('-created_at').first()
            
            if payment_transaction:
                payment_transaction.transaction_id = notchpay_reference
                payment_response = payment_transaction.payment_response or {}
                payment_response.update({"webhook_notification": data})
                payment_transaction.payment_response = payment_response
                payment_transaction.save(update_fields=['transaction_id', 'payment_response'])
                logger.info(f"Transaction {payment_transaction.id} mise à jour avec la référence NotchPay {notchpay_reference}")
        except Booking.DoesNotExist:
            logger.warning(f"Réservation {object_id} non trouvée pour la notification de paiement en attente")
        except Exception as e:
            logger.exception(f"Erreur lors de la mise à jour de la transaction pour la réservation {object_id}: {str(e)}")
    
    elif transaction_type == 'subscription' and object_id:
        try:
            subscription = OwnerSubscription.objects.get(id=object_id)
            subscription.payment_reference = notchpay_reference
            subscription.save(update_fields=['payment_reference'])
            logger.info(f"Abonnement {subscription.id} mis à jour avec la référence NotchPay {notchpay_reference}")
        except OwnerSubscription.DoesNotExist:
            logger.warning(f"Abonnement {object_id} non trouvé pour la notification de paiement en attente")
        except Exception as e:
            logger.exception(f"Erreur lors de la mise à jour de l'abonnement {object_id}: {str(e)}")