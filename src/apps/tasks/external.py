import logging
from typing import Any, Optional

import requests
from django.conf import settings
from django.core.cache import cache

from apps.tasks.services import (
    ExternalServiceConnectionError,
    ExternalServiceError,
    ExternalServiceTimeoutError,
)

logger = logging.getLogger(__name__)


class ExternalCalendarService:
    """
    Клієнт зовнішнього REST API (виробничий календар / державні свята)
    зі стійкою обробкою таймаутів, мережевих помилок та кешуванням у пам'яті (LocMemCache).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        cache_ttl: Optional[int] = None,
    ):
        self.base_url = (
            base_url or getattr(settings, "EXTERNAL_API_BASE_URL", "https://date.nager.at/api/v3")
        ).rstrip("/")
        self.timeout = (
            timeout
            if timeout is not None
            else getattr(settings, "EXTERNAL_API_TIMEOUT", 3.0)
        )
        self.cache_ttl = (
            cache_ttl
            if cache_ttl is not None
            else getattr(settings, "EXTERNAL_API_CACHE_TTL", 300)
        )

    def _cache_key(self, country_code: str, year: int) -> str:
        return f"external_holidays_{country_code.upper()}_{year}"

    def get_public_holidays(
        self, year: int, country_code: str = "UA"
    ) -> dict[str, Any]:
        """
        Отримує перелік державних свят для вказаного року та країни.
        Спочатку перевіряє In-Memory Cache (LocMemCache).
        У разі відсутності виконує HTTP GET до зовнішнього REST API.
        """
        normalized_country = country_code.strip().upper()
        cache_key = self._cache_key(normalized_country, year)

        # 1. Перевірка кешу
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            logger.info(
                "Serving public holidays for %s/%s from cache.",
                normalized_country,
                year,
            )
            return {
                "country_code": normalized_country,
                "year": year,
                "cached": True,
                "total_holidays": len(cached_data),
                "holidays": cached_data,
            }

        # 2. Виклик зовнішнього сервісу з таймаутом
        url = f"{self.base_url}/PublicHolidays/{year}/{normalized_country}"
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "TaskTrackerApp/1.0",
                },
            )
            response.raise_for_status()
            holidays = response.json()
        except requests.exceptions.Timeout as exc:
            logger.error("Timeout connecting to external API %s: %s", url, exc)
            raise ExternalServiceTimeoutError(
                f"External calendar service timed out after {self.timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Connection error to external API %s: %s", url, exc)
            raise ExternalServiceConnectionError(
                "Unable to connect to external calendar service (network/connection error)."
            ) from exc
        except requests.exceptions.HTTPError as exc:
            logger.error("HTTP error from external API %s: %s", url, exc)
            raise ExternalServiceError(
                f"External calendar service returned HTTP error: {response.status_code}."
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.error("Unexpected error contacting external API %s: %s", url, exc)
            raise ExternalServiceError(
                f"External service request failed: {exc}"
            ) from exc

        # 3. Збереження результату у кеш
        cache.set(cache_key, holidays, timeout=self.cache_ttl)

        return {
            "country_code": normalized_country,
            "year": year,
            "cached": False,
            "total_holidays": len(holidays),
            "holidays": holidays,
        }
