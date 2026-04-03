"""
Logging configuration using Loguru.
Provides structured logging for the application.
"""
import sys
from pathlib import Path
from loguru import logger

from app.core.config import settings

# Remove default logger
logger.remove()

# Create logs directory
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Console logging format
console_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

# File logging format
file_format = (
    "{time:YYYY-MM-DD HH:mm:ss} | "
    "{level: <8} | "
    "{name}:{function}:{line} | "
    "{message}"
)

# Add console handler
logger.add(
    sys.stdout,
    format=console_format,
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True,
)

# Add file handler for all logs
logger.add(
    log_dir / "app.log",
    format=file_format,
    level="DEBUG",
    rotation="100 MB",
    retention="30 days",
    compression="zip",
)

# Add file handler for errors only
logger.add(
    log_dir / "error.log",
    format=file_format,
    level="ERROR",
    rotation="100 MB",
    retention="60 days",
    compression="zip",
)


def get_logger(name: str):
    """
    Get logger instance with specific name.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Logger instance
    """
    return logger.bind(name=name)
