"""
Logging configuration for the Binance Futures Trading Bot.
Provides structured, dual-channel logging: rotating file + colored console.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

# ── ANSI color codes for console output ────────────────────────────────────

RESET = "\033[0m"
BOLD  = "\033[1m"
COLORS = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Green
    "WARNING":  "\033[33m",   # Yellow
    "ERROR":    "\033[31m",   # Red
    "CRITICAL": "\033[35m",   # Magenta
}


class ColoredFormatter(logging.Formatter):
    """Human-friendly colored formatter for console output."""

    FMT = "{color}{bold}[{levelname:<8}]{reset} {asctime} | {name} | {message}"

    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelname, RESET)
        self._style._fmt = self.FMT.format(
            color=color,
            bold=BOLD,
            levelname=record.levelname,
            reset=RESET,
            asctime="%(asctime)s",
            name="%(name)s",
            message="%(message)s",
        )
        self.datefmt = "%H:%M:%S"
        return super().format(record)


class FileFormatter(logging.Formatter):
    """Plain structured formatter for log files (machine-readable)."""

    FORMAT = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
    )
    DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self):
        super().__init__(fmt=self.FORMAT, datefmt=self.DATEFMT)


def setup_logging(
    log_dir: str = "logs",
    log_file: str = "trading_bot.log",
    file_level: int = logging.DEBUG,
    console_level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,   # 5 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Configure and return the root application logger.

    Args:
        log_dir:       Directory where log files are written.
        log_file:      Base name of the rotating log file.
        file_level:    Minimum level captured in the log file.
        console_level: Minimum level printed to stdout.
        max_bytes:     Maximum size of a single log file before rotation.
        backup_count:  Number of rotated backup files to keep.

    Returns:
        Configured root logger for the application.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    logger = logging.getLogger("trading_bot")
    logger.setLevel(logging.DEBUG)          # let handlers filter independently

    if logger.handlers:                     # avoid duplicate handlers on re-init
        return logger

    # ── File handler (rotating) ────────────────────────────────────────────
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    fh.setLevel(file_level)
    fh.setFormatter(FileFormatter())

    # ── Console handler ────────────────────────────────────────────────────
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)
    ch.setFormatter(ColoredFormatter())

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.debug("Logging initialised — file: %s", log_path)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'trading_bot' hierarchy."""
    return logging.getLogger(f"trading_bot.{name}")
