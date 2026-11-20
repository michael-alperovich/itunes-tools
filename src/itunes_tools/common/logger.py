import logging
import os

LOG_LEVEL_ENV_VAR = "ITUNES_TOOLS_LOG_LEVEL"
DEFAULT_LOG_LEVEL = "DEBUG"


def get_logger(script_name: str) -> logging.Logger:
    """Return a pre-configured logger that writes to the console.

    The level comes from the ``ITUNES_TOOLS_LOG_LEVEL`` environment variable (case-insensitive,
    default ``DEBUG``). An unknown value falls back to the default with a warning instead of failing.

    Safe to call repeatedly with the same name: the console handler is added only once.
    The logger does not propagate to the root logger, so configuring root logging elsewhere
    (for example with ``logging.basicConfig``) does not print every message twice. As a side effect,
    pytest's ``caplog`` does not see these records; use ``capsys`` in tests instead.
    """
    logger = logging.getLogger(script_name)
    level_name = os.environ.get(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL).strip().upper()
    level = logging.getLevelNamesMapping().get(level_name)
    logger.setLevel(level if level is not None else DEFAULT_LOG_LEVEL)
    logger.propagate = False

    # Loggers are process-wide singletons, so a second call must not add a second handler.
    # Check this logger's own handlers, not hasHandlers(), which also counts ancestors such as root.
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if level is None:
        logger.warning("Unknown %s value %r; using %s", LOG_LEVEL_ENV_VAR, level_name, DEFAULT_LOG_LEVEL)
    return logger
