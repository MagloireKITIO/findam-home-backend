# payments/serializers.py
# Sérialiseurs pour les paiements et versements

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from .models import PaymentMethod, Transaction, Payout, Commission
from accounts.serializers import UserSerializer
from bookings.serializers import BookingListSerializer
from bookings.models import Booking
from .utils import NotchPayUtils

# Conserver les sérialiseurs existants
class PaymentMethodSerializer(serializers.ModelSerializer):
    """Sérialiseur de base pour les méthodes de paiement."""
    
    payment_type_display = serializers.CharField(source='get_payment_type_display', read_only=True)
    operator_display = serializers.CharField(source='get_operator_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    masked_phone_number = serializers.SerializerMethodField()
    masked_account_number = serializers.SerializerMethodField()
    can_activate = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'payment_type', 'payment_type_display', 'nickname', 
            'is_default', 'is_active', 'status', 'status_display',
            'operator', 'operator_display', 'masked_phone_number',
            'masked_account_number', 'bank_name', 'last_digits',
            'verification_attempts', 'last_verification_at',
            'can_activate', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'is_active', 'status', 'verification_attempts', 
            'last_verification_at', 'created_at', 'updated_at'
        ]
    
    def get_masked_phone_number(self, obj):
        """Retourne le numéro de téléphone masqué"""
        return obj.masked_phone_number()
    
    def get_masked_account_number(self, obj):
        """Retourne le numéro de compte masqué"""
        return obj.masked_account_number()
    
    def get_can_activate(self, obj):
        """Indique si la méthode peut être activée"""
        return obj.status == 'verified' and not obj.is_active


class PaymentMethodCreateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la création de nouvelles méthodes de paiement."""
    
    # Champs requis selon le type de paiement
    phone_number = serializers.CharField(required=False, allow_blank=True)
    account_number = serializers.CharField(required=False, allow_blank=True)
    account_name = serializers.CharField(required=False, allow_blank=True)
    bank_name = serializers.CharField(required=False, allow_blank=True)
    branch_code = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = PaymentMethod
        fields = [
            'payment_type', 'nickname', 'phone_number', 'operator',
            'account_number', 'account_name', 'bank_name', 'branch_code'
        ]
    
    def validate(self, data):
        """Validation personnalisée selon le type de paiement"""
        payment_type = data.get('payment_type')
        
        if payment_type == 'mobile_money':
            if not data.get('phone_number'):
                raise serializers.ValidationError({
                    'phone_number': _('Le numéro de téléphone est requis pour Mobile Money.')
                })
            
            # Valider le format du numéro
            phone = data['phone_number']
            if not NotchPayUtils.is_valid_cameroon_phone(phone):
                raise serializers.ValidationError({
                    'phone_number': _('Numéro de téléphone camerounais invalide.')
                })
            
            # Formater le numéro
            data['phone_number'] = NotchPayUtils.format_phone_number(phone)
            
        elif payment_type == 'bank_account':
            required_fields = ['account_number', 'account_name', 'bank_name']
            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError({
                        field: _(f'{field.replace("_", " ").title()} est requis pour un compte bancaire.')
                    })
        
        elif payment_type == 'credit_card':
            # Pour les cartes, on peut avoir d'autres validations
            # Note: Les informations de carte ne devraient jamais être stockées en plain text
            pass
        
        return data
    
    def create(self, validated_data):
        """Création d'une nouvelle méthode de paiement"""
        user = self.context['request'].user
        payment_type = validated_data.get('payment_type')
        
        # Retirer 'user' de validated_data s'il existe
        validated_data.pop('user', None)
        
        # Vérifier si l'utilisateur a déjà une méthode du même type et opérateur
        if payment_type == 'mobile_money':
            phone_number = validated_data.get('phone_number')
            existing = PaymentMethod.objects.filter(
                user=user,
                payment_type='mobile_money',
                phone_number=phone_number,
                status__in=['verified', 'pending']
            ).first()
            
            if existing:
                raise serializers.ValidationError(
                    _('Vous avez déjà une méthode Mobile Money avec ce numéro.')
                )
        
        # Créer la méthode de paiement
        payment_method = PaymentMethod.objects.create(user=user, **validated_data)
        
        # Si c'est la première méthode de l'utilisateur, la définir comme par défaut
        if PaymentMethod.objects.filter(user=user).count() == 1:
            payment_method.is_default = True
            payment_method.save(update_fields=['is_default'])
        
        return payment_method


