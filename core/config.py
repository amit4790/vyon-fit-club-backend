"""
Application Configuration
Centralized configuration management for the VYON Backend.
"""

import secrets
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application Info
    environment: str = "development"
    debug: bool = True
    api_title: str = "VYON Fit Club Management API"
    api_version: str = "0.1.0"
    api_description: str = "Backend API for VYON Fit Club Management System"

    # CORS Settings
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Database Settings
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/vyonfitclub"

    # Production administrator bootstrap settings
    super_admin_email: str = "admin@vyonfitclub.com"
    super_admin_name: str = "VYON Administrator"
    super_admin_password: str = ""

    # JWT settings
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    _generated_jwt_secret: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def environment_name(self) -> str:
        return self.environment.strip().lower()

    @property
    def is_local_environment(self) -> bool:
        return self.environment_name in {"development", "dev", "local", "test"}

    @property
    def is_production_like_environment(self) -> bool:
        return self.environment_name in {"production", "prod", "staging", "stage"}

    @property
    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def effective_jwt_secret_key(self) -> str:
        """Resolve JWT secret, allowing a temporary local-only fallback.

        Development/local/test can auto-generate a process-local random secret so
        contributors can run the app without secret provisioning.
        """
        if self.jwt_secret_key.strip():
            return self.jwt_secret_key.strip()

        if self.is_local_environment:
            if self._generated_jwt_secret is None:
                self._generated_jwt_secret = secrets.token_urlsafe(64)
            return self._generated_jwt_secret

        raise ValueError("JWT_SECRET_KEY is required when environment is not local development")

    def validate_jwt_configuration(self) -> None:
        """Validate JWT settings at startup for fail-fast production safety.

        Production-like environments must always provide JWT_SECRET_KEY through
        environment configuration. Local environments may rely on fallback.
        """
        if self.jwt_algorithm.strip().upper() != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")

        if self.access_token_expire_minutes <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero")

        if self.is_production_like_environment and not self.jwt_secret_key.strip():
            raise ValueError("JWT_SECRET_KEY is required in production-like environments")

        # Resolve secret once during startup to surface config errors early.
        _ = self.effective_jwt_secret_key


# Global settings instance
settings = Settings()
