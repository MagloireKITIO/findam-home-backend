# common/management/commands/init_system_configs.py
import os
from django.core.management.base import BaseCommand
from common.models import SystemConfiguration

class Command(BaseCommand):
    help = 'Initialise les configurations système par défaut'

    def handle(self, *args, **options):
        # Définir les configurations par défaut avec leurs descriptions
        default_configs = [
            {
                'key': 'CANCELLATION_GRACE_PERIOD_MINUTES',
                'value': '30',
                'description': 'Période de grâce en minutes pendant laquelle un locataire peut annuler sans pénalité après avoir réservé.'
            },
            # Ajoutez d'autres configurations système par défaut ici si nécessaire
        ]
        
        created_count = 0
        updated_count = 0
        
        for config in default_configs:
            obj, created = SystemConfiguration.objects.update_or_create(
                key=config['key'],
                defaults={
                    'value': config['value'],
                    'description': config['description']
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Configuration créée: {config['key']} = {config['value']}"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"Configuration mise à jour: {config['key']} = {config['value']}"))
        
        self.stdout.write(self.style.SUCCESS(f"{created_count} configuration(s) créée(s), {updated_count} mise(s) à jour."))