"""
Dashboard Service
Handles dashboard data retrieval for different user roles
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from database import SessionLocal
from repositories import DashboardRepository
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

    def __init__(self, db: Session):
        self.db = db
        self.repository = DashboardRepository(db)
    
    def _build_admin_dashboard(self) -> AdminDashboardResponse:
        """
        Get admin dashboard data from the database.
        """
        total_members = self.repository.get_total_members()
        active_members = self.repository.get_active_members()
        inactive_members = self.repository.get_inactive_members()
        expiring_memberships = self.repository.get_expiring_memberships(days=30)
        recent_members = self.repository.get_recent_registrations(limit=5)

        return AdminDashboardResponse(
            total_members=total_members,
            active_members=active_members,
            inactive_members=inactive_members,
            monthly_revenue=None,
            expiring_memberships=expiring_memberships,
            todays_checkins=None,
            recent_registrations=[
                RecentRegistration(
                    name=member.full_name,
                    email=member.email,
                    registration_date=member.joined_at.isoformat(),
                )
                for member in recent_members
            ]
        )

    @staticmethod
    def get_admin_dashboard(db: Session | None = None) -> AdminDashboardResponse:
        """Public admin dashboard API used by routes."""
        if db is not None:
            return DashboardService(db)._build_admin_dashboard()

        local_db = SessionLocal()
        try:
            return DashboardService(local_db)._build_admin_dashboard()
        finally:
            local_db.close()
    
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
