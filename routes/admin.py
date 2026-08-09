"""
Admin routes for VYON FIT CLUB.
Handles admin dashboard and management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_session, require_admin_access, require_super_admin
from models import User
from schemas.profile import AdminProfileResponse
from schemas.admin_user import AdminCreateRequest, AdminUserOperationResponse, AdminUserResponse
from schemas.device import (
    DeviceAttendanceRecordResponse,
    DeviceAttendanceResponse,
    DeviceStatusData,
    DeviceStatusResponse,
    DeviceUserResponse,
    DeviceUsersResponse,
    MemberDeviceMappingData,
    MemberDeviceMappingRequest,
    MemberDeviceMappingResponse,
    MemberDeviceUnlinkRequest,
)
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
from schemas.report import ReportsSummaryResponse, UpdateTargetRevenueRequest, UpdateTargetRevenueResponse
from schemas.subscription import (
    AssignSubscriptionRequest,
    ChangeSubscriptionPlanRequest,
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
from schemas.trainer_detail import (
    TrainerAssignedMember,
    TrainerDetailOperationResponse,
    TrainerDetailResponse,
)
from services.member_service import (
    DuplicateDeviceIdentifierError,
    DuplicateMobileError,
    InvalidDeviceMappingError,
    MemberNotFoundError,
    MemberService,
)
from services.admin_user_service import AdminUserService, DuplicateAdminEmailError, DuplicateAdminPhoneError
from services.device_service import (
    DeviceConnectionError,
    DeviceDependencyError,
    DeviceNotFoundError,
    DeviceOperationError,
    DeviceService,
    DeviceValidationError,
)
from services.report_service import ReportService
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
    SubscriptionNotFoundError as SubscriptionLookupError,
    SubscriptionService,
)
from services.trainer_service import (
    DuplicateTrainerEmailError,
    DuplicateTrainerPhoneError,
    TrainerNotFoundError,
    TrainerService,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_access)])


def _raise_device_http_exception(exc: Exception) -> None:
    if isinstance(exc, DeviceValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, DeviceNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _to_member_response(member) -> MemberResponse:
    return MemberResponse(
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
        device_user_id=member.device_user_id,
        device_uid=member.device_uid,
        device_card=member.device_card,
        device_sync_status=member.device_sync_status,
    )


def _to_member_device_mapping_response(member, message: str) -> MemberDeviceMappingResponse:
    return MemberDeviceMappingResponse(
        message=message,
        data=MemberDeviceMappingData(
            member_id=member.id,
            device_user_id=member.device_user_id,
            device_uid=member.device_uid,
            device_card=member.device_card,
            device_sync_status=member.device_sync_status,
            last_device_sync_at=member.last_device_sync_at,
        ),
    )


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


@router.get("/profile", response_model=AdminProfileResponse)
def get_admin_profile(
    session=Depends(get_current_session),
    db: Session = Depends(get_db),
) -> AdminProfileResponse:
    user = db.execute(select(User).where(User.id == int(session.user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return AdminProfileResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone_number=user.phone_number,
        role=user.role,
        is_active=user.is_active,
        joined_date=user.created_at.isoformat(),
    )


@router.get("/device/status", response_model=DeviceStatusResponse)
def get_device_status() -> DeviceStatusResponse:
    """Return live connection and device metadata for the configured ZKTeco device."""
    service = DeviceService()

    try:
        status_payload = service.get_status()
    finally:
        try:
            service.disconnect()
        except DeviceOperationError as exc:
            _raise_device_http_exception(exc)

    return DeviceStatusResponse(
        message="ZKTeco device status fetched successfully" if status_payload.connected else "ZKTeco device unavailable",
        data=DeviceStatusData(
            connected=status_payload.connected,
            device_model=status_payload.device_model,
            serial_number=status_payload.serial_number,
            firmware_version=status_payload.firmware_version,
            platform=status_payload.platform,
            face_algorithm_version=status_payload.face_algorithm_version,
            current_device_time=status_payload.current_device_time,
            user_count=status_payload.user_count,
            connection_error=status_payload.connection_error,
        ),
    )


@router.get("/device/users", response_model=DeviceUsersResponse)
def get_device_users() -> DeviceUsersResponse:
    """Return the current user list from the configured ZKTeco device."""
    service = DeviceService()

    try:
        users = service.get_users()
    except (DeviceDependencyError, DeviceConnectionError, DeviceOperationError) as exc:
        _raise_device_http_exception(exc)
    finally:
        try:
            service.disconnect()
        except DeviceOperationError as exc:
            _raise_device_http_exception(exc)

    return DeviceUsersResponse(
        message="ZKTeco device users fetched successfully",
        data=[
            DeviceUserResponse(
                uid=user.uid,
                user_id=user.user_id,
                name=user.name,
                privilege=user.privilege,
                card=user.card,
            )
            for user in users
        ],
    )


@router.get("/device/attendance", response_model=DeviceAttendanceResponse)
def get_device_attendance(
    limit: int | None = Query(None, ge=1, le=1000, description="Optional maximum records from latest attendance logs"),
) -> DeviceAttendanceResponse:
    """Return attendance records from the configured ZKTeco device."""
    service = DeviceService()

    try:
        rows = service.get_attendance(limit=limit)
    except (DeviceDependencyError, DeviceConnectionError, DeviceOperationError, DeviceValidationError) as exc:
        _raise_device_http_exception(exc)
    finally:
        try:
            service.disconnect()
        except DeviceOperationError as exc:
            _raise_device_http_exception(exc)

    return DeviceAttendanceResponse(
        message="ZKTeco attendance fetched successfully",
        data=[
            DeviceAttendanceRecordResponse(
                uid=row.uid,
                user_id=row.user_id,
                timestamp=row.timestamp,
                status=row.status,
                punch=row.punch,
            )
            for row in rows
        ],
    )


@router.put("/members/{member_id}/device-mapping", response_model=MemberDeviceMappingResponse)
def upsert_member_device_mapping(
    member_id: int,
    payload: MemberDeviceMappingRequest,
    db: Session = Depends(get_db),
) -> MemberDeviceMappingResponse:
    """Link a member profile to device identifiers, optionally pushing to the physical device."""
    member_service = MemberService(db)

    try:
        member = member_service.get_member_or_raise(member_id)
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    expected_device_user_id = str(member.id)
    normalized_device_user_id = payload.device_user_id.strip() if payload.device_user_id else expected_device_user_id
    mapping_uid = payload.device_uid
    mapping_card = payload.device_card

    if normalized_device_user_id != expected_device_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device user id must match member id for this implementation",
        )

    sync_status = "mapped"
    update_sync_timestamp = False

    if payload.push_to_device:
        service = DeviceService()
        try:
            created_user = service.create_user(
                uid=mapping_uid,
                user_id=expected_device_user_id,
                name=member.full_name,
                privilege=0,
                password="",
                card=0,
            )

            if mapping_uid is None and created_user.uid:
                mapping_uid = created_user.uid
            normalized_device_user_id = expected_device_user_id

            sync_status = "synced"
            update_sync_timestamp = True
        except (DeviceDependencyError, DeviceConnectionError, DeviceOperationError, DeviceValidationError) as exc:
            _raise_device_http_exception(exc)
        finally:
            try:
                service.disconnect()
            except DeviceOperationError as exc:
                _raise_device_http_exception(exc)

    try:
        updated_member = member_service.upsert_device_mapping(
            member_id=member_id,
            device_user_id=normalized_device_user_id,
            device_uid=mapping_uid,
            device_card=mapping_card,
            sync_status=sync_status,
            update_sync_timestamp=update_sync_timestamp,
        )
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidDeviceMappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DuplicateDeviceIdentifierError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _to_member_device_mapping_response(updated_member, "Member-device mapping updated successfully")


@router.delete("/members/{member_id}/device-mapping", response_model=MemberDeviceMappingResponse)
def clear_member_device_mapping(
    member_id: int,
    payload: MemberDeviceUnlinkRequest,
    db: Session = Depends(get_db),
) -> MemberDeviceMappingResponse:
    """Unlink a member profile from device identifiers, optionally deleting the user from device."""
    member_service = MemberService(db)

    try:
        member = member_service.get_member_or_raise(member_id)
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if payload.delete_from_device:
        if member.device_uid is None and not member.device_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Member has no device identifiers to delete from device",
            )

        service = DeviceService()
        try:
            service.delete_user(uid=member.device_uid, user_id=member.device_user_id)
        except (DeviceDependencyError, DeviceConnectionError, DeviceOperationError, DeviceValidationError) as exc:
            _raise_device_http_exception(exc)
        finally:
            try:
                service.disconnect()
            except DeviceOperationError as exc:
                _raise_device_http_exception(exc)

    updated_member = member_service.clear_device_mapping(
        member_id=member_id,
        sync_status="unlinked",
    )
    return _to_member_device_mapping_response(updated_member, "Member-device mapping cleared successfully")


@router.get("/members")
def get_members(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=500, description="Items per page"),
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
        data=[_to_member_response(member) for member in members],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


@router.get("/members/{member_id}", response_model=MemberOperationResponse)
def get_member_by_id(member_id: int, db: Session = Depends(get_db)) -> MemberOperationResponse:
    service = MemberService(db)
    member = service.repository.get_member_by_id(member_id)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    return MemberOperationResponse(
        message="Member details",
        data=_to_member_response(member),
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
        data=_to_member_response(member),
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
        data=_to_member_response(member),
    )


@router.delete("/members/{member_id}", response_model=MemberDeleteResponse)
def delete_member(member_id: int, db: Session = Depends(get_db)) -> MemberDeleteResponse:
    """
    Soft-delete a member and permanently remove associated memberships/invoices.
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
            duration_value=payload.duration_value,
            duration_unit=payload.duration_unit,
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


