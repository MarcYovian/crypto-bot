import os
import sys
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(name: str = "crypto_bot") -> logging.Logger:
    """Menyiapkan logger terstandarisasi dengan output ke Console (stdout) dan Rotating File."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Mencegah duplikasi handler jika fungsi dipanggil ulang
    if logger.handlers:
        return logger
        
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 1. Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 2. Rotating File Handler (maks 10MB per file, simpan 5 cadangan)
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

# Shared global logger
logger = setup_logger()
