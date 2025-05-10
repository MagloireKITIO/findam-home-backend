# payments/services/payout_service.py
# Service pour gérer les versements programmés (anti-escrow)

import logging
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from ..models import Payout, Transaction, PaymentMethod
from bookings.models import Booking
from .notchpay_service import NotchPayService

logger = logging.getLogger('findam')

class PayoutService:
    """
    Service pour gérer les versements aux propriétaires avec système d'anti-escrow.
    Gère le cycle de vie complet des versements depuis leur programmation jusqu'à
    leur exécution via NotchPay.
    """
    
    @classmethod
    def schedule_payout_for_booking(cls, booking):
        """
        Programme un versement pour une réservation.
        
        Args:
            booking (Booking): Réservation pour laquelle programmer un versement
            
        Returns:
            Payout: Versement programmé ou None en cas d'erreur
        """
        if not booking or booking.status not in ['confirmed', 'completed']:
            logger.warning(f"Tentative de programmer un versement pour une réservation non confirmée: {booking.id if booking else 'None'}")
            return None
            
        if booking.payment_status != 'paid':
            logger.warning(f"Tentative de programmer un versement pour une réservation non payée: {booking.id}")
            return None
        
        try:
            # Vérifier si un versement existe déjà pour cette réservation
            existing_payout = Payout.objects.filter(
                bookings__id=booking.id,
                status__in=['pending', 'scheduled', 'ready', 'processing']
            ).first()
            
            if existing_payout:
                logger.info(f"Un versement existe déjà pour la réservation {booking.id}: {existing_payout.id}")
                return existing_payout
            
            # Calculer la date de versement (24h après check-in)
            check_in_datetime = timezone.make_aware(
                timezone.datetime.combine(booking.check_in_date, timezone.datetime.min.time())
            )
            scheduled_date = check_in_datetime + timezone.timedelta(hours=24)
            
            # Programmer le versement
            payout = Payout.schedule_for_booking(booking, scheduled_date)
            logger.info(f"Versement programmé pour la réservation {booking.id}: {payout.id}, date: {scheduled_date}")
            
            return payout
            
        except Exception as e:
            logger.exception(f"Erreur lors de la programmation du versement pour la réservation {booking.id}: {str(e)}")
            return None
    
    @classmethod
    def process_scheduled_payouts(cls):
        """
        Traite tous les versements programmés qui sont maintenant dus.
        Change leur statut de 'scheduled' à 'ready'.
        """
        current_time = timezone.now()
        scheduled_payouts = Payout.objects.filter(
            status='scheduled',
            scheduled_at__lte=current_time
        )
        
        count = 0
        for payout in scheduled_payouts:
            try:
                payout.mark_as_ready()
                count += 1
                logger.info(f"Versement {payout.id} marqué comme prêt à être traité")
            except Exception as e:
                logger.exception(f"Erreur lors du traitement du versement programmé {payout.id}: {str(e)}")
        
        return count
    
    @classmethod
    def process_ready_payouts(cls):
        """
        Traite tous les versements prêts à être versés.
        Effectue les paiements via NotchPay et met à jour les statuts.
        """
        ready_payouts = Payout.objects.filter(status='ready')
        count_success = 0
        count_failed = 0
        
        notchpay_service = NotchPayService()
        
        for payout in ready_payouts:
            try:
                with transaction.atomic():
                    # Marquer comme en cours de traitement
                    payout.status = 'processing'
                    payout.save(update_fields=['status'])
                    
                    # Récupérer les informations de paiement du propriétaire
                    payment_method = payout.payment_method
                    
                    # Si aucune méthode de paiement n'est spécifiée, utiliser la méthode par défaut
                    if not payment_method:
                        payment_method = PaymentMethod.objects.filter(
                            user=payout.owner,
                            is_default=True
                        ).first()
                    
                    if not payment_method:
                        logger.error(f"Aucune méthode de paiement trouvée pour le propriétaire {payout.owner.id}")
                        payout.status = 'pending'  # Retour à l'état précédent
                        payout.admin_notes += f"\nÉchec du versement: Aucune méthode de paiement trouvée ({timezone.now().strftime('%Y-%m-%d %H:%M')})"
                        payout.save(update_fields=['status', 'admin_notes'])
                        count_failed += 1
                        continue
                    
                    # Préparer les métadonnées pour le paiement
                    metadata = {
                        'transaction_type': 'payout',
                        'object_id': str(payout.id),
                        'owner_id': str(payout.owner.id),
                    }
                    
                    # Préparer la description du paiement
                    description = f"Versement pour réservation(s) du {payout.period_start} au {payout.period_end}"
                    
                    # Déterminer le canal de paiement
                    payment_channel = cls._get_payment_channel(payment_method)
                    
                    # Préparer les informations du destinataire
                    recipient_data = cls._prepare_recipient_data(payment_method, payout.owner)
                    
                    # Créer ou récupérer l'ID du destinataire dans NotchPay
                    recipient_id = cls._get_or_create_recipient(notchpay_service, recipient_data)
                    
                    if not recipient_id:
                        logger.error(f"Impossible de créer un destinataire NotchPay pour le versement {payout.id}")
                        payout.status = 'pending'
                        payout.admin_notes += f"\nÉchec du versement: Création du destinataire échouée ({timezone.now().strftime('%Y-%m-%d %H:%M')})"
                        payout.save(update_fields=['status', 'admin_notes'])
                        count_failed += 1
                        continue
                    
                    # Effectuer le transfert via NotchPay
                    try:
                        # Cette méthode n'existe pas encore dans NotchPayService, il faudra l'ajouter
                        transfer_result = notchpay_service.initiate_transfer(
                            amount=float(payout.amount),
                            currency=payout.currency,
                            description=description,
                            recipient=recipient_id,
                            metadata=metadata
                        )
                        
                        # Mettre à jour le versement avec la référence externe
                        if transfer_result and 'transaction' in transfer_result:
                            payout.external_reference = transfer_result['transaction'].get('reference', '')
                            payout.mark_as_completed()
                            count_success += 1
                            logger.info(f"Versement {payout.id} effectué avec succès, référence: {payout.external_reference}")
                        else:
                            raise Exception("Réponse NotchPay invalide")
                            
                    except Exception as e:
                        logger.exception(f"Erreur lors du transfert NotchPay pour le versement {payout.id}: {str(e)}")
                        payout.status = 'failed'
                        payout.admin_notes += f"\nÉchec du versement: {str(e)} ({timezone.now().strftime('%Y-%m-%d %H:%M')})"
                        payout.save(update_fields=['status', 'admin_notes'])
                        count_failed += 1
                
            except Exception as e:
                logger.exception(f"Erreur lors du traitement du versement {payout.id}: {str(e)}")
                count_failed += 1
        
        return {
            'success': count_success,
            'failed': count_failed,
            'total': count_success + count_failed
        }
    
    @classmethod
    def _get_payment_channel(cls, payment_method):
        """
        Détermine le canal de paiement NotchPay en fonction de la méthode de paiement.
        """
        if payment_method.payment_type == 'mobile_money':
            if payment_method.operator.lower() == 'orange':
                return 'cm.orange'
            elif payment_method.operator.lower() == 'mtn':
                return 'cm.mtn'
            else:
                return 'cm.mobile'  # Par défaut, utiliser le mobile money générique
        elif payment_method.payment_type == 'bank_account':
            return 'bank'  # À vérifier si NotchPay prend en charge ce canal
        else:
            return 'cm.mobile'  # Canal par défaut
    
    @classmethod
    def _prepare_recipient_data(cls, payment_method, owner):
        """
        Prépare les données du destinataire pour NotchPay.
        """
        recipient_data = {
            'channel': cls._get_payment_channel(payment_method),
            'number': payment_method.phone_number or payment_method.account_number,
            'phone': owner.phone_number,
            'email': owner.email,
            'country': 'CM',  # Code pays pour le Cameroun
            'name': owner.get_full_name() or owner.email,
            'description': f"Propriétaire FINDAM: {owner.email}",
            'reference': f"owner-{owner.id}"
        }
        
        return recipient_data
    
    @classmethod
    def _get_or_create_recipient(cls, notchpay_service, recipient_data):
        """
        Récupère ou crée un destinataire dans NotchPay.
        """
        try:
            # Cette méthode n'existe pas encore dans NotchPayService, il faudra l'ajouter
            recipients = notchpay_service.get_recipients()
            
            # Chercher un destinataire existant avec la même référence
            recipient_id = None
            for recipient in recipients.get('data', []):
                if recipient.get('reference') == recipient_data['reference']:
                    recipient_id = recipient.get('id')
                    break
            
            # Si aucun destinataire trouvé, en créer un nouveau
            if not recipient_id:
                recipient_result = notchpay_service.create_recipient(recipient_data)
                if recipient_result and 'id' in recipient_result:
                    recipient_id = recipient_result['id']
            
            return recipient_id
            
        except Exception as e:
            logger.exception(f"Erreur lors de la création/récupération du destinataire: {str(e)}")
            return None