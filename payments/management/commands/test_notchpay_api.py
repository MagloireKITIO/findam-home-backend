# payments/management/commands/test_notchpay_api.py
from django.core.management.base import BaseCommand
import requests
import json
import uuid
from django.utils import timezone
from django.conf import settings

class Command(BaseCommand):
    help = "Script de test pour l'API NotchPay"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Démarrage du test de l\'API NotchPay'))
        
        # Clés d'API
        public_key = settings.NOTCHPAY_PUBLIC_KEY
        private_key = settings.NOTCHPAY_PRIVATE_KEY
        hash_key = getattr(settings, 'NOTCHPAY_HASH_KEY', '')
        
        # URL de base
        base_url = "https://api.notchpay.co"
        
        # Test du Ping
        self.stdout.write('Test de ping de l\'API...')
        try:
            ping_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            ping_response = requests.get(base_url, headers=ping_headers)
            self.stdout.write(f'Ping Status: {ping_response.status_code}')
            if ping_response.text:
                self.stdout.write(f'Ping Response: {ping_response.text[:100]}...')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ping Error: {str(e)}'))
        
        # Tests avec différentes combinaisons de clés et d'en-têtes
        self.stdout.write('\nTentatives d\'initialisation de paiement avec différentes configurations...')
        
        # Payload de base pour le test
        reference = f"test-{uuid.uuid4().hex[:8]}-{int(timezone.now().timestamp())}"
        base_payload = {
            "currency": "XAF",
            "amount": 100,
            "reference": reference,
            "description": "Test API NotchPay",
            "customer": {
                "email": "test@example.com",
                "phone": "237693937344",
                "name": "Test User"
            }
        }
        
        # Configurations à tester
        test_configs = [
            {
                "name": "Clé publique avec Bearer",
                "url": f"{base_url}/payments",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {public_key}"
                },
                "payload": base_payload
            },
            {
                "name": "Clé privée avec Bearer",
                "url": f"{base_url}/payments",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {private_key}"
                },
                "payload": base_payload
            },
            {
                "name": "Clé publique sans Bearer",
                "url": f"{base_url}/payments",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": public_key
                },
                "payload": base_payload
            },
            {
                "name": "Clé privée sans Bearer",
                "url": f"{base_url}/payments",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": private_key
                },
                "payload": base_payload
            },
            {
                "name": "Clé publique en X-API-Key",
                "url": f"{base_url}/payments",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-API-Key": public_key
                },
                "payload": base_payload
            },
            {
                "name": "Clé privée en X-API-Key",
                "url": f"{base_url}/payments",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-API-Key": private_key
                },
                "payload": base_payload
            },
            {
                "name": "Avec les trois clés",
                "url": f"{base_url}/payments",
                "headers": {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {private_key}",
                    "X-API-Key": public_key,
                    "X-Hash-Key": hash_key
                },
                "payload": base_payload
            },
        ]
        
        # Exécuter les tests
        for i, config in enumerate(test_configs):
            self.stdout.write(f"\nTest #{i+1}: {config['name']}")
            self.stdout.write(f"URL: {config['url']}")
            self.stdout.write(f"Headers: {json.dumps(config['headers'], indent=2)}")
            self.stdout.write(f"Payload: {json.dumps(config['payload'], indent=2)}")
            
            try:
                response = requests.post(
                    config['url'],
                    headers=config['headers'],
                    json=config['payload']
                )
                
                self.stdout.write(f"Status: {response.status_code}")
                
                if response.headers.get('Content-Type', '').startswith('application/json'):
                    self.stdout.write(f"Response: {json.dumps(response.json(), indent=2)}")
                else:
                    self.stdout.write(f"Response: {response.text[:200]}")
                
                if response.status_code < 300:
                    self.stdout.write(self.style.SUCCESS("SUCCESS! Cette configuration fonctionne."))
                    self.stdout.write("\nUtilisez cette configuration:")
                    self.stdout.write(f"Headers = {json.dumps(config['headers'], indent=2)}")
                    break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
                
        # Suggestions finales
        self.stdout.write("\nSuggestions:")
        self.stdout.write("1. Vérifiez que vos clés API sont correctes et actives dans le dashboard NotchPay")
        self.stdout.write("2. Assurez-vous d'utiliser l'environnement correct (sandbox vs production)")
        self.stdout.write("3. Si aucune configuration ne fonctionne, contactez le support NotchPay")