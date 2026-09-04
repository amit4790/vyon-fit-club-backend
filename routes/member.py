"""
Authenticated member mobile routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_member_access
from models import Member, User
from schemas.member_mobile import MemberMeData, MemberMeResponse
from services.auth_service import SessionPayload

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
