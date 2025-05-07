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
    """Sérialiseur pour les méthodes de paiement."""
    
    payment_type_display = serializers.CharField(source='get_payment_type_display', read_only=True)
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'payment_type', 'payment_type_display', 'is_default', 'is_verified',
            'nickname', 'account_number', 'account_name', 'phone_number', 'operator',
            'last_digits', 'expiry_date', 'bank_name', 'branch_code',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_verified', 'created_at', 'updated_at']
        extra_kwargs = {
            'account_number': {'write_only': True}
        }
    
    def create(self, validated_data):
        """Création d'une méthode de paiement."""
        user = self.context['request'].user
        
        # Traitement spécifique selon le type de paiement
        payment_type = validated_data.get('payment_type')
        
        if payment_type == 'credit_card' and 'account_number' in validated_data:
            # Garder uniquement les 4 derniers chiffres pour les cartes bancaires
            account_number = validated_data.get('account_number')
            if account_number and len(account_number) >= 4:
                validated_data['last_digits'] = account_number[-4:]
        
        # Créer la méthode de paiement
        payment_method = PaymentMethod.objects.create(user=user, **validated_data)
        
        # Si c'est la première méthode de paiement de l'utilisateur, la définir comme méthode par défaut
        if PaymentMethod.objects.filter(user=user).count() == 1:
            payment_method.is_default = True
            payment_method.save(update_fields=['is_default'])
        
        return payment_method

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
    
    class Meta:
        model = Payout
        fields = [
            'id', 'owner', 'owner_details', 'amount', 'currency', 'payment_method',
            'payment_method_details', 'status', 'status_display', 'transaction',
            'external_reference', 'bookings', 'bookings_details', 'period_start', 'period_end',
            'notes', 'admin_notes', 'created_at', 'updated_at', 'processed_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'processed_at']

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