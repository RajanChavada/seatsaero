"""
Programs Endpoints - Loyalty program information
"""
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel
import asyncio

from loguru import logger

from scraper.programs import (
    SCRAPER_REGISTRY, 
    PROGRAM_DISPLAY_NAMES, 
    PROGRAM_ROUTES,
    get_scraper,
    get_programs_for_route
)


router = APIRouter()


class SampleRoute(BaseModel):
    """Sample route for a program"""
    origin: str
    destination: str
    description: str


class ProgramInfo(BaseModel):
    """Loyalty program information"""
    name: str
    display_name: str
    supported_airlines: List[str]
    status: str  # healthy, unhealthy, unknown
    sample_routes: List[SampleRoute] = []


class ProgramsResponse(BaseModel):
    """Programs list response"""
    programs: List[ProgramInfo]
    count: int


class ProgramHealthResponse(BaseModel):
    """Health check response for a program"""
    program: str
    healthy: bool
    message: Optional[str] = None


class RouteRecommendation(BaseModel):
    """Recommended programs for a route"""
    origin: str
    destination: str
    recommended_programs: List[str]


@router.get("/programs", response_model=ProgramsResponse)
async def list_programs():
    """
    List all available loyalty programs with sample routes.
    """
    programs = []
    
    for name, scraper_class in SCRAPER_REGISTRY.items():
        scraper = scraper_class()
        
        # Get sample routes for this program
        routes = PROGRAM_ROUTES.get(name, [])
        sample_routes = [
            SampleRoute(origin=r[0], destination=r[1], description=r[2])
            for r in routes
        ]
        
        programs.append(ProgramInfo(
            name=scraper.program_name,
            display_name=PROGRAM_DISPLAY_NAMES.get(name, scraper.program_display_name),
            supported_airlines=scraper.supported_airlines,
            status="unknown",  # Would need health check
            sample_routes=sample_routes
        ))
    
    return ProgramsResponse(
        programs=programs,
        count=len(programs)
    )


@router.get("/programs/recommend")
async def recommend_programs(origin: str, destination: str) -> RouteRecommendation:
    """
    Get recommended programs for a specific route.
    
    Uses smart route-based selection to suggest the best programs
    for searching award availability.
    """
    recommended = get_programs_for_route(origin, destination)
    
    return RouteRecommendation(
        origin=origin.upper(),
        destination=destination.upper(),
        recommended_programs=recommended
    )


@router.get("/programs/{program_name}", response_model=ProgramInfo)
async def get_program(program_name: str):
    """
    Get information about a specific loyalty program.
    """
    if program_name not in SCRAPER_REGISTRY:
        from fastapi import HTTPException
        raise HTTPException(404, f"Program not found: {program_name}")
    
    scraper_class = SCRAPER_REGISTRY[program_name]
    scraper = scraper_class()
    
    # Run health check
    try:
        is_healthy = await scraper.health_check()
        status = "healthy" if is_healthy else "unhealthy"
    except Exception as e:
        logger.error(f"Health check failed for {program_name}: {e}")
        status = "unhealthy"
    
    # Get sample routes
    routes = PROGRAM_ROUTES.get(program_name, [])
    sample_routes = [
        SampleRoute(origin=r[0], destination=r[1], description=r[2])
        for r in routes
    ]
    
    return ProgramInfo(
        name=scraper.program_name,
        display_name=PROGRAM_DISPLAY_NAMES.get(program_name, scraper.program_display_name),
        supported_airlines=scraper.supported_airlines,
        status=status,
        sample_routes=sample_routes
    )


@router.get("/programs/{program_name}/health", response_model=ProgramHealthResponse)
async def check_program_health(program_name: str):
    """
    Check if a loyalty program scraper is working.
    """
    if program_name not in SCRAPER_REGISTRY:
        from fastapi import HTTPException
        raise HTTPException(404, f"Program not found: {program_name}")
    
    scraper_class = SCRAPER_REGISTRY[program_name]
    scraper = scraper_class()
    
    try:
        is_healthy = await scraper.health_check()
        return ProgramHealthResponse(
            program=program_name,
            healthy=is_healthy,
            message="OK" if is_healthy else "Failed to connect"
        )
    except Exception as e:
        return ProgramHealthResponse(
            program=program_name,
            healthy=False,
            message=str(e)
        )


@router.get("/programs/health/all")
async def check_all_programs_health():
    """
    Check health of all program scrapers.
    """
    results = {}
    
    async def check_one(name: str, scraper_class):
        try:
            scraper = scraper_class()
            is_healthy = await scraper.health_check()
            return name, is_healthy
        except Exception:
            return name, False
    
    # Run health checks concurrently
    tasks = [
        check_one(name, scraper_class) 
        for name, scraper_class in SCRAPER_REGISTRY.items()
    ]
    
    check_results = await asyncio.gather(*tasks)
    
    for name, is_healthy in check_results:
        results[name] = {
            "healthy": is_healthy,
            "status": "healthy" if is_healthy else "unhealthy"
        }
    
    healthy_count = sum(1 for r in results.values() if r["healthy"])
    
    return {
        "programs": results,
        "summary": {
            "total": len(results),
            "healthy": healthy_count,
            "unhealthy": len(results) - healthy_count
        }
    }
