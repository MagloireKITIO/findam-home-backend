# bookings/signals.py
# Gestionnaires de signaux pour automatiser les versements lors des changements de statut de réservation

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Booking, PaymentTransaction
from django.db.models.signals import pre_delete


logger = logging.getLogger('findam')

@receiver(post_save, sender=Booking)
def handle_booking_status_change(sender, instance, created, **kwargs):
    """
    Gère les changements de statut d'une réservation pour programmer des versements.
    """
    if created:
        # Ne rien faire pour les nouvelles réservations
        return
    
    # Vérifier si le statut est 'confirmed' et le paiement est 'paid'
    if instance.status == 'confirmed' and instance.payment_status == 'paid':
        try:
            # Vérifier s'il existe déjà un versement programmé
            from payments.models import Payout
            existing_payout = Payout.objects.filter(
                bookings__id=instance.id,
                status__in=['pending', 'scheduled', 'ready', 'processing', 'completed']
            ).exists()
            
            if not existing_payout:
                # Programmer un versement pour 24h après le check-in
                from payments.services.payout_service import PayoutService
                payout = PayoutService.schedule_payout_for_booking(instance)
                
                if payout:
                    logger.info(f"Versement programmé automatiquement pour la réservation {instance.id}, statut: {payout.status}")
        
        except Exception as e:
            logger.exception(f"Erreur lors de la programmation du versement pour la réservation {instance.id}: {str(e)}")
    
    # Si la réservation est marquée comme terminée
    elif instance.status == 'completed' and instance.payment_status == 'paid':
        try:
            # Vérifier s'il existe un versement programmé
            from payments.models import Payout
            payout = Payout.objects.filter(
                bookings__id=instance.id,
                status__in=['pending', 'scheduled']
            ).first()
            
            if payout:
                # Marquer le versement comme prêt
                payout.mark_as_ready()
                payout.admin_notes += f"\nVersement marqué comme prêt suite à complétion de la réservation (signal)"
                payout.save(update_fields=['admin_notes'])
                logger.info(f"Versement {payout.id} marqué comme prêt suite à la complétion de la réservation {instance.id}")
            else:
                # S'il n'y a pas de versement, en créer un immédiatement prêt
                from payments.services.payout_service import PayoutService
                payout = PayoutService.schedule_payout_for_booking(instance)
                
                if payout:
                    payout.mark_as_ready()
                    payout.admin_notes += f"\nVersement créé et marqué comme prêt suite à complétion de la réservation (signal)"
                    payout.save(update_fields=['admin_notes'])
                    logger.info(f"Nouveau versement {payout.id} créé et marqué comme prêt pour la réservation {instance.id}")
        
        except Exception as e:
            logger.exception(f"Erreur lors du traitement du versement pour la réservation terminée {instance.id}: {str(e)}")
    
    # Si la réservation est annulée
    elif instance.status == 'cancelled':
        try:
            # Annuler tout versement programmé
            from payments.models import Payout
            payouts = Payout.objects.filter(
                bookings__id=instance.id,
                status__in=['pending', 'scheduled', 'ready']
            )
            
            for payout in payouts:
                payout.cancel(reason=f"Réservation {instance.id} annulée")
                payout.admin_notes += f"\nVersement annulé suite à l'annulation de la réservation (signal)"
                payout.save(update_fields=['admin_notes'])
                logger.info(f"Versement {payout.id} annulé suite à l'annulation de la réservation {instance.id}")
        
        except Exception as e:
            logger.exception(f"Erreur lors de l'annulation des versements pour la réservation {instance.id}: {str(e)}")

@receiver(post_save, sender=PaymentTransaction)
def handle_payment_status_change(sender, instance, created, **kwargs):
    """
    Gère les changements de statut d'une transaction de paiement pour mettre à jour les versements.
    """
    # Ignorer les nouvelles transactions, se concentrer sur les mises à jour de statut
    if created:
        return
    
    # Vérifier si le paiement est maintenant complété
    if instance.status == 'completed' and instance.booking:
        try:
            # Mettre à jour le statut de paiement de la réservation si nécessaire
            booking = instance.booking
            if booking.payment_status != 'paid':
                booking.payment_status = 'paid'
                booking.save(update_fields=['payment_status'])
                logger.info(f"Statut de paiement de la réservation {booking.id} mis à jour à 'paid'")
            
            # Vérifier s'il existe déjà un versement programmé
            from payments.models import Payout
            existing_payout = Payout.objects.filter(
                bookings__id=booking.id,
                status__in=['pending', 'scheduled', 'ready', 'processing', 'completed']
            ).exists()
            
            # Si la réservation est confirmée et qu'il n'y a pas de versement, en programmer un
            if booking.status == 'confirmed' and not existing_payout:
                from payments.services.payout_service import PayoutService
                payout = PayoutService.schedule_payout_for_booking(booking)
                
                if payout:
                    logger.info(f"Versement programmé automatiquement après paiement pour la réservation {booking.id}")
        
        except Exception as e:
            logger.exception(f"Erreur lors de la gestion du changement de statut de paiement pour la transaction {instance.id}: {str(e)}")
    
    # Traiter également les remboursements et les échecs de paiement
    elif instance.status == 'refunded' and instance.booking:
        try:
            # Annuler tout versement programmé
            from payments.models import Payout
            payouts = Payout.objects.filter(
                bookings__id=instance.booking.id,
                status__in=['pending', 'scheduled', 'ready']
            )
            
            for payout in payouts:
                payout.cancel(reason=f"Paiement remboursé pour la réservation {instance.booking.id}")
                payout.admin_notes += f"\nVersement annulé suite au remboursement du paiement (signal)"
                payout.save(update_fields=['admin_notes'])
                logger.info(f"Versement {payout.id} annulé suite au remboursement du paiement pour la réservation {instance.booking.id}")
        
        except Exception as e:
            logger.exception(f"Erreur lors du traitement du remboursement pour la transaction {instance.id}: {str(e)}")

@receiver(pre_delete, sender=Booking)
def cleanup_availability_on_booking_delete(sender, instance, **kwargs):
    """Supprime les objets Availability lorsqu'une réservation est supprimée"""
    from properties.models import Availability
    Availability.objects.filter(booking_id=instance.id).delete()