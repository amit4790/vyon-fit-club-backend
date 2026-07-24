"""
Admin routes for VYON FIT CLUB.
Handles admin dashboard and management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.member import (
    MemberCreateRequest,
    MemberDeleteResponse,
    MemberListResponse,
    MemberOperationResponse,
    MemberResponse,
    MemberUpdateRequest,
    PaginationMeta,
)
from services.member_service import DuplicateMobileError, MemberNotFoundError, MemberService

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
def get_members(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search by name or mobile number"),
    db: Session = Depends(get_db),
) -> MemberListResponse:
    """
    Get paginated list of members.
    """
    service = MemberService(db)
    members, total_items = service.list_members(page=page, page_size=page_size, search=search)

    total_pages = total_items // page_size + (1 if total_items % page_size else 0)
    if total_items == 0:
        total_pages = 0

    return MemberListResponse(
        message="Members list",
        data=[
            MemberResponse(
                id=member.id,
                full_name=member.full_name,
                mobile_number=member.mobile_number,
                joining_date=member.joined_at,
                status=member.status,
                email=member.email,
                date_of_birth=member.date_of_birth,
                gender=member.gender,
                address=member.address,
                emergency_contact=member.emergency_contact,
                emergency_phone=member.emergency_phone,
                notes=member.notes,
            )
            for member in members
        ],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


@router.post("/members", response_model=MemberOperationResponse, status_code=status.HTTP_201_CREATED)
def create_member(payload: MemberCreateRequest, db: Session = Depends(get_db)) -> MemberOperationResponse:
    """
    Create a new member.
    """
    service = MemberService(db)

    try:
        member = service.create_member(payload)
    except DuplicateMobileError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return MemberOperationResponse(
        message="Member created successfully",
        data=MemberResponse(
            id=member.id,
            full_name=member.full_name,
            mobile_number=member.mobile_number,
            joining_date=member.joined_at,
            status=member.status,
            email=member.email,
            date_of_birth=member.date_of_birth,
            gender=member.gender,
            address=member.address,
            emergency_contact=member.emergency_contact,
            emergency_phone=member.emergency_phone,
            notes=member.notes,
        ),
    )


@router.put("/members/{member_id}", response_model=MemberOperationResponse)
def update_member(
    member_id: int,
    payload: MemberUpdateRequest,
    db: Session = Depends(get_db),
) -> MemberOperationResponse:
    """
    Update an existing member.
    """
    service = MemberService(db)

    try:
        member = service.update_member(member_id, payload)
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateMobileError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return MemberOperationResponse(
        message="Member updated successfully",
        data=MemberResponse(
            id=member.id,
            full_name=member.full_name,
            mobile_number=member.mobile_number,
            joining_date=member.joined_at,
            status=member.status,
            email=member.email,
            date_of_birth=member.date_of_birth,
            gender=member.gender,
            address=member.address,
            emergency_contact=member.emergency_contact,
            emergency_phone=member.emergency_phone,
            notes=member.notes,
        ),
    )


@router.delete("/members/{member_id}", response_model=MemberDeleteResponse)
def delete_member(member_id: int, db: Session = Depends(get_db)) -> MemberDeleteResponse:
    """
    Soft-delete a member by marking the record inactive.
    """
    service = MemberService(db)

    try:
        service.delete_member(member_id)
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return MemberDeleteResponse(message="Member deleted successfully")


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
