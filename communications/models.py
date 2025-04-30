# communications/models.py
# Modèles pour la gestion des communications (chat, notifications)

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.utils import timezone
from properties.models import Property

User = get_user_model()

class Conversation(models.Model):
    """
    Modèle pour les conversations entre utilisateurs.
    Une conversation peut être liée à un logement spécifique.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participants = models.ManyToManyField(User, related_name='conversations')
    property = models.ForeignKey(
        Property, 
        on_delete=models.CASCADE, 
        related_name='conversations',
        null=True,
        blank=True
    )
    
    is_active = models.BooleanField(_('active'), default=True)
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de dernière mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('conversation')
        verbose_name_plural = _('conversations')
        ordering = ['-updated_at']
        db_table = 'findam_conversations'
    
    def __str__(self):
        participants_str = ", ".join([p.email for p in self.participants.all()[:3]])
        if self.participants.count() > 3:
            participants_str += f" et {self.participants.count() - 3} autre(s)"
        
        property_str = f" - {self.property.title}" if self.property else ""
        return f"Conversation: {participants_str}{property_str}"
    
    def add_message(self, sender, content, message_type='text'):
        """
        Ajoute un message à la conversation et met à jour sa date de dernière mise à jour.
        """
        message = Message.objects.create(
            conversation=self,
            sender=sender,
            content=content,
            message_type=message_type
        )
        self.updated_at = timezone.now()
        self.save(update_fields=['updated_at'])
        return message
    
    def get_other_participant(self, user):
        """
        Retourne l'autre participant de la conversation pour un utilisateur donné.
        Utile pour les conversations à deux.
        """
        return self.participants.exclude(id=user.id).first()
    
    def mark_as_read(self, user):
        """
        Marque tous les messages non lus de la conversation comme lus pour un utilisateur donné.
        """
        unread_messages = self.messages.filter(read_by__isnull=True).exclude(sender=user)
        for message in unread_messages:
            message.mark_as_read(user)

class Message(models.Model):
    """
    Modèle pour les messages échangés dans une conversation.
    """
    MESSAGE_TYPE_CHOICES = (
        ('text', _('Texte')),
        ('image', _('Image')),
        ('system', _('Système')),
        ('promo_code', _('Code promo')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(_('contenu'))
    message_type = models.CharField(_('type de message'), max_length=20, choices=MESSAGE_TYPE_CHOICES, default='text')
    
    # Pièce jointe (image ou autre fichier)
    attachment = models.FileField(_('pièce jointe'), upload_to='messages/', null=True, blank=True)
    
    # Lecture du message
    read_by = models.ManyToManyField(User, related_name='read_messages', blank=True)
    
    created_at = models.DateTimeField(_('date d\'envoi'), auto_now_add=True)
    updated_at = models.DateTimeField(_('date de dernière mise à jour'), auto_now=True)
    
    class Meta:
        verbose_name = _('message')
        verbose_name_plural = _('messages')
        ordering = ['created_at']
        db_table = 'findam_messages'
    
    def __str__(self):
        return f"Message de {self.sender.email} - {self.created_at.strftime('%d/%m/%Y %H:%M')}"
    
    def mark_as_read(self, user):
        """
        Marque le message comme lu par un utilisateur.
        """
        self.read_by.add(user)
    
    def is_read_by(self, user):
        """
        Vérifie si le message a été lu par un utilisateur donné.
        """
        return self.read_by.filter(id=user.id).exists()

class Notification(models.Model):
    """
    Modèle pour les notifications envoyées aux utilisateurs.
    """
    NOTIFICATION_TYPE_CHOICES = (
        ('new_message', _('Nouveau message')),
        ('new_booking', _('Nouvelle réservation')),
        ('booking_confirmed', _('Réservation confirmée')),
        ('booking_cancelled', _('Réservation annulée')),
        ('payment_received', _('Paiement reçu')),
        ('new_review', _('Nouvel avis')),
        ('system', _('Notification système')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    
    notification_type = models.CharField(_('type de notification'), max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(_('titre'), max_length=100)
    content = models.TextField(_('contenu'))
    
    # Liens vers les objets concernés (optionnels)
    related_conversation = models.ForeignKey(
        Conversation, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='notifications'
    )
    related_object_id = models.CharField(_('ID de l\'objet lié'), max_length=100, blank=True)
    related_object_type = models.CharField(_('type de l\'objet lié'), max_length=50, blank=True)
    
    # Statut de la notification
    is_read = models.BooleanField(_('lue'), default=False)
    
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        ordering = ['-created_at']
        db_table = 'findam_notifications'
    
    def __str__(self):
        return f"Notification pour {self.recipient.email} - {self.title}"
    
    def mark_as_read(self):
        """
        Marque la notification comme lue.
        """
        self.is_read = True
        self.save(update_fields=['is_read'])
    
    @classmethod
    def create_for_new_message(cls, message):
        """
        Crée une notification pour un nouveau message.
        """
        # Récupérer les destinataires (tous les participants sauf l'expéditeur)
        recipients = message.conversation.participants.exclude(id=message.sender.id)
        
        for recipient in recipients:
            notification = cls.objects.create(
                recipient=recipient,
                notification_type='new_message',
                title=_('Nouveau message'),
                content=_('Vous avez reçu un nouveau message de {}').format(message.sender.get_full_name() or message.sender.email),
                related_conversation=message.conversation,
                related_object_id=str(message.id),
                related_object_type='message'
            )
        
        return notification

class DeviceToken(models.Model):
    """
    Modèle pour stocker les tokens des appareils pour les notifications push.
    """
    PLATFORM_CHOICES = (
        ('android', _('Android')),
        ('ios', _('iOS')),
        ('web', _('Web')),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(_('token'), max_length=255, unique=True)
    platform = models.CharField(_('plateforme'), max_length=10, choices=PLATFORM_CHOICES)
    device_name = models.CharField(_('nom de l\'appareil'), max_length=100, blank=True)
    
    is_active = models.BooleanField(_('actif'), default=True)
    last_used = models.DateTimeField(_('dernière utilisation'), auto_now=True)
    created_at = models.DateTimeField(_('date de création'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('token d\'appareil')
        verbose_name_plural = _('tokens d\'appareils')
        db_table = 'findam_device_tokens'
    
    def __str__(self):
        return f"Token de {self.user.email} ({self.get_platform_display()} - {self.device_name})"