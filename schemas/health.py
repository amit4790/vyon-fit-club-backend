"""
Health Check Schemas
"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response model"""
    
    status: str = Field(..., description="Status of the backend")
    message: str = Field(..., description="Health status message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "VYON Backend Running"
            }
        }
