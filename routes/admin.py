"""
Admin routes for VYON FIT CLUB.
Handles admin dashboard and management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
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
from schemas.invoice import (
    CapturePaymentRequest,
    CapturePaymentResponse,
    InvoiceListResponse,
    InvoiceOperationResponse,
    InvoiceStatusUpdateRequest,
)
from schemas.subscription import (
    AssignSubscriptionRequest,
    ExpiringSubscriptionsResponse,
    MemberSubscriptionsResponse,
    PlanCatalogResponse,
    PlanOptionOperationResponse,
    PlanPriceUpdateRequest,
    SubscriptionOperationResponse,
)
from schemas.trainer import (
    TrainerCreateRequest,
    TrainerDeleteResponse,
    TrainerListResponse,
    TrainerOperationResponse,
    TrainerResponse,
    TrainerUpdateRequest,
)
from services.member_service import DuplicateMobileError, MemberNotFoundError, MemberService
from services.invoice_service import (
    InvalidPaymentAmountError,
    InvalidInvoiceStatusTransitionError,
    InvoiceNotFoundError,
    InvoiceService,
    SubscriptionNotFoundError,
)
from services.subscription_service import (
    MemberNotFoundError as SubscriptionMemberNotFoundError,
    PlanNotFoundError,
    SubscriptionConflictError,
    SubscriptionService,
)
from services.trainer_service import (
    DuplicateTrainerEmailError,
    TrainerNotFoundError,
    TrainerService,
)

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


@router.get("/plans", response_model=PlanCatalogResponse)
def get_plan_catalog(db: Session = Depends(get_db)) -> PlanCatalogResponse:
    """Get active membership plan catalog."""
    service = SubscriptionService(db)
    service.sync_expired_subscriptions()
    catalog = service.get_plan_catalog()
    return PlanCatalogResponse(message="Plan catalog", data=catalog)


@router.patch("/plans/{plan_id}", response_model=PlanOptionOperationResponse)
def update_plan_price(
    plan_id: int,
    payload: PlanPriceUpdateRequest,
    db: Session = Depends(get_db),
) -> PlanOptionOperationResponse:
    """Update membership plan pricing."""
    service = SubscriptionService(db)

    try:
        option = service.update_plan_pricing(
            plan_id=plan_id,
            base_price=payload.base_price,
            tax_percent=payload.tax_percent,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return PlanOptionOperationResponse(message="Plan pricing updated successfully", data=option)


@router.post(
    "/members/{member_id}/subscriptions",
    response_model=SubscriptionOperationResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_member_subscription(
    member_id: int,
    payload: AssignSubscriptionRequest,
    db: Session = Depends(get_db),
) -> SubscriptionOperationResponse:
    """Assign a membership subscription to a member."""
    service = SubscriptionService(db)

    try:
        subscription, notifications = service.assign_subscription(
            member_id=member_id,
            plan_id=payload.plan_id,
            start_date=payload.start_date,
        )
    except SubscriptionMemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SubscriptionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return SubscriptionOperationResponse(
        message="Subscription assigned successfully",
        data=subscription,
        notifications=notifications,
    )


@router.get("/members/{member_id}/subscriptions", response_model=MemberSubscriptionsResponse)
def get_member_subscriptions(member_id: int, db: Session = Depends(get_db)) -> MemberSubscriptionsResponse:
    """Get all subscriptions for a specific member."""
    service = SubscriptionService(db)

    try:
        subscriptions = service.get_member_subscriptions(member_id)
    except SubscriptionMemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return MemberSubscriptionsResponse(message="Member subscriptions", data=subscriptions)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionOperationResponse)
def get_subscription_by_id(subscription_id: int, db: Session = Depends(get_db)) -> SubscriptionOperationResponse:
    """Get a subscription record by id."""
    service = SubscriptionService(db)

    subscription = service.repo.get_subscription_by_id(subscription_id)
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    return SubscriptionOperationResponse(
        message="Subscription details",
        data=service._to_subscription_response(subscription),
        notifications=[],
    )


@router.post(
    "/subscriptions/{subscription_id}/payment",
    response_model=CapturePaymentResponse,
)
def capture_subscription_payment(
    subscription_id: int,
    payload: CapturePaymentRequest,
    db: Session = Depends(get_db),
) -> CapturePaymentResponse:
    """Capture payment details for a subscription and generate invoice PDF."""
    service = InvoiceService(db)

    try:
        invoice = service.capture_payment_for_subscription(subscription_id=subscription_id, payload=payload)
    except SubscriptionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidPaymentAmountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return CapturePaymentResponse(message="Payment saved successfully", data=invoice)


@router.get("/subscriptions/expiring", response_model=ExpiringSubscriptionsResponse)
def get_expiring_subscriptions(
    days: int = Query(7, ge=1, le=90, description="Lookahead window in days"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> ExpiringSubscriptionsResponse:
    """Get active subscriptions expiring within the configured window."""
    service = SubscriptionService(db)
    service.sync_expired_subscriptions()
    result = service.get_expiring_subscriptions(days=days, page=page, page_size=page_size)

    total_pages = result.total_items // page_size + (1 if result.total_items % page_size else 0)
    if result.total_items == 0:
        total_pages = 0

    return ExpiringSubscriptionsResponse(
        message="Expiring subscriptions",
        data=result.items,
        pagination={
            "page": page,
            "page_size": page_size,
            "total_items": result.total_items,
            "total_pages": total_pages,
            "days": days,
        },
    )


@router.get("/invoices", response_model=InvoiceListResponse)
def get_invoices(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    status_filter: str | None = Query(None, alias="status", description="Invoice status filter"),
    member_id: int | None = Query(None, ge=1, description="Filter by member id"),
    db: Session = Depends(get_db),
) -> InvoiceListResponse:
    """Get paginated invoices with optional filters."""
    service = InvoiceService(db)
    invoices, total_items = service.list_invoices(
        page=page,
        page_size=page_size,
        status=status_filter,
        member_id=member_id,
    )

    total_pages = total_items // page_size + (1 if total_items % page_size else 0)
    if total_items == 0:
        total_pages = 0

    return InvoiceListResponse(
        message="Invoices list",
        data=invoices,
        pagination={
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceOperationResponse)
def get_invoice_by_id(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOperationResponse:
    """Get invoice details by id."""
    service = InvoiceService(db)

    try:
        invoice = service.get_invoice(invoice_id)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return InvoiceOperationResponse(message="Invoice details", data=invoice, notifications=[])


@router.get("/invoices/{invoice_id}/download")
def download_invoice(invoice_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Download generated invoice PDF."""
    service = InvoiceService(db)

    try:
        pdf_path = service.get_invoice_pdf_path(invoice_id)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"invoice-{invoice_id}.pdf",
    )


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceOperationResponse)
def update_invoice_status(
    invoice_id: int,
    payload: InvoiceStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> InvoiceOperationResponse:
    """Update invoice payment status."""
    service = InvoiceService(db)

    try:
        invoice, notifications = service.update_invoice_status(invoice_id, payload.status)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidInvoiceStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return InvoiceOperationResponse(
        message="Invoice status updated successfully",
        data=invoice,
        notifications=service.delivery_results_to_dict(notifications),
    )


@router.post("/invoices/{invoice_id}/resend", response_model=InvoiceOperationResponse)
def resend_invoice(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOperationResponse:
    """Resend invoice notifications over dummy email and SMS channels."""
    service = InvoiceService(db)

    try:
        invoice, notifications = service.resend_invoice(invoice_id)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return InvoiceOperationResponse(
        message="Invoice resent successfully",
        data=invoice,
        notifications=service.delivery_results_to_dict(notifications),
    )


@router.get("/trainers", response_model=TrainerListResponse)
def get_trainers(db: Session = Depends(get_db)) -> TrainerListResponse:
    """Get list of all trainers."""
    service = TrainerService(db)
    trainers = service.list_trainers()

    return TrainerListResponse(
        message="Trainers list",
        data=[
            TrainerResponse(
                id=trainer.id,
                full_name=trainer.full_name,
                email=trainer.email,
                role=trainer.role,
                is_active=trainer.is_active,
            )
            for trainer in trainers
        ],
    )


@router.post("/trainers", response_model=TrainerOperationResponse, status_code=status.HTTP_201_CREATED)
def create_trainer(payload: TrainerCreateRequest, db: Session = Depends(get_db)) -> TrainerOperationResponse:
    """Create a new trainer."""
    service = TrainerService(db)

    try:
        trainer = service.create_trainer(payload)
    except DuplicateTrainerEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return TrainerOperationResponse(
        message="Trainer created successfully",
        data=TrainerResponse(
            id=trainer.id,
            full_name=trainer.full_name,
            email=trainer.email,
            role=trainer.role,
            is_active=trainer.is_active,
        ),
    )


@router.put("/trainers/{trainer_id}", response_model=TrainerOperationResponse)
def update_trainer(
    trainer_id: int,
    payload: TrainerUpdateRequest,
    db: Session = Depends(get_db),
) -> TrainerOperationResponse:
    """Update trainer details."""
    service = TrainerService(db)

    try:
        trainer = service.update_trainer(trainer_id, payload)
    except TrainerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateTrainerEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return TrainerOperationResponse(
        message="Trainer updated successfully",
        data=TrainerResponse(
            id=trainer.id,
            full_name=trainer.full_name,
            email=trainer.email,
            role=trainer.role,
            is_active=trainer.is_active,
        ),
    )


@router.delete("/trainers/{trainer_id}", response_model=TrainerDeleteResponse)
def delete_trainer(trainer_id: int, db: Session = Depends(get_db)) -> TrainerDeleteResponse:
    """Soft-delete trainer by setting inactive state."""
    service = TrainerService(db)

    try:
        service.delete_trainer(trainer_id)
    except TrainerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return TrainerDeleteResponse(message="Trainer deleted successfully")


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
