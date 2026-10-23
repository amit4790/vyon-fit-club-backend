"""
Authenticated member mobile routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_linked_member_id, require_member_access
from models import Member, User
from schemas.member_body_assessment import (
    MemberBodyAssessmentListResponse,
    MemberBodyAssessmentOperationResponse,
)
from schemas.member_mobile import MemberMeData, MemberMeResponse
from services.auth_service import SessionPayload
from services.body_assessment_service import BodyAssessmentService

router = APIRouter(prefix="/api/member", tags=["member"])


@router.get("/me", response_model=MemberMeResponse)
def get_member_me(
    session: SessionPayload = Depends(require_member_access),
    db: Session = Depends(get_db),
) -> MemberMeResponse:
    user = db.execute(select(User).where(User.id == int(session.user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    member = db.execute(
        select(Member).where(Member.user_id == user.id, Member.deleted_at.is_(None))
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member profile not linked")

    return MemberMeResponse(
        data=MemberMeData(
            user_id=user.id,
            member_id=member.id,
            full_name=member.full_name,
            mobile_number=member.mobile_number,
            email=member.email or user.email,
            status=member.status,
            joined_at=member.joined_at,
            trainer_id=member.trainer_id,
            has_pin=bool(user.pin_hash),
        )
    )


@router.get("/body-assessments", response_model=MemberBodyAssessmentListResponse)
def list_my_body_assessments(
    member_id: int = Depends(require_linked_member_id),
    db: Session = Depends(get_db),
) -> MemberBodyAssessmentListResponse:
    data = BodyAssessmentService(db).list_member_assessments(member_id)
    return MemberBodyAssessmentListResponse(message="Your body assessments", data=data)


@router.get("/body-assessments/{assessment_id}", response_model=MemberBodyAssessmentOperationResponse)
def get_my_body_assessment(
    assessment_id: int,
    member_id: int = Depends(require_linked_member_id),
    db: Session = Depends(get_db),
) -> MemberBodyAssessmentOperationResponse:
    data = BodyAssessmentService(db).get_member_assessment(member_id, assessment_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return MemberBodyAssessmentOperationResponse(message="Assessment detail", data=data)
