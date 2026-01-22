import logging
import sys
from typing import Optional

# ANSI color codes for terminal output
class Colors:
    GREY = "\033[90m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;91m"
    RESET = "\033[0m"

# Custom formatter with colors
class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt, datefmt)
        self.LEVEL_COLORS = {
            logging.DEBUG: Colors.BLUE,
            logging.INFO: Colors.GREEN,
            logging.WARNING: Colors.YELLOW,
            logging.ERROR: Colors.RED,
            logging.CRITICAL: Colors.BOLD_RED,
        }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.LEVEL_COLORS.get(record.levelno, Colors.GREY)
        record.levelname = f"{log_color}{record.levelname}{Colors.RESET}"
        return super().format(record)


# Create logger
logger = logging.getLogger("MoneyDahong")
logger.setLevel(logging.DEBUG)  # Capture all levels

# Prevent propagation to avoid duplicate logs
logger.propagate = False

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)  # Default to INFO level for console

# Console format: [TIME] [LEVEL] [MODULE] Message
console_format = "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
console_datefmt = "%Y-%m-%d %H:%M:%S"
console_formatter = ColoredFormatter(console_format, console_datefmt)
console_handler.setFormatter(console_formatter)

# File handler (optional, set level to DEBUG for detailed logs)
file_handler = logging.FileHandler("money_dahong.log", mode="a", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_format = "[%(asctime)s] [%(levelname)-8s] [%(name)s:%(lineno)d] %(message)s"
file_datefmt = "%Y-%m-%d %H:%M:%S"
file_formatter = logging.Formatter(file_format, file_datefmt)
file_handler.setFormatter(file_formatter)

# Add handlers to logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(f"MoneyDahong.{name}")
