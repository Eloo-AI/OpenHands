import logging
from eloo.server.config import config

def setup_logging():
    """Configure logging for the entire application."""
    
    # Reset all existing loggers
    for logger_name in logging.root.manager.loggerDict:
        logging.getLogger(logger_name).handlers = []
        logging.getLogger(logger_name).setLevel(logging.ERROR)
        logging.getLogger(logger_name).propagate = False
    
    # Reset and configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.setLevel(logging.ERROR)
    
    # Configure eloo logger
    eloo_logger = logging.getLogger("eloo")
    eloo_logger.setLevel(getattr(logging, config.log_level))
    eloo_logger.propagate = False
    
    # Create and add handler for eloo logs
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(config.log_format))
    eloo_logger.addHandler(handler)
    
    return eloo_logger

# Initialize and export logger
logger = setup_logging() 