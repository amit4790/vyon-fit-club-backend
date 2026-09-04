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

    # ZKTeco device settings (legacy pyzk/Standalone SDK)
    zkteco_device_host: str = "192.168.31.218"
    zkteco_device_port: int = 4370
    zkteco_device_id: int = 1
    zkteco_communication_key: int = 0
    zkteco_timeout_seconds: int = 10
    zkteco_force_udp: bool = False
    zkteco_map_6001_to_unauth: bool = True
    zkteco_omit_ping: bool = True
    zkteco_encoding: str = "UTF-8"

    # ZKTeco PUSH Protocol settings (official iClock/ADMS HTTP protocol)
    device_push_enabled: bool = True
    # Full raw payload logging (Render logs / extras). Keep false in production.
    device_push_log_raw: bool = False
    # Device ATTLOG timestamps are local wall clock with no offset (gym is India).
    device_timezone: str = "Asia/Kolkata"
    # Throttle push_devices.last_seen writes (seconds) for heartbeats/empty polls.
    # POST cdata/devicecmd force-touch so real device traffic keeps Neon warm enough
    # for ZKTeco's short upload timeouts.
    device_presence_write_interval_seconds: int = 120
    # After an empty command poll, skip DB briefly. Keep short — long windows plus a
    # sleeping Neon caused the device to miss ATTLOG uploads after churn cuts.
    device_empty_poll_skip_seconds: int = 30
    # Only these cdata tables are written to device_attendance_logs (comma-separated).
    # OPERLOG/BIODATA are ack'd without insert. Set "ATTLOG,USERINFO" while debugging sync.
    device_persist_cdata_tables: str = "ATTLOG"
    # Retention: punches kept longer for payroll; raw blobs are debug-only.
    attendance_punch_retention_days: int = 90
    device_raw_log_retention_days: int = 14
    # Shared secret for POST /api/internal/cron/* (Render Cron Job header X-Cron-Secret).
    cron_secret: str = ""

    # Production administrator bootstrap settings
    super_admin_email: str = "admin@vyonfitclub.com"
    super_admin_name: str = "VYON Administrator"
    super_admin_password: str = ""

    # JWT settings
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # Mobile OTP / PIN auth
    mobile_otp_ttl_seconds: int = 300
    mobile_otp_session_ttl_minutes: int = 10
    mobile_otp_max_verify_attempts: int = 5
    mobile_pin_min_length: int = 4
    mobile_pin_max_length: int = 6
    mobile_pin_max_failed_attempts: int = 5
    mobile_pin_lockout_minutes: int = 15

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
    def device_persist_cdata_table_set(self) -> set[str]:
        """Uppercase table names allowed to persist into device_attendance_logs."""
        return {
            part.strip().upper()
            for part in self.device_persist_cdata_tables.split(",")
            if part.strip()
        }

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

        if self.zkteco_device_port <= 0:
            raise ValueError("ZKTECO_DEVICE_PORT must be greater than zero")

        if self.zkteco_timeout_seconds <= 0:
            raise ValueError("ZKTECO_TIMEOUT_SECONDS must be greater than zero")

        if self.zkteco_device_id <= 0:
            raise ValueError("ZKTECO_DEVICE_ID must be greater than zero")

        if self.is_production_like_environment and not self.jwt_secret_key.strip():
            raise ValueError("JWT_SECRET_KEY is required in production-like environments")

        # Resolve secret once during startup to surface config errors early.
        _ = self.effective_jwt_secret_key


# Global settings instance
settings = Settings()
