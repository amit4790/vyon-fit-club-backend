"""
Routes Package
API route handlers
"""

from .health import router as health_router
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .admin import router as admin_router

__all__ = ["health_router", "auth_router", "dashboard_router", "admin_router"]
