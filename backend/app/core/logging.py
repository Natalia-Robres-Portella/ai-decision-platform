import logging

import structlog


def setup_logging(debug: bool = False) -> None:
    """Configure structlog for structured, consistent log output.

    Why structlog instead of stdlib logging?
    - Every log call produces a dict, not a formatted string. That means logs
      are machine-parseable (grep, jq, Datadog, Grafana Loki all work natively).
    - Key-value context is first-class: logger.info("event", query=q, latency=t)
      instead of f-string concatenation you later can't query.
    - In development (debug=True) → human-readable coloured output via ConsoleRenderer.
    - In production (debug=False) → JSON lines, one per event, indexable by log aggregators.

    structlog wraps stdlib logging, so uvicorn's and SQLAlchemy's existing loggers
    are unaffected — they still emit their messages through the normal channel.
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,  # request-scoped context (e.g. request_id)
        structlog.stdlib.add_log_level,
        # NOTE: add_logger_name requires stdlib LoggerFactory (it reads logger.name).
        # We use PrintLoggerFactory + make_filtering_bound_logger, so we omit it.
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.dev.ConsoleRenderer()  # colour + alignment in dev
        if debug
        else structlog.processors.JSONRenderer()  # JSON lines in prod
    )

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib root logger so uvicorn / sqlalchemy logs go through
    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG if debug else logging.INFO,
    )
