"""
Schemas Package
Pydantic request and response models
"""

from .auth import LoginRequest, LoginResponse, UserInfo
from .dashboard import (
    AdminDashboardResponse,
    TrainerDashboardResponse,
    MemberDashboardResponse,
)
from .health import HealthResponse

__all__ = [
    "LoginRequest",
    "LoginResponse",
    "UserInfo",
    "AdminDashboardResponse",
    "TrainerDashboardResponse",
    "MemberDashboardResponse",
    "HealthResponse",
]
