# reviews/admin.py
# Configuration de l'interface d'administration pour l'application reviews

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import Review, ReviewImage, ReviewReply, ReportedReview

class ReviewImageInline(admin.TabularInline):
    """Configuration inline pour les images des avis."""
    model = ReviewImage
    extra = 1
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        """Affiche une prévisualisation de l'image."""
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" />', obj.image.url)
        return "Pas d'image"
    
    image_preview.short_description = _("Aperçu")

class ReviewReplyInline(admin.StackedInline):
    """Configuration inline pour les réponses aux avis."""
    model = ReviewReply
    extra = 0
    readonly_fields = ['created_at', 'updated_at']

class ReportedReviewInline(admin.TabularInline):
    """Configuration inline pour les signalements d'avis."""
    model = ReportedReview
    extra = 0
    readonly_fields = ['reporter', 'reason', 'status', 'created_at']
    fields = ['reporter', 'reason', 'status', 'created_at']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle Review."""
    list_display = ('title', 'property_title', 'reviewer_name', 'rating', 'is_verified_stay', 'is_public', 'created_at')
    list_filter = ('rating', 'is_verified_stay', 'is_public', 'created_at', 'property__property_type')
    search_fields = ('title', 'comment', 'reviewer__email', 'reviewer__first_name', 'reviewer__last_name', 'property__title')
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('property', 'reviewer', 'title', 'comment', 'stay_date')
        }),
        (_('Évaluations'), {
            'fields': ('rating', 'cleanliness_rating', 'location_rating', 'value_rating', 'communication_rating')
        }),
        (_('Statut'), {
            'fields': ('is_public', 'is_verified_stay')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    inlines = [ReviewImageInline, ReviewReplyInline, ReportedReviewInline]
    
    def property_title(self, obj):
        """Affiche le titre du logement."""
        return obj.property.title
    
    def reviewer_name(self, obj):
        """Affiche le nom de l'auteur de l'avis."""
        return obj.reviewer.get_full_name() or obj.reviewer.email
    
    property_title.short_description = _('Logement')
    reviewer_name.short_description = _('Auteur')

@admin.register(ReviewReply)
class ReviewReplyAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle ReviewReply."""
    list_display = ('review_title', 'owner_name', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('review__title', 'content', 'owner__email', 'owner__first_name', 'owner__last_name')
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('review', 'owner', 'content')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def review_title(self, obj):
        """Affiche le titre de l'avis."""
        return obj.review.title
    
    def owner_name(self, obj):
        """Affiche le nom du propriétaire."""
        return obj.owner.get_full_name() or obj.owner.email
    
    review_title.short_description = _('Avis')
    owner_name.short_description = _('Propriétaire')

@admin.register(ReportedReview)
class ReportedReviewAdmin(admin.ModelAdmin):
    """Configuration de l'admin pour le modèle ReportedReview."""
    list_display = ('review_title', 'reporter_name', 'reason', 'status', 'created_at')
    list_filter = ('reason', 'status', 'created_at')
    search_fields = ('review__title', 'details', 'reporter__email', 'admin_notes')
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        (_('Informations de base'), {
            'fields': ('review', 'reporter', 'reason', 'details')
        }),
        (_('Traitement'), {
            'fields': ('status', 'admin_notes')
        }),
        (_('Métadonnées'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def review_title(self, obj):
        """Affiche le titre de l'avis signalé."""
        return obj.review.title
    
    def reporter_name(self, obj):
        """Affiche le nom de l'utilisateur qui a signalé l'avis."""
        return obj.reporter.get_full_name() or obj.reporter.email
    
    review_title.short_description = _('Avis signalé')
    reporter_name.short_description = _('Signalé par')
    
    def get_queryset(self, request):
        """Optimise les requêtes avec les relations."""
        return super().get_queryset(request).select_related('review', 'reporter')
    
    def save_model(self, request, obj, form, change):
        """Traite automatiquement l'avis signalé si le statut est 'actioned'."""
        if 'status' in form.changed_data and obj.status == 'actioned':
            obj.review.is_public = False
            obj.review.save(update_fields=['is_public'])
        super().save_model(request, obj, form, change)