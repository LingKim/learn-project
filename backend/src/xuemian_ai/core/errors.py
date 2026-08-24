from dataclasses import dataclass


@dataclass(slots=True)
class AppError(Exception):
    title: str
    detail: str
    status_code: int = 500
    error_type: str = "about:blank"
