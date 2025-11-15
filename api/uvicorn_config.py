"""Uvicorn configuration for the FastAPI application."""
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        },
        "access": {
            "format": "%(asctime)s | %(levelname)s | %(client_addr)s -> %(request_line)s | %(status_code)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
        },
        "application_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "level": "INFO",
            "filename": str(LOG_DIR / "application.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
        },
        "uvicorn_error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "level": "INFO",
            "filename": str(LOG_DIR / "uvicorn.error.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
        },
        "uvicorn_access_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "access",
            "level": "INFO",
            "filename": str(LOG_DIR / "uvicorn.access.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
        },
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["console", "application_file"],
            "level": "INFO",
        },
        "uvicorn": {
            "handlers": ["console", "uvicorn_error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["console", "uvicorn_error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["uvicorn_access_file"],
            "level": "INFO",
            "propagate": False,
        },
        "app_dia": {
            "handlers": ["application_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

UVICORN_CONFIG = {
    "app": "app_dia:app",
    "host": "0.0.0.0",
    "port": 60001,
    "workers": 8,
    "log_config": LOG_CONFIG,
    "log_level": "info",
}

__all__ = ["UVICORN_CONFIG", "LOG_CONFIG", "LOG_DIR"]
