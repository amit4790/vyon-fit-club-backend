"""
Routes Package
API route handlers
"""

from .health import router as health_router
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .admin import router as admin_router
from .device import router as device_router, mgmt_router as device_mgmt_router
from .mobile_auth import router as mobile_auth_router
from .member import router as member_router
from .trainer import router as trainer_router
from .internal import router as internal_router

__all__ = [
    "health_router",
    "auth_router",
    "dashboard_router",
    "admin_router",
    "device_router",
    "device_mgmt_router",
    "mobile_auth_router",
    "member_router",
    "trainer_router",
    "internal_router",
]