@router.patch(
    "/subscriptions/{subscription_id}/plan",
    response_model=SubscriptionOperationResponse,
)
def change_subscription_plan(
    subscription_id: int,
    payload: ChangeSubscriptionPlanRequest,
    db: Session = Depends(get_db),
) -> SubscriptionOperationResponse:
    """Change the membership plan on an existing subscription."""
    service = SubscriptionService(db)

    try:
        subscription = service.change_subscription_plan(
            subscription_id=subscription_id,
            plan_id=payload.plan_id,
            start_date=payload.start_date,
            duration_value=payload.duration_value,
            duration_unit=payload.duration_unit,
        )
    except SubscriptionLookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SubscriptionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return SubscriptionOperationResponse(
        message="Subscription plan updated successfully",
        data=subscription,
        notifications=[],
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


@router.get("/subscriptions/expiring", response_model=ExpiringSubscriptionsResponse)
def get_expiring_subscriptions(
    days: int = Query(7, ge=1, le=90, description="Lookahead window in days"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=500, description="Items per page"),
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


@router.get("/subscriptions/{subscription_id:int}", response_model=SubscriptionOperationResponse)
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


@router.get("/reports/summary", response_model=ReportsSummaryResponse)
def get_reports_summary(db: Session = Depends(get_db)) -> ReportsSummaryResponse:
    """Get live summary metrics for reports module."""
    summary = ReportService(db).get_summary()
    return ReportsSummaryResponse(message="Reports summary", data=summary)


@router.patch("/reports/target-revenue", response_model=UpdateTargetRevenueResponse)
def update_target_revenue(
    payload: UpdateTargetRevenueRequest,
    db: Session = Depends(get_db),
) -> UpdateTargetRevenueResponse:
    """Update editable target revenue used by Reports."""
    summary = ReportService(db).update_target_revenue(payload.target_revenue)
    return UpdateTargetRevenueResponse(message="Target revenue updated", data=summary)


@router.get("/invoices", response_model=InvoiceListResponse)
def get_invoices(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=500, description="Items per page"),
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
                phone_number=trainer.phone_number,
                specialization=trainer.specialization,
                role=trainer.role,
                is_active=trainer.is_active,
            )
            for trainer in trainers
        ],
    )


