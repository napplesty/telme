"""Logger configuration module."""
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def get_logger(name: Optional[str] = None, log_file: Optional[Path] = None):
    """Get a configured logger instance.

    Args:
        name: Logger name (usually __name__).
        log_file: Optional log file path.

    Returns:
        Configured logger instance.
    """
    # Remove default handler
    logger.remove()

    # Add console handler with custom format
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    # Add file handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="7 days",
            compression="zip",
        )

    # Return logger with name context
    if name:
        return logger.bind(name=name)
    return logger


# Create default logger
default_logger = get_logger("telme")
