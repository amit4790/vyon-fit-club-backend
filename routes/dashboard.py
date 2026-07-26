"""
Dashboard Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_admin_access
from schemas.dashboard import (
    AdminDashboardResponse,
    TrainerDashboardResponse,
    MemberDashboardResponse,
)
from services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get(
    "/admin",
    response_model=AdminDashboardResponse,
    summary="Admin Dashboard",
    description="Get admin dashboard with system statistics",
    responses={200: {"description": "Admin dashboard data retrieved successfully"}}
)
def get_admin_dashboard(
    _session=Depends(require_admin_access),
    db: Session = Depends(get_db),
) -> AdminDashboardResponse:
    """
    Admin dashboard endpoint
    
    Returns:
        AdminDashboardResponse: Admin dashboard with statistics
    """
    return DashboardService.get_admin_dashboard(db)


@router.get(
    "/trainer",
    response_model=TrainerDashboardResponse,
    summary="Trainer Dashboard",
    description="Get trainer dashboard with session and member information",
    responses={200: {"description": "Trainer dashboard data retrieved successfully"}}
)
def get_trainer_dashboard() -> TrainerDashboardResponse:
    """
    Trainer dashboard endpoint
    
    Returns:
        TrainerDashboardResponse: Trainer dashboard with sessions and statistics
    """
    return DashboardService.get_trainer_dashboard()


@router.get(
    "/member",
    response_model=MemberDashboardResponse,
    summary="Member Dashboard",
    description="Get member dashboard with membership and attendance information",
    responses={200: {"description": "Member dashboard data retrieved successfully"}}
)
def get_member_dashboard() -> MemberDashboardResponse:
    """
    Member dashboard endpoint
    
    Returns:
        MemberDashboardResponse: Member dashboard with membership and attendance data
    """
    return DashboardService.get_member_dashboard()
