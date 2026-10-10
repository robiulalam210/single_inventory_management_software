# myapp/base.py — minimal BaseInventoryViewSet stub (replace with your real base class)
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

class BaseInventoryViewSet(viewsets.ModelViewSet):
    """
    Minimal base viewset for inventory endpoints. Your real BaseInventoryViewSet
    likely defines authentication, permission, or common behavior — copy that in here.
    """
    permission_classes = [IsAuthenticated]
    # You can define common methods, parser_classes, etc. here.