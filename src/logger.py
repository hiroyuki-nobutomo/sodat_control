import logging
import sys
from typing import Optional

class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())

    def flush(self):
        pass

def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """
    Configures the root logger for the application.
    Outputs to both stdout and an optional log file.
    
    File output is ALWAYS DEBUG level.
    Console output is user-configurable (default INFO).
    Captures stdout/stderr into the log file.
    """
    # Map string level to logging constants
    console_level = getattr(logging, level.upper(), logging.INFO)
    file_level = logging.DEBUG  # File always gets everything
    
    # Define log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)
    
    # Configure root logger to the MOST verbose level needed (DEBUG)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) 
    
    # Clear existing handlers
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    
    # Console Handler (Filters to user level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File Handler (Filters to DEBUG - catch all)
    if log_file:
        from logging.handlers import TimedRotatingFileHandler
        # Rotate at midnight, keep 7 days of backup
        file_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7)
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Redirect stdout and stderr to logger
    # Only if not running under pytest (to avoid recursion or breaking test output)
    if "pytest" not in sys.modules and "unittest" not in sys.modules:
        sys.stdout = StreamToLogger(logging.getLogger('STDOUT'), logging.INFO)
        sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.ERROR)

    logging.debug(f"Logging initialized. Console: {level}, File: DEBUG")
