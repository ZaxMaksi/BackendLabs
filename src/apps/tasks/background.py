import concurrent.futures
import logging
import uuid
from enum import Enum
from typing import Any, Callable, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


class BackgroundTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundTaskStore:
    """Thread-safe сховище стану фонових завдань за допомогою Django Cache (LocMemCache)."""

    CACHE_PREFIX = "bg_task_"

    @classmethod
    def _key(cls, job_id: str) -> str:
        return f"{cls.CACHE_PREFIX}{job_id}"

    @classmethod
    def set(cls, job_id: str, data: dict[str, Any], timeout: int = 86400) -> None:
        cache.set(cls._key(job_id), data, timeout=timeout)

    @classmethod
    def get(cls, job_id: str) -> Optional[dict[str, Any]]:
        return cache.get(cls._key(job_id))

    @classmethod
    def update(cls, job_id: str, **fields) -> Optional[dict[str, Any]]:
        current = cls.get(job_id)
        if current is not None:
            current.update(fields)
            cls.set(job_id, current)
            return current
        return None

    @classmethod
    def clear(cls, job_id: str) -> None:
        cache.delete(cls._key(job_id))


class BackgroundTaskExecutor:
    """
    Singleton фонового пулу потоків (ThreadPoolExecutor) для опрацювання
    довготривалих операцій без зовнішнього брокера повідомлень.
    """

    _instance: Optional["BackgroundTaskExecutor"] = None

    def __new__(cls) -> "BackgroundTaskExecutor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            max_workers = getattr(settings, "BACKGROUND_TASK_MAX_WORKERS", 4)
            cls._instance.executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="task_tracker_worker",
            )
            cls._instance.store = BackgroundTaskStore
        return cls._instance

    def submit_task(
        self,
        job_type: str,
        target_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        job_id = str(uuid.uuid4())
        task_data = {
            "job_id": job_id,
            "job_type": job_type,
            "status": BackgroundTaskStatus.PENDING.value,
            "created_at": timezone.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }
        self.store.set(job_id, task_data)

        self.executor.submit(self._run_wrapper, job_id, target_fn, *args, **kwargs)
        return job_id

    def _run_wrapper(
        self,
        job_id: str,
        target_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.store.update(
            job_id,
            status=BackgroundTaskStatus.RUNNING.value,
            started_at=timezone.now().isoformat(),
        )
        try:
            result = target_fn(*args, **kwargs)
            self.store.update(
                job_id,
                status=BackgroundTaskStatus.COMPLETED.value,
                completed_at=timezone.now().isoformat(),
                result=result,
            )
        except Exception as exc:
            logger.exception("Error executing background task %s: %s", job_id, exc)
            self.store.update(
                job_id,
                status=BackgroundTaskStatus.FAILED.value,
                completed_at=timezone.now().isoformat(),
                error=str(exc),
            )
        finally:
            connection.close()

    def get_task_status(self, job_id: str) -> Optional[dict[str, Any]]:
        return self.store.get(job_id)
