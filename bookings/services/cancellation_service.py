# bookings/services/cancellation_service.py
# Service pour gérer les annulations et les remboursements associés

from datetime import timedelta
import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import requests
from bookings.models import Booking, PaymentTransaction
from payments.models import Transaction, Payout
from payments.services.notchpay_service import NotchPayService
from common.models import SystemConfiguration

logger = logging.getLogger('findam')

class CancellationService:
    """
    Service pour gérer les annulations de réservations,
    y compris les politiques d'annulation et les remboursements.
    """
    
    # Définition des politiques d'annulation (en jours avant l'arrivée)
    CANCELLATION_POLICIES = {
        'flexible': {
            'full_refund': 1,  # Remboursement total si annulé au moins 1 jour avant
            'partial_refund': 0,  # Remboursement partiel si annulé moins de 1 jour avant
            'partial_rate': Decimal('0.5')  # 50% de remboursement si en zone partielle
        },
        'moderate': {
            'full_refund': 5,  # Remboursement total si annulé au moins 5 jours avant
            'partial_refund': 0,  # Remboursement partiel si annulé moins de 5 jours avant
            'partial_rate': Decimal('0.5')  # 50% de remboursement si en zone partielle
        },
        'strict': {
            'full_refund': 14,  # Remboursement total si annulé au moins 14 jours avant
            'partial_refund': 7,  # Remboursement partiel si annulé entre 7 et 14 jours avant
            'partial_rate': Decimal('0.5')  # 50% de remboursement si en zone partielle
        }
    }
    
    @classmethod
    def cancel_booking(cls, booking, cancelled_by, reason=None):
        """
        Annule une réservation et gère le remboursement selon la politique applicable.
        
        Args:
            booking (Booking): La réservation à annuler
            cancelled_by (User): L'utilisateur qui annule la réservation
            reason (str, optional): La raison de l'annulation
            
        Returns:
            dict: Informations sur l'annulation et le remboursement
        """
        if booking.status in ['cancelled', 'completed']:
            raise ValueError(_("Cette réservation ne peut pas être annulée car elle est déjà terminée ou annulée."))
        
        # Vérifier si la date d'arrivée est déjà passée
        if booking.check_in_date < timezone.now().date():
            raise ValueError(_("Vous ne pouvez pas annuler une réservation dont la date d'arrivée est passée."))
        
        try:
            with transaction.atomic():
                # 1. Calculer le montant à rembourser
                refund_amount, refund_percentage = cls.calculate_refund_amount(booking)
                
                # 1.b Vérifier si annulation pendant période de grâce
                is_within_grace_period = cls._is_within_grace_period(booking)
                
                # 1.c Calculer la compensation propriétaire
                owner_compensation = cls.calculate_owner_compensation(booking, refund_percentage)
                
                # 2. Annuler la réservation
                booking.status = 'cancelled'
                booking.cancelled_at = timezone.now()
                booking.cancelled_by = cancelled_by
                
                # Ajouter la raison et l'info sur la période de grâce dans les notes
                note_text = ""
                if reason:
                    note_text += f"Annulation: {reason}"
                
                if is_within_grace_period:
                    grace_period_minutes = SystemConfiguration.get_value('CANCELLATION_GRACE_PERIOD_MINUTES', '30')
                    if note_text:
                        note_text += "\n"
                    note_text += f"Annulation pendant la période de grâce ({grace_period_minutes} minutes après réservation)."
                
                if note_text:
                    booking.notes = note_text if not booking.notes else f"{booking.notes}\n{note_text}"
                
                booking.save(update_fields=['status', 'cancelled_at', 'cancelled_by', 'notes'])
            
                
                # 3. Réactiver le code promo si utilisé
                if booking.promo_code and not booking.promo_code.is_active:
                    booking.promo_code.is_active = True
                    booking.promo_code.save(update_fields=['is_active'])
                
                # 4. Traiter le remboursement si la réservation était payée
                refund_transaction = None
                refund_reference = None
                
                if booking.payment_status == 'paid' and refund_amount > 0:
                    refund_transaction, refund_reference = cls.process_refund(booking, refund_amount)
                
                # 5. Annuler ou mettre à jour les versements programmés
                payout_status = cls.update_scheduled_payouts(booking)
                
                # 6. Préparer les données de réponse
                result = {
                    "success": True,
                    "booking_id": str(booking.id),
                    "status": "cancelled",
                    "cancelled_at": booking.cancelled_at.isoformat(),
                    "cancelled_by": cancelled_by.email,
                    "refund_info": {
                        "amount": float(refund_amount),
                        "percentage": float(refund_percentage * 100),
                        "transaction_id": str(refund_transaction.id) if refund_transaction else None,
                        "external_reference": refund_reference,
                        "status": refund_transaction.status if refund_transaction else None,
                        "within_grace_period": is_within_grace_period
                    } if refund_amount > 0 else None,
                    "owner_compensation": {
                        "amount": float(owner_compensation),
                        "percentage": float((Decimal('1.0') - refund_percentage) * 100)
                    },
                    "grace_period": {
                        "applied": is_within_grace_period,
                        "minutes": int(SystemConfiguration.get_value('CANCELLATION_GRACE_PERIOD_MINUTES', '30'))
                    }
                }
                
                logger.info(f"Réservation {booking.id} annulée avec succès. Remboursement: {refund_amount} XAF")
                return result
                
        except Exception as e:
            logger.exception(f"Erreur lors de l'annulation de la réservation {booking.id}: {str(e)}")
            raise
    
    @classmethod
    def calculate_refund_amount(cls, booking):
        """
        Calcule le montant à rembourser en fonction de la politique d'annulation.
        Inclut une période de grâce pour les annulations rapides après réservation.
        
        Args:
            booking (Booking): La réservation annulée
            
        Returns:
            tuple: (Montant à rembourser, Pourcentage du remboursement)
        """
        # Si la réservation n'est pas payée, pas de remboursement nécessaire
        if booking.payment_status != 'paid':
            return Decimal('0'), Decimal('0')
        
        # Vérifier si l'annulation intervient pendant la période de grâce
        is_within_grace_period = cls._is_within_grace_period(booking)
        
        # Si on est dans la période de grâce, remboursement total (sauf frais de service)
        if is_within_grace_period:
            refundable_amount = booking.base_price + booking.cleaning_fee
            return refundable_amount, Decimal('1.0')
        
        # Obtenir la politique d'annulation (par défaut: modérée)
        policy_type = booking.property.cancellation_policy if booking.property else 'moderate'
        policy = cls.CANCELLATION_POLICIES.get(policy_type, cls.CANCELLATION_POLICIES['moderate'])
        
        # Calculer les jours restants avant l'arrivée
        today = timezone.now().date()
        days_until_checkin = (booking.check_in_date - today).days
        
        # Déterminer le pourcentage de remboursement selon la politique
        if days_until_checkin >= policy['full_refund']:
            # Remboursement complet
            refund_percentage = Decimal('1.0')
        elif days_until_checkin >= policy['partial_refund']:
            # Remboursement partiel
            refund_percentage = policy['partial_rate']
        else:
            # Pas de remboursement
            refund_percentage = Decimal('0.0')
        
        # Calculer le montant du remboursement (base_price + cleaning_fee, pas de remboursement des frais de service)
        refundable_amount = booking.base_price + booking.cleaning_fee
        refund_amount = refundable_amount * refund_percentage
        
        # Arrondir à l'entier inférieur
        refund_amount = refund_amount.quantize(Decimal('1.'))
        
        return refund_amount, refund_percentage

    @classmethod
    def _is_within_grace_period(cls, booking):
        """
        Vérifie si l'annulation intervient pendant la période de grâce après la réservation.
        
        Args:
            booking (Booking): La réservation à vérifier
            
        Returns:
            bool: True si l'annulation est dans la période de grâce
        """
        # Si la réservation n'est pas annulée ou n'a pas de date d'annulation, retourner False
        if booking.status != 'cancelled' or not booking.cancelled_at:
            return False
        
        # Obtenir la durée de la période de grâce depuis la configuration (par défaut 30 minutes)
        grace_period_minutes = int(SystemConfiguration.get_value('CANCELLATION_GRACE_PERIOD_MINUTES', '30'))
        
        # Calculer la fin de la période de grâce
        grace_period_end = booking.created_at + timedelta(minutes=grace_period_minutes)
        
        # Vérifier si l'annulation est intervenue avant la fin de la période de grâce
        return booking.cancelled_at <= grace_period_end
    
    @classmethod
    def process_refund(cls, booking, refund_amount):
        """
        Traite le remboursement via NotchPay.
        
        Args:
            booking (Booking): La réservation annulée
            refund_amount (Decimal): Le montant à rembourser
            
        Returns:
            tuple: (Transaction de remboursement, Référence externe)
        """
        # Créer d'abord la transaction de remboursement dans notre système
        refund_transaction = Transaction.objects.create(
            user=booking.tenant,
            transaction_type='refund',
            status='processing',
            amount=refund_amount,
            currency='XAF',
            booking=booking,
            description=f"Remboursement pour l'annulation de la réservation {booking.id}"
        )
        
        # Récupérer la transaction de paiement d'origine
        original_payment = PaymentTransaction.objects.filter(
            booking=booking,
            status='completed'
        ).order_by('-created_at').first()

        notchpay_reference = None

        # Si on a une transaction NotchPay originale, tenter d'initier le remboursement
        if original_payment and original_payment.payment_response:
            try:
                # Extraire la référence NotchPay
                original_reference = None
                if isinstance(original_payment.payment_response, dict) and 'transaction' in original_payment.payment_response:
                    original_reference = original_payment.payment_response['transaction'].get('reference')
                    
                if original_reference:
                    # Initialiser le service NotchPay
                    notchpay_service = NotchPayService()
                    
                    # Préparer les informations client pour le remboursement
                    customer_info = {
                        'email': booking.tenant.email,
                        'phone': booking.tenant.phone_number,
                        'name': f"{booking.tenant.first_name} {booking.tenant.last_name}"
                    }
                    
                    try:
                        # Tenter le remboursement via NotchPay avec la nouvelle méthode
                        refund_result = notchpay_service.process_refund(
                            original_reference,
                            float(refund_amount),
                            f"Remboursement annulation réservation {booking.id}",
                            {
                                'booking_id': str(booking.id),
                                'refund_transaction_id': str(refund_transaction.id)
                            },
                            customer_info  # Ajout des informations client
                        )
                        
                        # Mettre à jour la transaction avec la référence NotchPay
                        if refund_result and 'transaction' in refund_result:
                            notchpay_reference = refund_result['transaction'].get('reference')
                            refund_transaction.external_reference = notchpay_reference
                            refund_transaction.status = 'completed'
                            refund_transaction.save(update_fields=['external_reference', 'status'])
                            
                            # Mettre à jour le statut de paiement de la réservation
                            booking.payment_status = 'refunded'
                            booking.save(update_fields=['payment_status'])
                            
                            return refund_transaction, notchpay_reference
                            
                    except Exception as e:
                        logger.warning(f"Erreur lors du remboursement NotchPay, passage en mode manuel: {str(e)}")
                        # En cas d'erreur avec NotchPay, on passe en mode manuel
                        refund_transaction.status = 'pending'
                        refund_transaction.admin_notes = f"Remboursement à traiter manuellement - Erreur NotchPay: {str(e)}"
                        refund_transaction.save(update_fields=['status', 'admin_notes'])
                        # Marquer quand même la réservation comme remboursée pour l'expérience utilisateur
                        booking.payment_status = 'refunded'
                        booking.save(update_fields=['payment_status'])
                        return refund_transaction, None
            
            except Exception as e:
                logger.exception(f"Erreur lors du remboursement pour la réservation {booking.id}: {str(e)}")
                refund_transaction.status = 'pending'
                refund_transaction.admin_notes = f"Remboursement à traiter manuellement - Erreur: {str(e)}"
                refund_transaction.save(update_fields=['status', 'admin_notes'])
                # Marquer quand même la réservation comme remboursée pour l'expérience utilisateur
                booking.payment_status = 'refunded'
                booking.save(update_fields=['payment_status'])
        else:
            # Si on n'a pas de référence NotchPay, marquer comme à traiter manuellement
            refund_transaction.status = 'pending'
            refund_transaction.admin_notes = "Remboursement à traiter manuellement - Pas de référence NotchPay trouvée"
            refund_transaction.save(update_fields=['status', 'admin_notes'])
            # Marquer quand même la réservation comme remboursée pour l'expérience utilisateur
            booking.payment_status = 'refunded'
            booking.save(update_fields=['payment_status'])
        
        return refund_transaction, notchpay_reference
    
    @classmethod
    def update_scheduled_payouts(cls, booking):
        """
        Met à jour ou annule les versements programmés pour une réservation annulée.
        Crée un versement de compensation si nécessaire.
        
        Args:
            booking (Booking): La réservation annulée
                
        Returns:
            dict: Statut de la mise à jour des versements
        """
        # Rechercher les versements programmés pour cette réservation
        payouts = Payout.objects.filter(
            bookings__id=booking.id,
            status__in=['pending', 'scheduled', 'ready']
        )
        
        result = {
            "updated_payouts": [],
            "status": "no_payouts_found",
            "compensation_payout": None
        }
        
        if not payouts.exists():
            # Pas de versement existant, vérifier si une compensation est due
            refund_amount, refund_percentage = cls.calculate_refund_amount(booking)
            owner_compensation = cls.calculate_owner_compensation(booking, refund_percentage)
            
            if owner_compensation > 0:
                # Créer un versement de compensation pour le propriétaire
                result["compensation_payout"] = cls.create_compensation_payout(booking, owner_compensation)
            
            return result
        
        # Calculer la compensation propriétaire
        refund_amount, refund_percentage = cls.calculate_refund_amount(booking)
        owner_compensation = cls.calculate_owner_compensation(booking, refund_percentage)
        
        for payout in payouts:
            # Si le versement ne concerne que cette réservation
            if payout.bookings.count() == 1:
                if owner_compensation > 0:
                    # Mettre à jour le versement avec le montant de compensation
                    old_amount = payout.amount
                    payout.amount = owner_compensation
                    payout.admin_notes += f"\nMontant ajusté suite à l'annulation de la réservation {booking.id}. Ancien montant: {old_amount}, Nouveau montant (compensation): {owner_compensation}"
                    payout.save(update_fields=['amount', 'admin_notes'])
                    
                    result["updated_payouts"].append({
                        "payout_id": str(payout.id),
                        "action": "updated_compensation",
                        "old_amount": float(old_amount),
                        "new_amount": float(owner_compensation)
                    })
                else:
                    # Annuler le versement si aucune compensation
                    payout.cancel(cancelled_by=booking.cancelled_by, reason=f"Annulation de la réservation {booking.id}")
                    result["updated_payouts"].append({
                        "payout_id": str(payout.id),
                        "action": "cancelled"
                    })
            else:
                # Si le versement concerne plusieurs réservations
                all_bookings = payout.bookings.all()
                total_amount = Decimal('0')
                
                # Calculer le nouveau montant total (sans cette réservation)
                for other_booking in all_bookings:
                    if other_booking.id != booking.id:
                        from payments.models import Commission
                        commission = Commission.objects.filter(booking=other_booking).first()
                        if not commission:
                            commission = Commission.calculate_for_booking(other_booking)
                        
                        booking_amount = other_booking.total_price - commission.owner_amount
                        total_amount += booking_amount
                
                # Ajouter la compensation si applicable
                if owner_compensation > 0:
                    total_amount += owner_compensation
                    result["compensation_added"] = float(owner_compensation)
                
                # Supprimer cette réservation de la liste
                payout.bookings.remove(booking)
                
                # Mettre à jour le montant du versement
                old_amount = payout.amount
                payout.amount = total_amount
                payout.admin_notes += f"\nMontant mis à jour suite à l'annulation de la réservation {booking.id}. Ancien montant: {old_amount}, Nouveau montant: {total_amount}"
                if owner_compensation > 0:
                    payout.admin_notes += f" (inclut {owner_compensation} de compensation d'annulation)"
                payout.save(update_fields=['amount', 'admin_notes'])
                
                result["updated_payouts"].append({
                    "payout_id": str(payout.id),
                    "action": "updated",
                    "old_amount": float(old_amount),
                    "new_amount": float(total_amount)
                })
        
        result["status"] = "payouts_updated"
        return result

    @classmethod
    def calculate_owner_compensation(cls, booking, refund_percentage):
        """
        Calcule la compensation du propriétaire en cas d'annulation.
        Selon la politique d'annulation et le moment de l'annulation,
        le propriétaire peut avoir droit à une partie du paiement.
        
        Args:
            booking (Booking): La réservation annulée
            refund_percentage (Decimal): Pourcentage remboursé au locataire
                
        Returns:
            Decimal: Montant de la compensation propriétaire
        """
        # CORRECTION: Si le remboursement est à 100%, le propriétaire ne reçoit rien
        if refund_percentage >= Decimal('1.0'):
            return Decimal('0')
        
        # Calculer le pourcentage que le propriétaire conserve
        # C'est l'inverse du pourcentage remboursé au locataire
        owner_keep_percentage = Decimal('1.0') - refund_percentage
        
        # Base de calcul pour la compensation (hors frais de service)
        base_amount = booking.base_price
        
        # Récupérer le taux de commission propriétaire
        from payments.models import Commission
        commission = Commission.objects.filter(booking=booking).first()
        if not commission:
            commission = Commission.calculate_for_booking(booking)
        
        owner_commission_rate = commission.owner_rate / 100 if commission else Decimal('0.03')
        
        # Le propriétaire reçoit un pourcentage du montant, moins sa commission
        compensation_amount = base_amount * owner_keep_percentage
        commission_amount = compensation_amount * owner_commission_rate
        
        net_compensation = compensation_amount - commission_amount
        
        # Arrondir à l'entier
        return net_compensation.quantize(Decimal('1.'))
    
    @classmethod
    def create_compensation_payout(cls, booking, compensation_amount):
        """
        Crée un versement de compensation pour le propriétaire suite à une annulation.
        
        Args:
            booking (Booking): La réservation annulée
            compensation_amount (Decimal): Montant de la compensation
                
        Returns:
            Payout: Le versement créé ou None en cas d'erreur
        """
        try:
            from payments.models import Payout
            from django.utils import timezone
            
            # Créer un versement immédiat (sans programmation)
            payout = Payout.objects.create(
                owner=booking.property.owner,
                amount=compensation_amount,
                currency='XAF',
                status='ready',  # Prêt à verser immédiatement
                period_start=booking.check_in_date,
                period_end=booking.check_out_date,
                notes=f"Compensation suite à l'annulation de la réservation {booking.id}",
                admin_notes=f"Versement de compensation créé automatiquement suite à l'annulation de la réservation {booking.id}. Politique appliquée: {booking.property.cancellation_policy}"
            )
            
            # Associer la réservation au versement
            payout.bookings.add(booking)
            
            logger.info(f"Versement de compensation créé pour la réservation {booking.id} - Montant: {compensation_amount}")
            
            return {
                "payout_id": str(payout.id),
                "amount": float(compensation_amount),
                "status": payout.status
            }
        except Exception as e:
            logger.exception(f"Erreur lors de la création du versement de compensation: {str(e)}")
            return None
    