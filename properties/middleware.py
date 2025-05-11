# properties/middleware.py
# Middleware pour la validation des limites d'abonnement

from django.utils import timezone
from django.db.models import Count
from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied
from properties.models import Property
from accounts.models import OwnerSubscription

class SubscriptionLimitValidator:
    """
    Classe utilitaire pour valider les limites d'abonnement des propriétaires.
    Cette classe est utilisée pour vérifier si un propriétaire a atteint
    la limite de logements autorisés par son abonnement.
    """
    
    @staticmethod
    def get_property_limit(subscription_type):
        """
        Retourne le nombre maximal de logements autorisés pour un type d'abonnement.
        
        Args:
            subscription_type (str): Type d'abonnement (free, monthly, quarterly, yearly)
            
        Returns:
            int: Nombre maximal de logements autorisés
        """
        # Modification: Tous les abonnements ont maintenant une limite infinie
        return float('inf')  # Illimité pour tous les plans
        
        # Code commenté - ancienne version avec limites
        # limits = {
        #     'free': 1,
        #     'monthly': 5,
        #     'quarterly': 10,
        #     'yearly': float('inf')  # Illimité
        # }
        # return limits.get(subscription_type, 0)
    
    @staticmethod
    def validate_property_creation(owner):
        """
        Vérifie si un propriétaire peut créer un nouveau logement
        en fonction des limites de son abonnement actif.
        
        Args:
            owner: L'utilisateur propriétaire
            
        Raises:
            PermissionDenied: Si le propriétaire a atteint la limite de logements
        """
        # Modification: Ne plus vérifier les limites d'abonnement
        # Cette fonction ne fait plus rien - tous les propriétaires peuvent créer autant de logements qu'ils veulent
        return
        
        # Code commenté - ancienne logique de validation
        # # Récupérer l'abonnement actif du propriétaire
        # active_subscription = OwnerSubscription.objects.filter(
        #     owner=owner,
        #     status='active',
        #     end_date__gt=timezone.now()
        # ).first()
        # 
        # # Si pas d'abonnement actif, utiliser le plan gratuit par défaut
        # subscription_type = 'free'
        # if active_subscription:
        #     subscription_type = active_subscription.subscription_type
        # 
        # # Récupérer la limite de logements pour ce type d'abonnement
        # property_limit = SubscriptionLimitValidator.get_property_limit(subscription_type)
        # 
        # # Compter le nombre de logements du propriétaire
        # property_count = Property.objects.filter(owner=owner).count()
        # 
        # # Vérifier si la limite est atteinte
        # if property_count >= property_limit:
        #     if subscription_type == 'free':
        #         message = _("Vous avez atteint la limite de {} logement pour l'abonnement gratuit. Veuillez souscrire à un plan payant pour ajouter plus de logements.").format(property_limit)
        #     else:
        #         message = _("Vous avez atteint la limite de {} logements pour votre abonnement {}. Veuillez passer à un plan supérieur pour ajouter plus de logements.").format(
        #             property_limit, 
        #             SubscriptionLimitValidator.get_subscription_display(subscription_type)
        #         )
        #     
        #     raise PermissionDenied(message)
    
    @staticmethod
    def get_subscription_display(subscription_type):
        """
        Retourne l'affichage lisible d'un type d'abonnement.
        
        Args:
            subscription_type (str): Type d'abonnement
            
        Returns:
            str: Nom lisible de l'abonnement
        """
        displays = {
            'free': _('Gratuit'),
            'monthly': _('Mensuel'),
            'quarterly': _('Trimestriel'),
            'yearly': _('Annuel')
        }
        
        return displays.get(subscription_type, subscription_type)