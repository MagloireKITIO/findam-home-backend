# accounts/models.py
# Modèles pour la gestion des utilisateurs (propriétaires et locataires)

import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator

phone_regex = RegexValidator(
    regex=r'^\+?1?\d{9,15}$',
    message="Le numéro de téléphone doit être au format: '+999999999'. 15 chiffres maximum."
)

class UserManager(BaseUserManager):
    """Manager personnalisé pour les utilisateurs Findam."""
    
    def create_user(self, email, phone_number, password=None, **extra_fields):
        """Crée et sauvegarde un utilisateur avec l'email et le mot de passe donnés."""
        if not email:
            raise ValueError('L\'adresse email est obligatoire')
        if not phone_number:
            raise ValueError('Le numéro de téléphone est obligatoire')
            
        email = self.normalize_email(email)
        user = self.model(email=email, phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, phone_number, password=None, **extra_fields):
        """Crée et sauvegarde un superutilisateur avec l'email et le mot de passe donnés."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Le superutilisateur doit avoir is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Le superutilisateur doit avoir is_superuser=True.')
        
        return self.create_user(email, phone_number, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    """Modèle utilisateur personnalisé pour Findam."""
    
    USER_TYPE_CHOICES = (
        ('tenant', 'Locataire'),
        ('owner', 'Propriétaire'),
        ('admin', 'Administrateur'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('adresse email'), unique=True)
    phone_number = models.CharField(_('numéro de téléphone'), max_length=15, validators=[phone_regex], unique=True)
    first_name = models.CharField(_('prénom'), max_length=30, blank=True)
    last_name = models.CharField(_('nom'), max_length=30, blank=True)
    user_type = models.CharField(_('type d\'utilisateur'), max_length=10, choices=USER_TYPE_CHOICES, default='tenant')
    
    is_staff = models.BooleanField(_('statut staff'), default=False)
    is_active = models.BooleanField(_('actif'), default=True)
    is_verified = models.BooleanField(_('vérifié'), default=False)
    
    date_joined = models.DateTimeField(_('date d\'inscription'), default=timezone.now)
    last_login = models.DateTimeField(_('dernière connexion'), null=True, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone_number']
    
    class Meta:
        verbose_name = _('utilisateur')
        verbose_name_plural = _('utilisateurs')
        db_table = 'findam_users'
        
    def __str__(self):
        return self.email
    
    def get_full_name(self):
        """Retourne le prénom et le nom."""
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()
    
    def get_short_name(self):
        """Retourne le prénom."""
        return self.first_name
    
    @property
    def is_owner(self):
        """Vérifie si l'utilisateur est un propriétaire."""
        return self.user_type == 'owner'
    
    @property
    def is_tenant(self):
        """Vérifie si l'utilisateur est un locataire."""
        return self.user_type == 'tenant'

class Profile(models.Model):
    """
    Modèle de profil utilisateur contenant des informations supplémentaires.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Cameroun")
    
    # Champs pour la vérification d'identité
    id_card_number = models.CharField(max_length=50, blank=True)
    id_card_image = models.ImageField(upload_to='id_cards/', null=True, blank=True)
    selfie_image = models.ImageField(upload_to='selfies/', null=True, blank=True)
    verification_date = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'En attente'),
            ('verified', 'Vérifié'),
            ('rejected', 'Rejeté'),
        ],
        default='pending'
    )
    verification_notes = models.TextField(blank=True)
    
    # Champs pour le système d'évaluation
    avg_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('profil')
        verbose_name_plural = _('profils')
        db_table = 'findam_profiles'
        
    def __str__(self):
        return f"Profil de {self.user.email}"
    
    def update_rating(self, new_rating):
        """
        Met à jour la note moyenne de l'utilisateur.
        """
        current_total = self.avg_rating * self.rating_count
        self.rating_count += 1
        self.avg_rating = (current_total + new_rating) / self.rating_count
        self.save()

class OwnerSubscription(models.Model):
    """
    Modèle pour gérer les abonnements des propriétaires.
    """
    SUBSCRIPTION_TYPE_CHOICES = (
        ('free', 'Gratuit'),
        ('monthly', 'Mensuel'),
        ('quarterly', 'Trimestriel'),
        ('yearly', 'Annuel'),
    )
    
    STATUS_CHOICES = (
        ('active', 'Actif'),
        ('expired', 'Expiré'),
        ('cancelled', 'Annulé'),
        ('pending', 'En attente'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    subscription_type = models.CharField(max_length=10, choices=SUBSCRIPTION_TYPE_CHOICES, default='free')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    
    payment_reference = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('abonnement propriétaire')
        verbose_name_plural = _('abonnements propriétaires')
        db_table = 'findam_owner_subscriptions'
        
    def __str__(self):
        return f"{self.owner.email} - {self.get_subscription_type_display()}"
    
    def is_active(self):
        """Vérifie si l'abonnement est actif."""
        return self.status == 'active' and (self.end_date is None or self.end_date > timezone.now())
    
    def calculate_end_date(self):
        """Calcule la date de fin d'abonnement en fonction du type."""
        if self.subscription_type == 'free':
            return None
        elif self.subscription_type == 'monthly':
            return self.start_date + timezone.timedelta(days=30)
        elif self.subscription_type == 'quarterly':
            return self.start_date + timezone.timedelta(days=90)
        elif self.subscription_type == 'yearly':
            return self.start_date + timezone.timedelta(days=365)
        return None
    
    def save(self, *args, **kwargs):
        """Surcharge de la méthode save pour calculer automatiquement la date de fin."""
        if not self.end_date and self.subscription_type != 'free':
            self.end_date = self.calculate_end_date()
        super().save(*args, **kwargs)

# Signal pour créer automatiquement un profil à la création d'un utilisateur
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Crée automatiquement un profil à la création d'un utilisateur."""
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Sauvegarde le profil lors de la sauvegarde de l'utilisateur."""
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        Profile.objects.create(user=instance)