"""
Health Check Endpoints
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime

from storage.memory import get_store


router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    version: str


class StatsResponse(BaseModel):
    """Store statistics response"""
    total_flights: int
    routes: int
    dates: int
    programs: dict


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="0.1.0"
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get store statistics"""
    store = get_store()
    stats = store.get_stats()
    return StatsResponse(**stats)
