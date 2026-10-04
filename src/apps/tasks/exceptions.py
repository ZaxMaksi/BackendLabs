import http.client
from typing import Any, Optional

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.tasks.services import BadRequestError, EntityNotFoundError
from apps.tasks.services import ValidationError as ServiceValidationError


def _format_error_detail(detail: Any) -> tuple[str, Optional[Any]]:
    """Преобразует детали ошибки DRF в текстовое пояснение detail и структуру invalid_params."""
    if isinstance(detail, str):
        return detail, None

    if isinstance(detail, list):
        items = [_format_error_detail(item)[0] for item in detail]
        return "; ".join(items), detail

    if isinstance(detail, dict):
        messages = []
        for field, errs in detail.items():
            field_msg = _format_error_detail(errs)[0]
            messages.append(f"{field}: {field_msg}")
        return "Validation failed: " + "; ".join(messages), detail

    return str(detail), None


def custom_exception_handler(
    exc: Exception, context: dict[str, Any]
) -> Optional[Response]:
    """
    Кастомный обработчик исключений для стандартизации ответов об ошибках
    в единый JSON-формат RFC 7807 (Problem Details for HTTP APIs).

    Поля ответа:
    - type: URI-идентификатор типа проблемы
    - title: Краткое описание статуса ошибки
    - status: Числовой HTTP-код статуса
    - detail: Подробное сообщение об ошибке
    - instance: URI запрошенного ресурса
    - invalid_params: Словарь ошибок валидации полей (при наличии)
    """
    request = context.get("request")
    instance = request.path if request else ""

    # 1. Маппинг специфичных исключений приложения и Django к DRF APIException / статус-кодам
    status_code: int
    title: str
    detail_msg: str
    invalid_params: Optional[Any] = None

    if isinstance(exc, EntityNotFoundError) or isinstance(exc, Http404):
        status_code = status.HTTP_404_NOT_FOUND
        title = "Not Found"
        detail_msg = str(exc) or "Resource not found."

    elif isinstance(exc, BadRequestError) or isinstance(exc, drf_exceptions.ParseError):
        status_code = status.HTTP_400_BAD_REQUEST
        title = "Bad Request"
        detail_msg = (
            str(exc)
            if isinstance(exc, BadRequestError)
            else (getattr(exc, "detail", str(exc)) or "Bad Request.")
        )

    elif isinstance(exc, (ServiceValidationError, DjangoValidationError)):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        title = "Unprocessable Entity"
        if hasattr(exc, "message_dict"):
            detail_msg, invalid_params = _format_error_detail(exc.message_dict)
        elif hasattr(exc, "messages"):
            detail_msg, invalid_params = _format_error_detail(exc.messages)
        else:
            detail_msg = str(exc)
            invalid_params = {"detail": [detail_msg]}

    elif isinstance(exc, drf_exceptions.ValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        title = "Unprocessable Entity"
        raw_detail = getattr(exc, "detail", str(exc))
        detail_msg, invalid_params = _format_error_detail(raw_detail)

    elif isinstance(
        exc, (drf_exceptions.AuthenticationFailed, drf_exceptions.NotAuthenticated)
    ):
        status_code = status.HTTP_401_UNAUTHORIZED
        title = "Unauthorized"
        detail_msg = (
            getattr(exc, "detail", str(exc))
            or "Authentication credentials were not provided or are invalid."
        )

    elif isinstance(exc, (drf_exceptions.PermissionDenied, DjangoPermissionDenied)):
        status_code = status.HTTP_403_FORBIDDEN
        title = "Forbidden"
        detail_msg = (
            getattr(exc, "detail", str(exc))
            or "You do not have permission to perform this action."
        )

    elif isinstance(exc, drf_exceptions.MethodNotAllowed):
        status_code = status.HTTP_405_METHOD_NOT_ALLOWED
        title = "Method Not Allowed"
        detail_msg = (
            getattr(exc, "detail", str(exc))
            or f"Method {request.method if request else ''} not allowed."
        )

    elif isinstance(exc, drf_exceptions.APIException):
        status_code = exc.status_code
        title = http.client.responses.get(status_code, "Error")
        raw_detail = getattr(exc, "detail", str(exc))
        detail_msg, invalid_params = _format_error_detail(raw_detail)

    else:
        # Попытка обработать стандартным обработчиком DRF
        response = exception_handler(exc, context)
        if response is not None:
            status_code = response.status_code
            title = http.client.responses.get(status_code, "Error")
            detail_msg, invalid_params = _format_error_detail(response.data)
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            title = "Internal Server Error"
            detail_msg = "An unexpected internal server error occurred."

    # Нормализация слага типа проблемы
    slug = title.lower().replace(" ", "-")
    problem_type = f"urn:problem-type:{slug}"

    data: dict[str, Any] = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": str(detail_msg),
        "instance": instance,
    }

    if invalid_params is not None:
        data["invalid_params"] = invalid_params

    return Response(data, status=status_code)
