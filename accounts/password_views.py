# accounts/password_views.py
# Vues pour gérer la réinitialisation de mot de passe

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

from rest_framework import status, views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

User = get_user_model()

class PasswordResetView(views.APIView):
    """
    Vue pour demander la réinitialisation du mot de passe.
    Envoie un email contenant un lien pour réinitialiser le mot de passe.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        
        if not email:
            # Pour des raisons de sécurité, ne pas indiquer que l'email est requis
            return Response({
                "message": "Si un compte existe avec cette adresse email, vous recevrez un lien de réinitialisation."
            })
        
        try:
            user = User.objects.get(email=email)
            
            # Générer un token de réinitialisation
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            
            # Construire le lien de réinitialisation
            reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            
            # Construire et envoyer l'email
            context = {
                'user': user,
                'reset_url': reset_url,
                'site_name': 'FINDAM',
            }
            
            email_subject = 'Réinitialisation de votre mot de passe FINDAM'
            email_body = render_to_string('password_reset_email.html', context)
            
            send_mail(
                email_subject,
                email_body,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
                html_message=email_body
            )
        except User.DoesNotExist:
            # Utilisateur non trouvé, mais ne pas l'indiquer pour des raisons de sécurité
            pass
        
        # Toujours retourner une réponse de succès pour éviter la divulgation d'informations
        return Response({
            "message": "Si un compte existe avec cette adresse email, vous recevrez un lien de réinitialisation."
        })

class ValidateResetTokenView(views.APIView):
    """
    Vue pour valider un token de réinitialisation de mot de passe.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        uid = request.data.get('uid')
        token = request.data.get('token')
        
        if not uid or not token:
            return Response({
                "error": "UID et token sont requis."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Décoder l'UID pour obtenir l'ID utilisateur
            uid_decoded = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=uid_decoded)
            
            # Vérifier la validité du token
            if default_token_generator.check_token(user, token):
                return Response({
                    "valid": True,
                    "message": "Token valide."
                })
            else:
                return Response({
                    "valid": False,
                    "error": "Token invalide ou expiré."
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({
                "valid": False,
                "error": "Lien de réinitialisation invalide."
            }, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmView(views.APIView):
    """
    Vue pour confirmer la réinitialisation du mot de passe.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        uid = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        
        if not uid or not token or not new_password:
            return Response({
                "error": "UID, token et nouveau mot de passe sont requis."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Décoder l'UID pour obtenir l'ID utilisateur
            uid_decoded = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=uid_decoded)
            
            # Vérifier la validité du token
            if default_token_generator.check_token(user, token):
                # Définir le nouveau mot de passe
                user.set_password(new_password)
                user.save()
                
                return Response({
                    "message": "Mot de passe réinitialisé avec succès."
                })
            else:
                return Response({
                    "error": "Token invalide ou expiré."
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({
                "error": "Lien de réinitialisation invalide."
            }, status=status.HTTP_400_BAD_REQUEST)