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
from .member import (
    MemberCreateRequest,
    MemberDeleteResponse,
    MemberListResponse,
    MemberOperationResponse,
    MemberResponse,
    MemberUpdateRequest,
)

__all__ = [
    "LoginRequest",
    "LoginResponse",
    "UserInfo",
    "AdminDashboardResponse",
    "TrainerDashboardResponse",
    "MemberDashboardResponse",
    "HealthResponse",
    "MemberCreateRequest",
    "MemberUpdateRequest",
    "MemberResponse",
    "MemberListResponse",
    "MemberOperationResponse",
    "MemberDeleteResponse",
]
