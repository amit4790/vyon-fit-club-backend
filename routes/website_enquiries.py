"""Admin inbox for public website enquiries."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_admin_access
from models import WebsiteEnquiry
from schemas.website_enquiry import (
    WebsiteEnquiryCountResponse,
    WebsiteEnquiryListResponse,
    WebsiteEnquiryResponse,
    WebsiteEnquiryUpdateRequest,
)

router = APIRouter(
    prefix="/api/admin/enquiries",
    tags=["admin"],
    dependencies=[Depends(require_admin_access)],
)

ALLOWED_FILTERS = {"new", "contacted", "closed", "all"}


def _new_count(db: Session) -> int:
    return db.query(WebsiteEnquiry).filter(WebsiteEnquiry.status == "new").count()


@router.get("/count", response_model=WebsiteEnquiryCountResponse)
def get_website_enquiry_count(db: Session = Depends(get_db)) -> WebsiteEnquiryCountResponse:
    return WebsiteEnquiryCountResponse(new_count=_new_count(db))


@router.get("", response_model=WebsiteEnquiryListResponse)
def list_website_enquiries(
    status_filter: str = Query(default="new", alias="status"),
    db: Session = Depends(get_db),
) -> WebsiteEnquiryListResponse:
    normalized = status_filter.strip().lower()
    if normalized not in ALLOWED_FILTERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be new, contacted, closed, or all",
        )

    query = db.query(WebsiteEnquiry)
    if normalized != "all":
        query = query.filter(WebsiteEnquiry.status == normalized)

    rows = query.order_by(WebsiteEnquiry.created_at.desc()).limit(200).all()
    return WebsiteEnquiryListResponse(
        data=[WebsiteEnquiryResponse.model_validate(row) for row in rows],
        new_count=_new_count(db),
    )


@router.patch("/{enquiry_id}", response_model=WebsiteEnquiryResponse)
def update_website_enquiry(
    enquiry_id: int,
    payload: WebsiteEnquiryUpdateRequest,
    db: Session = Depends(get_db),
) -> WebsiteEnquiryResponse:
    row = db.get(WebsiteEnquiry, enquiry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found")

    if "status" in payload.model_fields_set and payload.status is not None:
        row.status = payload.status
    if "notes" in payload.model_fields_set:
        row.notes = (payload.notes or "").strip() or None

    db.commit()
    db.refresh(row)
    return WebsiteEnquiryResponse.model_validate(row)
