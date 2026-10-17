from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetryableError(RuntimeError):
    pass


def is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def retry(operation: Callable[[], T], max_retries: int) -> T:
    attempt = 0
    while True:
        try:
            return operation()
        except RetryableError:
            if attempt >= max_retries:
                raise
            attempt += 1
