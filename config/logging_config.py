import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Define log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Create a logger instance
logger = logging.getLogger("yuanfang_digital_employee")
logger.setLevel(logging.DEBUG) # Set default level to DEBUG; can be overridden by handlers

# Ensure the 'logs' directory exists
log_dir = Path(__file__).resolve().parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file_path = log_dir / "app.log"

def setup_logging(log_level: str = "INFO", structured: bool = False):
    """
    Configures logging for the application.
    """
    # Remove any existing handlers to prevent duplicate logging
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # File Handler (Rotating)
    # Rotate logs at 5MB, keep 5 backup logs
    file_handler = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG) # Log DEBUG level and above to file

    if structured:
        # Example for structured logging (e.g., using python-json-logger)
        # from pythonjsonlogger import jsonlogger
        # formatter = jsonlogger.JsonFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        # For now, using standard formatter. If python-json-logger is added to requirements,
        # this can be enabled.
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        logger.warning("Structured logging requested but not fully implemented with specialized library. Using standard formatter.")
    else:
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    logger.info(f"Logging configured. Level: {log_level}. Log file: {log_file_path}")

# To make the logger easily importable
def get_logger(name: str):
    return logging.getLogger(f"yuanfang_digital_employee.{name}")

# Example of how to use it in other modules:
# from config.logging_config import get_logger
# logger = get_logger(__name__)
# logger.info("This is an info message.")
# logger.debug("This is a debug message.")
# logger.error("This is an error message.")
