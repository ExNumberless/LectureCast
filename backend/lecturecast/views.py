from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok"])


@extend_schema(responses=HealthResponseSerializer)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Report that the API is up and can reach the database."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return Response({"status": "ok"})
