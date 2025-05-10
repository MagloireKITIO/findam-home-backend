# common/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import SystemConfiguration
from .serializers import SystemConfigurationSerializer

class SystemConfigurationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour accéder aux configurations système en lecture seule.
    """
    queryset = SystemConfiguration.objects.all()
    serializer_class = SystemConfigurationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filtrer les configurations accessibles selon l'utilisateur."""
        queryset = SystemConfiguration.objects.all()
        
        # Restreindre certaines configurations aux administrateurs uniquement
        if not self.request.user.is_staff:
            queryset = queryset.exclude(key__startswith='ADMIN_')
        
        # Filtrer par clé si spécifiée
        key = self.request.query_params.get('key', None)
        if key:
            queryset = queryset.filter(key=key)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def public(self, request):
        """
        Endpoint pour récupérer les configurations publiques.
        Pas besoin d'authentification.
        """
        # Liste des clés accessibles publiquement
        public_keys = ['CANCELLATION_GRACE_PERIOD_MINUTES']
        
        queryset = SystemConfiguration.objects.filter(key__in=public_keys)
        
        # Filtrer par clé si spécifiée
        key = request.query_params.get('key', None)
        if key and key in public_keys:
            queryset = queryset.filter(key=key)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_key(self, request):
        """
        Récupère une configuration par sa clé.
        """
        key = request.query_params.get('key', None)
        if not key:
            return Response({"detail": "Le paramètre 'key' est requis."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            config = self.get_queryset().get(key=key)
            serializer = self.get_serializer(config)
            return Response(serializer.data)
        except SystemConfiguration.DoesNotExist:
            return Response({"detail": f"Configuration '{key}' non trouvée."}, status=status.HTTP_404_NOT_FOUND)