@router.get("/trainers/{trainer_id}", response_model=TrainerDetailOperationResponse)
def get_trainer_by_id(trainer_id: int, db: Session = Depends(get_db)) -> TrainerDetailOperationResponse:
    service = TrainerService(db)
    trainer = service.repository.get_trainer_by_id(trainer_id)
    if not trainer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trainer not found")

    assigned_members = service.get_trainer_assigned_members(trainer_id)
    return TrainerDetailOperationResponse(
        message="Trainer details",
        data=TrainerDetailResponse(
            id=trainer.id,
            full_name=trainer.full_name,
            email=trainer.email,
            phone_number=trainer.phone_number,
            specialization=trainer.specialization,
            role=trainer.role,
            is_active=trainer.is_active,
            assigned_members=[
                TrainerAssignedMember(
                    id=item.id,
                    full_name=item.full_name,
                    mobile_number=item.mobile_number,
                )
                for item in assigned_members
            ],
        ),
    )


@router.post("/users/admins", response_model=AdminUserOperationResponse, status_code=status.HTTP_201_CREATED)
def create_admin_user(
    payload: AdminCreateRequest,
    _session=Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> AdminUserOperationResponse:
    """Create a new ADMIN user (SUPER_ADMIN only)."""
    service = AdminUserService(db)

    try:
        admin_user = service.create_admin_user(payload)
    except DuplicateAdminEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DuplicateAdminPhoneError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AdminUserOperationResponse(
        message="Admin created successfully",
        data=AdminUserResponse(
            id=admin_user.id,
            full_name=admin_user.full_name,
            email=admin_user.email,
            phone_number=admin_user.phone_number,
            role=admin_user.role,
            is_active=admin_user.is_active,
        ),
    )


@router.post("/trainers", response_model=TrainerOperationResponse, status_code=status.HTTP_201_CREATED)
def create_trainer(payload: TrainerCreateRequest, db: Session = Depends(get_db)) -> TrainerOperationResponse:
    """Create a new trainer."""
    service = TrainerService(db)

    try:
        trainer = service.create_trainer(payload)
    except DuplicateTrainerEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DuplicateTrainerPhoneError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return TrainerOperationResponse(
        message="Trainer created successfully",
        data=TrainerResponse(
            id=trainer.id,
            full_name=trainer.full_name,
            email=trainer.email,
            phone_number=trainer.phone_number,
            specialization=trainer.specialization,
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
    except DuplicateTrainerPhoneError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return TrainerOperationResponse(
        message="Trainer updated successfully",
        data=TrainerResponse(
            id=trainer.id,
            full_name=trainer.full_name,
            email=trainer.email,
            phone_number=trainer.phone_number,
            specialization=trainer.specialization,
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
