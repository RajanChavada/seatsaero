"""
FastAPI Application - Main entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from loguru import logger

from config import settings
from api.routes import search, health, programs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Seats Aero Clone API")
    logger.info(f"Running on {settings.api_host}:{settings.api_port}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    
    app = FastAPI(
        title="Seats Aero Clone",
        description="Award flight availability search across loyalty programs",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(search.router, prefix="/api", tags=["Search"])
    app.include_router(programs.router, prefix="/api", tags=["Programs"])
    
    return app


# Create app instance
app = create_app()
