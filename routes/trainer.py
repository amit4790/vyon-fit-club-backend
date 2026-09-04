"""
Authenticated trainer mobile routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_trainer_access
from models import Member, User
from schemas.trainer_mobile import TrainerMeData, TrainerMeResponse
from services.auth_service import SessionPayload

router = APIRouter(prefix="/api/trainer", tags=["trainer"])


@router.get("/me", response_model=TrainerMeResponse)
def get_trainer_me(
    session: SessionPayload = Depends(require_trainer_access),
    db: Session = Depends(get_db),
) -> TrainerMeResponse:
    user = db.execute(select(User).where(User.id == int(session.user_id))).scalar_one_or_none()
    if not user or user.role != "TRAINER":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trainer not found")

    assigned_count = db.scalar(
        select(func.count()).select_from(Member).where(
            Member.trainer_id == user.id,
            Member.deleted_at.is_(None),
        )
    ) or 0

    return TrainerMeResponse(
        data=TrainerMeData(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            phone_number=user.phone_number,
            specialization=user.specialization,
            assigned_member_count=int(assigned_count),
            has_pin=bool(user.pin_hash),
            is_active=user.is_active,
        )
    )
