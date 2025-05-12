# payments/signals.py
# Signals pour tracker les modifications de méthodes de paiement

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import PaymentMethod, PaymentMethodChange

@receiver(post_save, sender=PaymentMethod)
def track_payment_method_changes(sender, instance, created, **kwargs):
    """
    Track les modifications de méthodes de paiement pour les propriétaires
    """
    if instance.user.user_type != 'owner':
        return
    
    if created:
        # Nouvelle méthode créée
        PaymentMethodChange.log_change(
            payment_method=instance,
            change_type='created',
            user=instance.user
        )
    else:
        # Méthode modifiée - récupérer les données précédentes si nécessaire
        # Note: Pour récupérer les données précédentes, il faudrait une approche plus complexe
        # En attendant, on enregistre juste la modification
        PaymentMethodChange.log_change(
            payment_method=instance,
            change_type='updated',
            user=instance.user
        )

@receiver(post_delete, sender=PaymentMethod)
def track_payment_method_deletion(sender, instance, **kwargs):
    """
    Track la suppression d'une méthode de paiement
    """
    if instance.user.user_type != 'owner':
        return
    
    PaymentMethodChange.log_change(
        payment_method=instance,
        change_type='deleted',
        user=instance.user
    )