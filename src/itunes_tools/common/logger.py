import logging
import os


def get_logger(script_name: str) -> logging.Logger:
    """Return a pre-configured logger."""
    logger = logging.getLogger(script_name)
    logger.setLevel(os.environ.get("ITUNES_TOOLSLOG_LEVEL", "DEBUG"))
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger
