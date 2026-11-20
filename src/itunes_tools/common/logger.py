import logging
import os


def get_logger(script_name: str) -> logging.Logger:
    """Return a pre-configured logger.

    Safe to call repeatedly with the same name: the console handler is added only once.
    """
    logger = logging.getLogger(script_name)
    logger.setLevel(os.environ.get("ITUNES_TOOLS_LOG_LEVEL", "DEBUG"))
    # Loggers are process-wide singletons, so a second call must not add a second handler.
    # Check this logger's own handlers, not hasHandlers(), which also counts ancestors such as root.
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger
