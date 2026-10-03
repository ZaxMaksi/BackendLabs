from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.tasks.services import HealthCheckService


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Служебный эндпоинт health-check для мониторинга работоспособности сервиса."""
    try:
        data = HealthCheckService.check_health()
        return Response(data, status=status.HTTP_200_OK)
    except Exception as exc:
        return Response(
            {"status": "error", "detail": str(exc)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
