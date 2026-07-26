"""
Dashboard Schemas
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class StatCard(BaseModel):
    """Generic statistics card model"""
    
    label: str = Field(..., description="Statistic label")
    value: str | int = Field(..., description="Statistic value")
    trend: Optional[str] = Field(None, description="Trend indicator (up/down/neutral)")


class RecentRegistration(BaseModel):
    """Recent registration model"""
    
    name: str
    email: str | None
    registration_date: str


class AdminDashboardResponse(BaseModel):
    """Admin dashboard response model"""
    
    total_members: int = Field(..., description="Total number of members")
    active_members: int = Field(..., description="Currently active members")
    total_trainers: int | None = Field(None, description="Currently active trainers")
    inactive_members: int | None = Field(None, description="Currently inactive members")
    monthly_revenue: float | None = Field(None, description="Revenue this month")
    expiring_memberships: int | None = Field(None, description="Memberships expiring this month")
    todays_checkins: int | None = Field(None, description="Check-ins today")
    recent_registrations: List[RecentRegistration] = Field(..., description="Recently registered members")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_members": 250,
                "active_members": 185,
                "total_trainers": 16,
                "inactive_members": 65,
                "monthly_revenue": None,
                "expiring_memberships": None,
                "todays_checkins": None,
                "recent_registrations": [
                    {
                        "name": "Alice Johnson",
                        "email": "alice@example.com",
                        "registration_date": "2024-07-22"
                    }
                ]
            }
        }


class Session(BaseModel):
    """Session model"""
    
    id: str
    member_name: str
    time: str
    duration: int


class TrainerDashboardResponse(BaseModel):
    """Trainer dashboard response model"""
    
    trainer_name: str = Field(..., description="Trainer full name")
    assigned_members: int = Field(..., description="Number of assigned members")
    todays_sessions: int = Field(..., description="Sessions scheduled for today")
    upcoming_sessions: List[Session] = Field(..., description="Upcoming training sessions")
    attendance_summary: dict = Field(..., description="Attendance statistics")
    
    class Config:
        json_schema_extra = {
            "example": {
                "trainer_name": "Sarah Mitchell",
                "assigned_members": 24,
                "todays_sessions": 5,
                "upcoming_sessions": [
                    {
                        "id": "session_001",
                        "member_name": "John Smith",
                        "time": "08:00 AM",
                        "duration": 60
                    }
                ],
                "attendance_summary": {
                    "present": 18,
                    "absent": 2,
                    "cancelled": 1
                }
            }
        }


class MemberAttendance(BaseModel):
    """Member attendance record"""
    
    date: str
    duration: int
    workout_type: str


class MemberDashboardResponse(BaseModel):
    """Member dashboard response model"""
    
    member_name: str = Field(..., description="Member full name")
    membership_plan: str = Field(..., description="Current membership plan")
    expiry_date: str = Field(..., description="Membership expiry date")
    remaining_days: int = Field(..., description="Days remaining on membership")
    assigned_trainer: Optional[str] = Field(None, description="Assigned trainer name")
    attendance_count: int = Field(..., description="Total attendance count")
    recent_visits: List[MemberAttendance] = Field(..., description="Recent workout visits")
    
    class Config:
        json_schema_extra = {
            "example": {
                "member_name": "Robert Wilson",
                "membership_plan": "Premium",
                "expiry_date": "2024-12-31",
                "remaining_days": 163,
                "assigned_trainer": "Sarah Mitchell",
                "attendance_count": 32,
                "recent_visits": [
                    {
                        "date": "2024-07-22",
                        "duration": 60,
                        "workout_type": "Strength Training"
                    }
                ]
            }
        }
