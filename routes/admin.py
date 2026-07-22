"""
Admin routes for VYON FIT CLUB.
Handles admin dashboard and management endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/dashboard")
async def get_admin_dashboard():
    """
    Get admin dashboard data.
    """
    return {
        "message": "Admin dashboard",
        "data": {
            "total_members": 150,
            "active_trainers": 12,
            "revenue_month": "$15,000",
            "occupancy_rate": "85%"
        }
    }


@router.get("/members")
async def get_members():
    """
    Get list of all members.
    """
    return {
        "message": "Members list",
        "data": [
            {"id": 1, "name": "Alice Wilson", "email": "alice@email.com", "status": "active"},
            {"id": 2, "name": "Bob Johnson", "email": "bob@email.com", "status": "active"},
            {"id": 3, "name": "Carol Martinez", "email": "carol@email.com", "status": "active"}
        ]
    }


@router.get("/trainers")
async def get_trainers():
    """
    Get list of all trainers.
    """
    return {
        "message": "Trainers list",
        "data": [
            {"id": 1, "name": "John Smith", "specialization": "Strength Training", "clients": 8},
            {"id": 2, "name": "Sarah Johnson", "specialization": "Cardio & HIIT", "clients": 10},
            {"id": 3, "name": "Mike Davis", "specialization": "Flexibility & Yoga", "clients": 6}
        ]
    }


@router.get("/classes")
async def get_classes():
    """
    Get list of all classes.
    """
    return {
        "message": "Classes list",
        "data": [
            {"id": 1, "name": "Morning Yoga", "trainer": "Sarah Johnson", "capacity": 20},
            {"id": 2, "name": "Evening Strength", "trainer": "John Smith", "capacity": 25},
            {"id": 3, "name": "HIIT Bootcamp", "trainer": "Sarah Johnson", "capacity": 15}
        ]
    }
