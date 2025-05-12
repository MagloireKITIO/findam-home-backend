# payments/management/commands/verify_payment_methods.py
# Commande pour vérifier en lot les méthodes de paiement

import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from payments.models import PaymentMethod

logger = logging.getLogger('findam')

class Command(BaseCommand):
    help = 'Vérifie les méthodes de paiement avec NotchPay'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            type=str,
            default='pending',
            help='Statut des méthodes à vérifier (pending, failed, disabled)',
        )
        
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Nombre maximum de méthodes à vérifier',
        )
        
        parser.add_argument(
            '--method-ids',
            type=str,
            help='IDs spécifiques des méthodes à vérifier (séparés par des virgules)',
        )
        
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help='Réessayer les méthodes qui ont échoué',
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mode simulation - ne pas effectuer la vérification',
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write(
            self.style.SUCCESS(f'Début de la vérification des méthodes de paiement à {start_time.strftime("%H:%M:%S")}')
        )
        
        status = options['status']
        limit = options['limit']
        method_ids = options.get('method_ids')
        retry_failed = options['retry_failed']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode simulation: aucune vérification ne sera effectuée'))
        
        # Sélectionner les méthodes à vérifier
        if method_ids:
            # Vérification de méthodes spécifiques
            ids = [id.strip() for id in method_ids.split(',')]
            methods = PaymentMethod.objects.filter(id__in=ids)
            
            if not methods.exists():
                self.stdout.write(self.style.ERROR('Aucune méthode trouvée avec les IDs spécifiés'))
                return
                
            self.stdout.write(f'Vérification de {methods.count()} méthodes spécifiées')
        else:
            # Vérification par statut
            methods = PaymentMethod.objects.filter(status=status)
            
            if retry_failed and status == 'failed':
                # Filtrer les méthodes qui n'ont pas atteint le maximum de tentatives
                methods = methods.filter(verification_attempts__lt=3)
            
            methods = methods[:limit]
            
            if not methods.exists():
                self.stdout.write(f'Aucune méthode trouvée avec le statut "{status}"')
                return
                
            self.stdout.write(f'Vérification de {methods.count()} méthodes avec le statut "{status}"')
        
        # Traiter les méthodes
        success_count = 0
        failed_count = 0
        
        for method in methods:
            try:
                self.stdout.write(f'Traitement de la méthode {method.id} ({method})')
                
                if dry_run:
                    self.stdout.write(f'  Simulation: La méthode serait vérifiée')
                    continue
                
                # Vérifier la méthode avec NotchPay
                verification_success = method.verify_with_notchpay()
                
                if verification_success:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Vérification réussie - Nouveau statut: {method.status}')
                    )
                else:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Vérification échouée - Statut: {method.status}')
                    )
                    
            except Exception as e:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Erreur lors de la vérification: {str(e)}')
                )
                logger.exception(f'Erreur lors de la vérification de la méthode {method.id}')
        
        # Résumé
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== RÉSUMÉ ==='))
        self.stdout.write(f'Durée: {duration:.2f} secondes')
        self.stdout.write(f'Méthodes traitées: {success_count + failed_count}')
        self.stdout.write(self.style.SUCCESS(f'Succès: {success_count}'))
        self.stdout.write(self.style.ERROR(f'Échecs: {failed_count}'))
        
        # Statistiques par statut
        self.stdout.write('')
        self.stdout.write('Statistiques par statut:')
        status_counts = {}
        for status_choice in PaymentMethod.STATUS_CHOICES:
            status_key = status_choice[0]
            count = PaymentMethod.objects.filter(status=status_key).count()
            status_counts[status_key] = count
            self.stdout.write(f'  {status_choice[1]}: {count}')
        
        # Recommandations
        self.stdout.write('')
        self.stdout.write('Recommandations:')
        
        pending_count = status_counts.get('pending', 0)
        if pending_count > 0:
            self.stdout.write(f'  - {pending_count} méthodes en attente de vérification')
        
        failed_count_total = status_counts.get('failed', 0)
        if failed_count_total > 0:
            failed_retryable = PaymentMethod.objects.filter(
                status='failed',
                verification_attempts__lt=3
            ).count()
            self.stdout.write(f'  - {failed_count_total} méthodes échouées')
            self.stdout.write(f'  - {failed_retryable} peuvent être re-vérifiées')
        
        verified_count = status_counts.get('verified', 0)
        inactive_verified = PaymentMethod.objects.filter(
            status='verified',
            is_active=False
        ).count()
        if verified_count > 0:
            self.stdout.write(f'  - {verified_count} méthodes vérifiées')
            self.stdout.write(f'  - {inactive_verified} vérifiées mais non activées')
    
    def _format_duration(self, seconds):
        """Formate la durée en format lisible"""
        if seconds < 60:
            return f"{seconds:.2f} secondes"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.2f} minutes"
        else:
            hours = seconds / 3600
            return f"{hours:.2f} heures"