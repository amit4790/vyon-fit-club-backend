"""
Application Configuration
Centralized configuration management for the VYON Backend
"""

from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application Info
    environment: str = "development"
    debug: bool = True
    api_title: str = "VYON Fit Club Management API"
    api_version: str = "0.1.0"
    api_description: str = "Backend API for VYON Fit Club Management System"
    
    # CORS Settings
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Global settings instance
settings = Settings()
