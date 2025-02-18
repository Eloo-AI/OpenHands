import os
from typing import List
from dotenv import load_dotenv

class Config:
    """Server configuration handler."""
    
    def __init__(self):
        load_dotenv()
        
        # Server
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        
        # Logging
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_format: str = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        
        # CORS
        cors_origins = os.getenv("CORS_ORIGINS", "*")
        self.cors_origins: List[str] = [x.strip() for x in cors_origins.split(",")]

config = Config() 