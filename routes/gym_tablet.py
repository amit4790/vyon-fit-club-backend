"""Gym tablet routes — members and body assessments only."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_body_assessment_access, require_gym_tablet_access
from repositories.trainer_repository import TrainerRepository
from routes.admin import _to_member_response
from schemas.body_assessment import (
    BodyAnalysisOverviewResponse,
    BodyAssessmentCreateRequest,
    BodyAssessmentListResponse,
    BodyAssessmentOperationResponse,
    BodyProgressResponse,
    GymTrainerListResponse,
    GymTrainerOption,
)
from schemas.member import MemberListResponse, MemberOperationResponse, PaginationMeta
from services.auth_service import SessionPayload
from services.body_assessment_service import BodyAssessmentService, DuplicateAssessmentDateError
from services.member_export_service import MemberExportService
from services.member_service import MemberNotFoundError, MemberService

router = APIRouter(prefix="/api/gym", tags=["gym-tablet"])


@router.get("/trainers", response_model=GymTrainerListResponse)
def list_gym_trainers(
    db: Session = Depends(get_db),
    _session: SessionPayload = Depends(require_body_assessment_access),
) -> GymTrainerListResponse:
    trainers = [t for t in TrainerRepository(db).list_trainers() if t.is_active]
    return GymTrainerListResponse(
        message="Active trainers",
        data=[GymTrainerOption(id=t.id, full_name=t.full_name) for t in trainers],
    )


@router.get("/members", response_model=MemberListResponse)
def list_gym_members(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    _session: SessionPayload = Depends(require_gym_tablet_access),
) -> MemberListResponse:
    service = MemberService(db)
    try:
        members, total_items, summaries = service.list_members(
            page=page,
            page_size=page_size,
            search=search,
            membership_status=None,
            sort=None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    total_pages = total_items // page_size + (1 if total_items % page_size else 0)
    if total_items == 0:
        total_pages = 0

    return MemberListResponse(
        message="Members list",
        data=[_to_member_response(member, summaries.get(member.id)) for member in members],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


@router.get("/members/{member_id}", response_model=MemberOperationResponse)
def get_gym_member(
    member_id: int,
    db: Session = Depends(get_db),
    _session: SessionPayload = Depends(require_gym_tablet_access),
) -> MemberOperationResponse:
    service = MemberService(db)
    try:
        member = service.get_member_or_raise(member_id)
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    summaries = MemberExportService(db).build_summaries_for_member_ids([member_id])
    return MemberOperationResponse(
        message="Member details",
        data=_to_member_response(member, summaries.get(member_id)),
    )


@router.get("/members/{member_id}/body-analysis/overview", response_model=BodyAnalysisOverviewResponse)
def get_body_analysis_overview(
    member_id: int,
    db: Session = Depends(get_db),
    _session: SessionPayload = Depends(require_body_assessment_access),
) -> BodyAnalysisOverviewResponse:
    try:
        MemberService(db).get_member_or_raise(member_id)
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return BodyAssessmentService(db).get_overview(member_id)


@router.get("/members/{member_id}/body-assessments", response_model=BodyAssessmentListResponse)
def list_body_assessments(
    member_id: int,
    db: Session = Depends(get_db),
    _session: SessionPayload = Depends(require_body_assessment_access),
) -> BodyAssessmentListResponse:
    try:
        MemberService(db).get_member_or_raise(member_id)
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    data = BodyAssessmentService(db).list_assessments(member_id)
    return BodyAssessmentListResponse(message="Assessment history", data=data)


@router.get("/members/{member_id}/body-assessments/progress", response_model=BodyProgressResponse)
def get_body_progress(
    member_id: int,
    months: int = Query(3, ge=1, le=24),
    db: Session = Depends(get_db),
    _session: SessionPayload = Depends(require_body_assessment_access),
) -> BodyProgressResponse:
    try:
        MemberService(db).get_member_or_raise(member_id)
    except MemberNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return BodyAssessmentService(db).get_progress(member_id, months=months)


@router.post(
    "/members/{member_id}/body-assessments",
    response_model=BodyAssessmentOperationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_body_assessment(
    member_id: int,
    payload: BodyAssessmentCreateRequest,
    db: Session = Depends(get_db),
    _session: SessionPayload = Depends(require_body_assessment_access),
) -> BodyAssessmentOperationResponse:
    service = BodyAssessmentService(db)
    try:
        data = service.create_assessment(member_id, payload)
    except DuplicateAssessmentDateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return BodyAssessmentOperationResponse(message="Assessment saved", data=data)


@router.get("/body-assessments/{assessment_id}", response_model=BodyAssessmentOperationResponse)
def get_body_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    _session: SessionPayload = Depends(require_body_assessment_access),
) -> BodyAssessmentOperationResponse:
    data = BodyAssessmentService(db).get_assessment(assessment_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return BodyAssessmentOperationResponse(message="Assessment detail", data=data)
