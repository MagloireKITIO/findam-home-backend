# payments/tasks.py
# Tâches planifiées pour le traitement des versements programmés

import logging
from django.utils import timezone
from bookings.models import Booking
from .services.payout_service import PayoutService

logger = logging.getLogger('findam')

def schedule_payouts_for_new_bookings():
    """
    Tâche planifiée pour créer des versements programmés pour les nouvelles réservations confirmées.
    """
    logger.info("Démarrage de la tâche de programmation des versements pour les nouvelles réservations")
    
    # Récupérer les réservations confirmées et payées qui n'ont pas encore de versement programmé
    eligible_bookings = Booking.objects.filter(
        status='confirmed',
        payment_status='paid'
    ).exclude(
        payouts__status__in=['pending', 'scheduled', 'ready', 'processing']
    )
    
    count = 0
    for booking in eligible_bookings:
        try:
            payout = PayoutService.schedule_payout_for_booking(booking)
            if payout:
                count += 1
        except Exception as e:
            logger.exception(f"Erreur lors de la programmation du versement pour la réservation {booking.id}: {str(e)}")
    
    logger.info(f"Tâche terminée: {count} nouveaux versements programmés")
    return count

def process_scheduled_payouts():
    """
    Tâche planifiée pour traiter les versements programmés qui sont maintenant dus.
    """
    logger.info("Démarrage de la tâche de traitement des versements programmés")
    
    # Mettre à jour les versements programmés qui sont maintenant dus
    count = PayoutService.process_scheduled_payouts()
    
    logger.info(f"Tâche terminée: {count} versements marqués comme prêts à être traités")
    return count

def process_ready_payouts():
    """
    Tâche planifiée pour effectuer les versements prêts via NotchPay.
    """
    logger.info("Démarrage de la tâche d'exécution des versements prêts")
    
    # Effectuer les versements prêts
    result = PayoutService.process_ready_payouts()
    
    logger.info(f"Tâche terminée: {result['success']} versements effectués avec succès, {result['failed']} échoués")
    return result

def check_pending_checkins():
    """
    Tâche planifiée pour vérifier les réservations dont le check-in est passé et
    programmer les versements aux propriétaires.
    """
    logger.info("Démarrage de la tâche de vérification des check-ins")
    
    today = timezone.now().date()
    
    # Récupérer les réservations confirmées dont la date de check-in est passée
    # mais qui n'ont pas encore de versement programmé
    checkin_bookings = Booking.objects.filter(
        status='confirmed',
        payment_status='paid',
        check_in_date__lt=today
    ).exclude(
        payouts__status__in=['scheduled', 'ready', 'processing', 'completed']
    )
    
    count = 0
    for booking in checkin_bookings:
        try:
            # Vérifier si le check-in est passé depuis au moins 24h
            check_in_datetime = timezone.make_aware(
                timezone.datetime.combine(booking.check_in_date, timezone.datetime.min.time())
            )
            checkin_passed_24h = (timezone.now() - check_in_datetime).total_seconds() >= 86400  # 24h en secondes
            
            if checkin_passed_24h:
                # Programmer un versement immédiat
                payout = PayoutService.schedule_payout_for_booking(booking)
                if payout:
                    # Marquer directement comme prêt (puisque les 24h sont déjà passées)
                    payout.mark_as_ready()
                    count += 1
                    logger.info(f"Versement marqué comme prêt pour la réservation {booking.id} avec check-in passé")
        except Exception as e:
            logger.exception(f"Erreur lors du traitement du check-in pour la réservation {booking.id}: {str(e)}")
    
    logger.info(f"Tâche terminée: {count} versements programmés pour des check-ins passés")
    return count

# Pour l'exécution régulière des tâches, vous pouvez utiliser:
# - Django Crontab: https://github.com/kraiz/django-crontab
# - Celery: https://docs.celeryproject.org/en/stable/django/first-steps-with-django.html

# Exemple de configuration avec Django Crontab:
# Dans settings.py:
# CRONJOBS = [
#     ('0 */4 * * *', 'payments.tasks.schedule_payouts_for_new_bookings'),  # Toutes les 4 heures
#     ('0 */2 * * *', 'payments.tasks.process_scheduled_payouts'),          # Toutes les 2 heures
#     ('0 */3 * * *', 'payments.tasks.process_ready_payouts'),              # Toutes les 3 heures
#     ('0 12 * * *', 'payments.tasks.check_pending_checkins'),              # Tous les jours à midi
# ]