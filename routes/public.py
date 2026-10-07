"""Unauthenticated public marketing endpoints."""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from models import WebsiteEnquiry
from schemas.website_enquiry import (
    WebsiteEnquiryCreateRequest,
    WebsiteEnquiryCreateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["Public"])


@router.post(
    "/enquiries",
    response_model=WebsiteEnquiryCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_website_enquiry(
    payload: WebsiteEnquiryCreateRequest,
    db: Session = Depends(get_db),
) -> WebsiteEnquiryCreateResponse:
    """Capture a membership or personal-training lead from the marketing site."""
    row = WebsiteEnquiry(
        full_name=payload.full_name.strip(),
        phone_number=payload.phone_number,
        email=(payload.email or "").strip() or None,
        intent=payload.intent.strip().lower(),
        plan_interest=(payload.plan_interest or "").strip() or None,
        status="new",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    logger.info(
        "Website enquiry received",
        extra={
            "enquiry_id": row.id,
            "intent": row.intent,
            "plan_interest": row.plan_interest,
        },
    )

    return WebsiteEnquiryCreateResponse(
        message="Thank you. Our team will contact you shortly.",
        enquiry_id=row.id,
    )
