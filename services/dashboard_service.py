"""
Dashboard Service
Handles dashboard data retrieval for different user roles
"""

from datetime import datetime, timedelta
from schemas.dashboard import (
    AdminDashboardResponse,
    TrainerDashboardResponse,
    MemberDashboardResponse,
    RecentRegistration,
    Session,
    MemberAttendance,
)


class DashboardService:
    """Service for dashboard operations"""
    
    @staticmethod
    def get_admin_dashboard() -> AdminDashboardResponse:
        """
        Get admin dashboard data with mock statistics
        """
        return AdminDashboardResponse(
            total_members=250,
            active_members=185,
            monthly_revenue=15750.50,
            expiring_memberships=12,
            todays_checkins=42,
            recent_registrations=[
                RecentRegistration(
                    name="Alice Johnson",
                    email="alice.johnson@example.com",
                    registration_date="2024-07-22"
                ),
                RecentRegistration(
                    name="Michael Chen",
                    email="michael.chen@example.com",
                    registration_date="2024-07-21"
                ),
                RecentRegistration(
                    name="Emma Davis",
                    email="emma.davis@example.com",
                    registration_date="2024-07-20"
                ),
            ]
        )
    
    @staticmethod
    def get_trainer_dashboard(trainer_id: str = "trainer_001") -> TrainerDashboardResponse:
        """
        Get trainer dashboard data with mock statistics
        """
        today = datetime.now()
        
        return TrainerDashboardResponse(
            trainer_name="Sarah Mitchell",
            assigned_members=24,
            todays_sessions=5,
            upcoming_sessions=[
                Session(
                    id="session_001",
                    member_name="John Smith",
                    time="08:00 AM",
                    duration=60
                ),
                Session(
                    id="session_002",
                    member_name="Lisa Anderson",
                    time="10:00 AM",
                    duration=45
                ),
                Session(
                    id="session_003",
                    member_name="David Kumar",
                    time="02:00 PM",
                    duration=60
                ),
                Session(
                    id="session_004",
                    member_name="Jennifer Lee",
                    time="04:00 PM",
                    duration=50
                ),
                Session(
                    id="session_005",
                    member_name="Marcus Brown",
                    time="06:00 PM",
                    duration=60
                ),
            ],
            attendance_summary={
                "present": 18,
                "absent": 2,
                "cancelled": 1,
                "completed_this_month": 89
            }
        )
    
    @staticmethod
    def get_member_dashboard(member_id: str = "member_001") -> MemberDashboardResponse:
        """
        Get member dashboard data with mock statistics
        """
        today = datetime.now()
        expiry_date = today + timedelta(days=163)
        
        return MemberDashboardResponse(
            member_name="Robert Wilson",
            membership_plan="Premium",
            expiry_date=expiry_date.strftime("%Y-%m-%d"),
            remaining_days=163,
            assigned_trainer="Sarah Mitchell",
            attendance_count=32,
            recent_visits=[
                MemberAttendance(
                    date="2024-07-22",
                    duration=60,
                    workout_type="Strength Training"
                ),
                MemberAttendance(
                    date="2024-07-21",
                    duration=45,
                    workout_type="Cardio"
                ),
                MemberAttendance(
                    date="2024-07-20",
                    duration=50,
                    workout_type="Functional Training"
                ),
                MemberAttendance(
                    date="2024-07-19",
                    duration=60,
                    workout_type="Strength Training"
                ),
                MemberAttendance(
                    date="2024-07-18",
                    duration=30,
                    workout_type="Yoga"
                ),
            ]
        )
