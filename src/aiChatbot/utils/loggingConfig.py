"""
Cloud Run optimized logging configuration.
Structured JSON logging for production, text for local development.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class CloudRunJSONFormatter(logging.Formatter):
    """JSON formatter optimized for Cloud Run."""
    
    def format(self, record: logging.LogRecord) -> str:
        severity_map = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO",
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL",
        }
        
        log_entry: Dict[str, Any] = {
            "severity": severity_map.get(record.levelno, "INFO"),
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "__dict__"):
            standard_fields = {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs", "message",
                "pathname", "process", "processName", "relativeCreated", "thread",
                "threadName", "exc_info", "exc_text", "stack_info", "taskName"
            }
            
            for key, value in record.__dict__.items():
                if key not in standard_fields and not key.startswith("_"):
                    try:
                        json.dumps(value)
                        log_entry[key] = value
                    except (TypeError, ValueError):
                        log_entry[key] = str(value)
        
        return json.dumps(log_entry, ensure_ascii=False)


class CloudRunTextFormatter(logging.Formatter):
    """Human-readable text formatter for local development."""
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        level = record.levelname.ljust(8)
        logger_name = record.name
        message = record.getMessage()
        
        extra_fields = []
        if hasattr(record, "__dict__"):
            standard_fields = {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs", "message",
                "pathname", "process", "processName", "relativeCreated", "thread",
                "threadName", "exc_info", "exc_text", "stack_info", "taskName"
            }
            
            for key, value in record.__dict__.items():
                if key not in standard_fields and not key.startswith("_"):
                    extra_fields.append(f"{key}={value}")
        
        context_str = f" [{', '.join(extra_fields)}]" if extra_fields else ""
        
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            return f"{timestamp} | {level} | {logger_name} | {message}{context_str}\n{exc_text}"
        
        return f"{timestamp} | {level} | {logger_name} | {message}{context_str}"


def setupLogging(
    level: str = "INFO",
    format_type: str = "json",
    enable_correlation_ids: bool = True
) -> None:
    """Configure logging for Cloud Run or local development."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    if format_type.lower() == "json":
        formatter = CloudRunJSONFormatter()
    else:
        formatter = CloudRunTextFormatter()
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Reduce noise from external libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={"level": level, "format": format_type}
    )
