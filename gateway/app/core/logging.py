"""Configuración centralizada de logging estructurado (structlog + JSON)."""

import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configura logging estándar y structlog con salida JSON y nivel indicado."""
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )
