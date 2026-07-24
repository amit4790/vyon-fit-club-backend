"""
VYON Fit Club Management System - Backend API
Main FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from routes import health_router, auth_router, dashboard_router, admin_router


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application
    
    Returns:
        FastAPI: Configured application instance
    """
    
    app = FastAPI(
        title=settings.api_title,
        description=settings.api_description,
        version=settings.api_version,
        debug=settings.debug
    )
    
    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(admin_router)
    
    return app


# Create application instance
app = create_app()


@app.on_event("startup")
async def startup_event():
    """Application startup event handler"""
    print(f"🚀 {settings.api_title} v{settings.api_version} is starting...")
    print(f"🔗 CORS Origins: {settings.get_cors_origins}")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event handler"""
    print(f"🛑 {settings.api_title} is shutting down...")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
