"""
Member routes for VYON FIT CLUB.
Handles member-specific endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/member", tags=["member"])


@router.get("/dashboard")
async def get_member_dashboard():
    """
    Get member dashboard data.
    """
    return {
        "message": "Member dashboard",
        "data": {
            "member_id": 1,
            "name": "Alice Wilson",
            "membership_type": "Premium",
            "visits_month": 12,
            "classes_enrolled": 3
        }
    }


@router.get("/profile")
async def get_member_profile():
    """
    Get member profile information.
    """
    return {
        "message": "Member profile",
        "data": {
            "id": 1,
            "name": "Alice Wilson",
            "email": "alice@email.com",
            "membership_type": "Premium",
            "join_date": "2023-01-15",
            "status": "active"
        }
    }


@router.get("/classes")
async def get_member_classes():
    """
    Get member's enrolled classes.
    """
    return {
        "message": "Member classes",
        "data": [
            {"id": 1, "name": "Morning Yoga", "trainer": "Sarah Johnson", "next_session": "2024-01-15"},
            {"id": 2, "name": "Evening Strength", "trainer": "John Smith", "next_session": "2024-01-16"},
            {"id": 3, "name": "HIIT Bootcamp", "trainer": "Sarah Johnson", "next_session": "2024-01-17"}
        ]
    }


@router.get("/bookings")
async def get_member_bookings():
    """
    Get member's training session bookings.
    """
    return {
        "message": "Member bookings",
        "data": [
            {"id": 1, "trainer": "John Smith", "date": "2024-01-15", "time": "5:00 PM", "status": "confirmed"},
            {"id": 2, "trainer": "Sarah Johnson", "date": "2024-01-16", "time": "6:00 AM", "status": "confirmed"}
        ]
    }
