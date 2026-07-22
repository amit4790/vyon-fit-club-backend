"""
Trainer routes for VYON FIT CLUB.
Handles trainer-specific endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/trainer", tags=["trainer"])


@router.get("/dashboard")
async def get_trainer_dashboard():
    """
    Get trainer dashboard data.
    """
    return {
        "message": "Trainer dashboard",
        "data": {
            "trainer_id": 1,
            "name": "John Smith",
            "clients": 8,
            "classes_today": 2,
            "upcoming_sessions": 5
        }
    }


@router.get("/clients")
async def get_trainer_clients():
    """
    Get clients assigned to trainer.
    """
    return {
        "message": "Trainer clients",
        "data": [
            {"id": 1, "name": "Alice Wilson", "session_date": "2024-01-15", "status": "confirmed"},
            {"id": 2, "name": "Bob Johnson", "session_date": "2024-01-16", "status": "pending"},
            {"id": 3, "name": "Carol Martinez", "session_date": "2024-01-17", "status": "confirmed"}
        ]
    }


@router.get("/schedule")
async def get_trainer_schedule():
    """
    Get trainer's class schedule.
    """
    return {
        "message": "Trainer schedule",
        "data": [
            {"class_id": 1, "name": "Morning Session", "time": "6:00 AM", "capacity": 20},
            {"class_id": 2, "name": "Evening Session", "time": "6:30 PM", "capacity": 25}
        ]
    }
