"""
Health Check Routes
"""

from fastapi import APIRouter
from schemas.health import HealthResponse

router = APIRouter(prefix="/api", tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check if the backend is running and healthy",
    responses={200: {"description": "Backend is running successfully"}}
)
def health_check() -> HealthResponse:
    """
    Health check endpoint
    
    Returns:
        HealthResponse: Status and message indicating backend health
    """
    return HealthResponse(
        status="success",
        message="VYON Backend Running"
    )