class PaymentMethodDetailSerializer(PaymentMethodSerializer):
    """Sérialiseur détaillé pour les méthodes de paiement."""
    
    user_details = UserSerializer(source='user', read_only=True)
    verification_notes = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    
    class Meta(PaymentMethodSerializer.Meta):
        fields = PaymentMethodSerializer.Meta.fields + [
            'user_details', 'verification_notes', 'display_name'
        ]
    
    def get_verification_notes(self, obj):
        """Retourne les notes de vérification (masquées pour les utilisateurs normaux)"""
        request = self.context.get('request')
        if request and request.user.is_staff:
            return obj.verification_notes
        
        # Pour les utilisateurs normaux, retourner un message générique
        if obj.status == 'verified':
            return "Méthode vérifiée avec succès"
        elif obj.status == 'pending':
            return "Vérification en cours"
        elif obj.status == 'failed':
            return "Échec de la vérification"
        else:
            return "Statut non défini"
    
    def get_display_name(self, obj):
        """Retourne un nom d'affichage convivial pour la méthode"""
        return str(obj)


class PaymentMethodUpdateSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la mise à jour des méthodes de paiement."""
    
    class Meta:
        model = PaymentMethod
        fields = ['nickname', 'is_default']
        read_only_fields = [
            'payment_type', 'phone_number', 'operator', 'account_number',
            'account_name', 'bank_name', 'status', 'is_active'
        ]
    
    def update(self, instance, validated_data):
        """Mise à jour avec validation"""
        if 'is_default' in validated_data and validated_data['is_default']:
            # Si on définit cette méthode comme par défaut, retirer le statut des autres
            PaymentMethod.objects.filter(
                user=instance.user,
                is_default=True
            ).exclude(id=instance.id).update(is_default=False)
        
        return super().update(instance, validated_data)


class PaymentMethodActivationSerializer(serializers.Serializer):
    """Sérialiseur pour l'activation/désactivation des méthodes de paiement."""
    
    activate = serializers.BooleanField(default=True)
    
    def validate_activate(self, value):
        """Validation pour l'activation"""
        payment_method = self.context.get('payment_method')
        
        if value and payment_method.status != 'verified':
            raise serializers.ValidationError(
                _('Seules les méthodes vérifiées peuvent être activées.')
            )
        
        return value


class PaymentMethodSummarySerializer(serializers.Serializer):
    """Sérialiseur pour le résumé des méthodes de paiement."""
    
    total_methods = serializers.IntegerField()
    verified_methods = serializers.IntegerField()
    pending_methods = serializers.IntegerField()
    failed_methods = serializers.IntegerField()
    mobile_money_count = serializers.IntegerField()
    bank_account_count = serializers.IntegerField()
    has_active_method = serializers.BooleanField()
    active_method = PaymentMethodDetailSerializer(allow_null=True)


class BulkVerificationSerializer(serializers.Serializer):
    """Sérialiseur pour la vérification en lot (admin uniquement)."""
    
    method_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=50
    )
    
    def validate_method_ids(self, value):
        """Valider que tous les IDs existent"""
        existing_ids = PaymentMethod.objects.filter(id__in=value).values_list('id', flat=True)
        
        if len(existing_ids) != len(value):
            missing_ids = set(value) - set(existing_ids)
            raise serializers.ValidationError(
                f"Méthodes introuvables: {list(missing_ids)}"
            )
        
        return value

class TransactionSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les transactions."""
    
    user_details = UserSerializer(source='user', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    booking_details = BookingListSerializer(source='booking', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'user', 'user_details', 'transaction_type', 'transaction_type_display',
            'status', 'status_display', 'amount', 'currency', 'booking', 'booking_details',
            'payment_transaction', 'external_reference', 'description', 'admin_notes',
            'created_at', 'updated_at', 'processed_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'processed_at']

class PayoutSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les versements."""
    
    owner_details = UserSerializer(source='owner', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    bookings_details = BookingListSerializer(source='bookings', many=True, read_only=True)
    payment_method_details = PaymentMethodSerializer(source='payment_method', read_only=True)
    processed_by_details = UserSerializer(source='processed_by', read_only=True)
    days_until_scheduled = serializers.SerializerMethodField()
    
    class Meta:
        model = Payout
        fields = [
            'id', 'owner', 'owner_details', 'amount', 'currency', 'payment_method',
            'payment_method_details', 'status', 'status_display', 'transaction',
            'external_reference', 'bookings', 'bookings_details', 'period_start', 'period_end',
            'scheduled_at', 'processed_by', 'processed_by_details', 'escrow_reason', 
            'days_until_scheduled', 'notes', 'admin_notes', 'created_at', 'updated_at', 'processed_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'processed_at']
    
    def get_days_until_scheduled(self, obj):
        """Calcule le nombre de jours jusqu'à la date programmée."""
        if obj.scheduled_at and obj.status == 'scheduled':
            now = timezone.now()
            if obj.scheduled_at > now:
                delta = obj.scheduled_at - now
                return delta.days + (delta.seconds / 86400)  # Jours + secondes convertis en fraction de jour
        return None

# Ajouter un nouveau sérialiseur pour la planification des versements
class PayoutScheduleSerializer(serializers.Serializer):
    """
    Sérialiseur pour programmer un versement.
    """
    scheduled_date = serializers.DateTimeField(required=True)
    
    def validate_scheduled_date(self, value):
        """Valide que la date programmée est future."""
        if value <= timezone.now():
            raise serializers.ValidationError(_("La date programmée doit être future."))
        return value
    
# Ajouter un nouveau sérialiseur pour l'annulation de la planification
class PayoutCancelScheduleSerializer(serializers.Serializer):
    """
    Sérialiseur pour annuler la programmation d'un versement.
    """
    reason = serializers.CharField(required=False, allow_blank=True)

# Ajouter un nouveau sérialiseur pour programmer un versement pour une réservation
class BookingPayoutScheduleSerializer(serializers.Serializer):
    """
    Sérialiseur pour programmer un versement pour une réservation.
    """
    booking_id = serializers.UUIDField(required=True)
    scheduled_date = serializers.DateTimeField(required=False)
    
    def validate_scheduled_date(self, value):
        """Valide que la date programmée est future."""
        if value and value <= timezone.now():
            raise serializers.ValidationError(_("La date programmée doit être future."))
        return value

class CommissionSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les commissions."""
    
    booking_details = BookingListSerializer(source='booking', read_only=True)
    
    class Meta:
        model = Commission
        fields = [
            'id', 'booking', 'booking_details', 'owner_amount', 'tenant_amount',
            'total_amount', 'owner_rate', 'tenant_rate', 'transaction',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'owner_amount', 'tenant_amount', 'total_amount',
            'owner_rate', 'tenant_rate', 'created_at', 'updated_at'
        ]

class PayoutCreateSerializer(serializers.Serializer):
    """Sérialiseur pour la création manuelle d'un versement."""
    
    bookings = serializers.ListField(
        child=serializers.UUIDField(),
        required=False
    )
    period_start = serializers.DateField(required=True)
    period_end = serializers.DateField(required=True)
    payment_method = serializers.UUIDField(required=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        """Validation personnalisée."""
        period_start = data.get('period_start')
        period_end = data.get('period_end')
        bookings_ids = data.get('bookings', [])
        payment_method_id = data.get('payment_method')
        user = self.context['request'].user
        
        # Vérifier que la période de fin est postérieure à la période de début
        if period_end <= period_start:
            raise serializers.ValidationError(_("La période de fin doit être postérieure à la période de début."))
        
        # Vérifier que la méthode de paiement appartient à l'utilisateur
        try:
            payment_method = PaymentMethod.objects.get(id=payment_method_id)
            if payment_method.user != user:
                raise serializers.ValidationError(_("Cette méthode de paiement ne vous appartient pas."))
            data['payment_method_obj'] = payment_method
        except PaymentMethod.DoesNotExist:
            raise serializers.ValidationError(_("Méthode de paiement introuvable."))
        
        # Vérifier les réservations
        if bookings_ids:
            bookings = []
            for booking_id in bookings_ids:
                try:
                    booking = Booking.objects.get(id=booking_id)
                    # Vérifier que la réservation appartient au propriétaire
                    if booking.property.owner != user:
                        raise serializers.ValidationError(_("La réservation {} ne vous appartient pas.").format(booking_id))
                    # Vérifier que la réservation est complétée
                    if booking.status != 'completed':
                        raise serializers.ValidationError(_("La réservation {} n'est pas terminée.").format(booking_id))
                    # Vérifier que le paiement est effectué
                    if booking.payment_status != 'paid':
                        raise serializers.ValidationError(_("Le paiement de la réservation {} n'est pas effectué.").format(booking_id))
                    # Vérifier qu'elle n'est pas déjà dans un versement
                    if booking.payouts.filter(status__in=['pending', 'processing', 'completed']).exists():
                        raise serializers.ValidationError(_("La réservation {} est déjà dans un versement.").format(booking_id))
                    
                    bookings.append(booking)
                except Booking.DoesNotExist:
                    raise serializers.ValidationError(_("Réservation {} introuvable.").format(booking_id))
            
            data['bookings_objs'] = bookings
        
        return data
    
    def create(self, validated_data):
        """Création d'un versement."""
        user = self.context['request'].user
        payment_method = validated_data.pop('payment_method_obj')
        bookings_objs = validated_data.pop('bookings_objs', [])
        bookings_ids = validated_data.pop('bookings', [])
        
        # Calculer le montant total à verser
        amount = 0
        for booking in bookings_objs:
            # Calculer le montant à verser (prix total - commission)
            commission = Commission.objects.filter(booking=booking).first()
            if commission:
                booking_amount = booking.total_price - commission.owner_amount
            else:
                # Si pas de commission, créer une
                commission = Commission.calculate_for_booking(booking)
                booking_amount = booking.total_price - commission.owner_amount
            
            amount += booking_amount
        
        # Créer le versement
        payout = Payout.objects.create(
            owner=user,
            amount=amount,
            payment_method=payment_method,
            period_start=validated_data.get('period_start'),
            period_end=validated_data.get('period_end'),
            notes=validated_data.get('notes', '')
        )
        
        # Associer les réservations
        if bookings_objs:
            payout.bookings.set(bookings_objs)
        
        return payout

# Ajout des nouveaux sérialiseurs pour NotchPay

class NotchPayPaymentInitSerializer(serializers.Serializer):
    """
    Sérialiseur pour l'initialisation d'un paiement NotchPay
    """
    payment_method = serializers.CharField(default='mobile_money')
    mobile_operator = serializers.CharField(required=False, default='mobile_money')
    phone_number = serializers.CharField(required=False)
    
    def validate_mobile_operator(self, value):
        """Valide l'opérateur mobile"""
        valid_operators = ['orange', 'mtn', 'mobile_money']
        if value not in valid_operators:
            raise serializers.ValidationError(f"Opérateur mobile non valide. Options: {', '.join(valid_operators)}")
        return value
    
    def validate_payment_method(self, value):
        """Valide la méthode de paiement"""
        valid_methods = ['mobile_money', 'credit_card', 'bank_transfer']
        if value not in valid_methods:
            raise serializers.ValidationError(f"Méthode de paiement non valide. Options: {', '.join(valid_methods)}")
        return value
    
    def validate(self, data):
        """Validation globale des données"""
        payment_method = data.get('payment_method')
        
        # Si la méthode est mobile_money, le numéro de téléphone est requis
        if payment_method == 'mobile_money' and not data.get('phone_number'):
            raise serializers.ValidationError({'phone_number': "Le numéro de téléphone est requis pour le paiement par Mobile Money."})
            
        return data

class NotchPayCallbackSerializer(serializers.Serializer):
    """
    Sérialiseur pour valider les données de callback NotchPay
    """
    event = serializers.CharField()
    data = serializers.DictField()
    
    def validate_event(self, value):
        """Valide le type d'événement"""
        valid_events = ['payment.success', 'payment.failed', 'payment.pending', 'payment.processing']
        if value not in valid_events:
            raise serializers.ValidationError(f"Type d'événement non valide: {value}")
        return value