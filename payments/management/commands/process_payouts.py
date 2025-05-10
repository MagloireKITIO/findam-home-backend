# payments/management/commands/process_payouts.py
# Commande de gestion Django pour traiter les versements programmés

import logging
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from payments.models import Payout
from payments.services.payout_service import PayoutService

logger = logging.getLogger('findam')

class Command(BaseCommand):
    help = 'Traite les versements programmés ou spécifiés'

    def add_arguments(self, parser):
        parser.add_argument(
            '--scheduled',
            action='store_true',
            help='Traite les versements programmés dont la date est passée'
        )
        
        parser.add_argument(
            '--ready',
            action='store_true',
            help='Traite les versements prêts à être versés'
        )
        
        parser.add_argument(
            '--payout-ids',
            type=str,
            help='Liste d\'IDs de versements à traiter, séparés par des virgules'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simule le traitement sans effectuer les versements'
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write(self.style.SUCCESS(f'Début du traitement des versements à {start_time.strftime("%H:%M:%S")}'))
        
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode simulation: aucun versement ne sera effectué'))
        
        # Traiter les versements spécifiques
        if options['payout_ids']:
            payout_ids = options['payout_ids'].split(',')
            self.stdout.write(f'Traitement des versements spécifiés: {payout_ids}')
            
            try:
                # Convertir les IDs de string en UUID
                uuid_payout_ids = []
                for pid in payout_ids:
                    try:
                        uuid_payout_ids.append(uuid.UUID(pid.strip()))
                    except ValueError:
                        self.stdout.write(self.style.WARNING(f'ID de versement invalide ignoré: {pid}'))
                
                payouts = Payout.objects.filter(id__in=uuid_payout_ids)
                
                if not payouts.exists():
                    self.stdout.write(self.style.ERROR('Aucun versement trouvé avec les IDs spécifiés'))
                    return
                
                # Marquer tous les versements comme prêts s'ils sont programmés
                for payout in payouts.filter(status='scheduled'):
                    payout.mark_as_ready()
                    self.stdout.write(f'Versement {payout.id} marqué comme prêt')
                
                # Si pas en mode simulation, traiter les versements prêts
                if not dry_run:
                    for payout in payouts.filter(status='ready'):
                        try:
                            # Traitement direct avec le service
                            from payments.services.notchpay_service import NotchPayService
                            notchpay_service = NotchPayService()
                            
                            self.stdout.write(f'Traitement du versement {payout.id} pour {payout.owner.email}')
                            
                            # Récupérer les informations de paiement du propriétaire
                            from payments.models import PaymentMethod
                            payment_method = payout.payment_method or PaymentMethod.objects.filter(
                                user=payout.owner,
                                is_default=True
                            ).first()
                            
                            if not payment_method:
                                self.stdout.write(self.style.ERROR(
                                    f'Aucune méthode de paiement trouvée pour {payout.owner.email}'
                                ))
                                continue
                            
                            # Déterminer le canal de paiement
                            payment_channel = self._get_payment_channel(payment_method)
                            
                            # Préparer les informations du destinataire
                            recipient_data = self._prepare_recipient_data(payment_method, payout.owner)
                            
                            # Créer ou récupérer l'ID du destinataire dans NotchPay
                            recipient_id = PayoutService._get_or_create_recipient(notchpay_service, recipient_data)
                            
                            if not recipient_id:
                                self.stdout.write(self.style.ERROR(
                                    f'Impossible de créer un destinataire NotchPay pour {payout.owner.email}'
                                ))
                                continue
                            
                            # Préparer les métadonnées pour le paiement
                            metadata = {
                                'transaction_type': 'payout',
                                'object_id': str(payout.id),
                                'owner_id': str(payout.owner.id),
                            }
                            
                            # Préparer la description du paiement
                            description = f"Versement pour réservation(s) du {payout.period_start} au {payout.period_end}"
                            
                            # Effectuer le transfert via NotchPay
                            try:
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
                                    self.stdout.write(self.style.SUCCESS(
                                        f'Versement {payout.id} effectué avec succès, référence: {payout.external_reference}'
                                    ))
                                else:
                                    self.stdout.write(self.style.ERROR(
                                        f'Réponse NotchPay invalide pour le versement {payout.id}'
                                    ))
                                    
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(
                                    f'Erreur lors du transfert NotchPay pour le versement {payout.id}: {str(e)}'
                                ))
                                payout.status = 'failed'
                                payout.admin_notes += f"\nÉchec du versement: {str(e)} ({timezone.now().strftime('%Y-%m-%d %H:%M')})"
                                payout.save(update_fields=['status', 'admin_notes'])
                        
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'Erreur lors du traitement du versement {payout.id}: {str(e)}'))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'Simulation: {payouts.filter(status="ready").count()} versements seraient traités'
                    ))
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Erreur: {str(e)}'))
                return
        
        # Traiter les versements programmés
        elif options['scheduled']:
            self.stdout.write('Traitement des versements programmés dont la date est passée')
            
            count = PayoutService.process_scheduled_payouts()
            
            self.stdout.write(self.style.SUCCESS(f'{count} versements marqués comme prêts'))
        
        # Traiter les versements prêts
        elif options['ready']:
            self.stdout.write('Traitement des versements prêts à être versés')
            
            if not dry_run:
                result = PayoutService.process_ready_payouts()
                
                self.stdout.write(self.style.SUCCESS(
                    f"{result['success']} versements effectués avec succès, {result['failed']} échoués"
                ))
            else:
                ready_count = Payout.objects.filter(status='ready').count()
                self.stdout.write(self.style.WARNING(f'Simulation: {ready_count} versements seraient traités'))
        
        # Si aucune option spécifiée, traiter tous les types
        else:
            self.stdout.write('Traitement de tous les types de versements')
            
            # Traiter d'abord les versements programmés
            scheduled_count = PayoutService.process_scheduled_payouts()
            self.stdout.write(self.style.SUCCESS(f'{scheduled_count} versements marqués comme prêts'))
            
            # Puis traiter les versements prêts
            if not dry_run:
                result = PayoutService.process_ready_payouts()
                
                self.stdout.write(self.style.SUCCESS(
                    f"{result['success']} versements effectués avec succès, {result['failed']} échoués"
                ))
            else:
                ready_count = Payout.objects.filter(status='ready').count()
                self.stdout.write(self.style.WARNING(f'Simulation: {ready_count} versements seraient traités'))
        
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self.stdout.write(self.style.SUCCESS(f'Traitement terminé en {duration:.2f} secondes'))
    
    def _get_payment_channel(self, payment_method):
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
    
    def _prepare_recipient_data(self, payment_method, owner):
        """
        Prépare les données du destinataire pour NotchPay.
        """
        recipient_data = {
            'channel': self._get_payment_channel(payment_method),
            'number': payment_method.phone_number or payment_method.account_number,
            'phone': owner.phone_number,
            'email': owner.email,
            'country': 'CM',  # Code pays pour le Cameroun
            'name': owner.get_full_name() or owner.email,
            'description': f"Propriétaire FINDAM: {owner.email}",
            'reference': f"owner-{owner.id}"
        }
        
        return recipient_data