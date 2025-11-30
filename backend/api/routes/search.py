"""
Search Endpoints - Flight availability search
"""
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
import asyncio

from loguru import logger

from scraper.base import CabinClass, FlightAvailability
from scraper.programs import get_scraper, SCRAPER_REGISTRY
from scraper.parsers.normalizer import FlightNormalizer
from storage.memory import get_store, SearchFilters


router = APIRouter()


# ============== Request/Response Models ==============

class SearchRequest(BaseModel):
    """Search request body"""
    origin: str = Field(..., min_length=3, max_length=3, description="Origin airport IATA code")
    destination: str = Field(..., min_length=3, max_length=3, description="Destination airport IATA code")
    departure_date: date = Field(..., description="Departure date")
    return_date: Optional[date] = Field(None, description="Return date (optional)")
    cabin_class: Optional[str] = Field(None, description="Cabin class filter")
    passengers: int = Field(1, ge=1, le=9, description="Number of passengers")
    programs: Optional[List[str]] = Field(None, description="Loyalty programs to search")


class FlightResponse(BaseModel):
    """Flight availability response"""
    id: str
    source_program: str
    origin: str
    destination: str
    airline: str
    flight_number: str
    departure_date: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    cabin_class: str
    points_required: int
    taxes_fees: float
    seats_available: int
    stops: int
    connection_airports: List[str]
    scraped_at: str


class SearchResponse(BaseModel):
    """Search response"""
    success: bool
    count: int
    flights: List[FlightResponse]
    message: Optional[str] = None


class ScrapeRequest(BaseModel):
    """Manual scrape trigger request"""
    origin: str = Field(..., min_length=3, max_length=3)
    destination: str = Field(..., min_length=3, max_length=3)
    departure_date: date
    programs: Optional[List[str]] = None


class ScrapeResponse(BaseModel):
    """Scrape response"""
    success: bool
    message: str
    flights_found: int


# ============== Helper Functions ==============

def flight_to_response(flight: FlightAvailability) -> FlightResponse:
    """Convert FlightAvailability to response model"""
    return FlightResponse(
        id=flight.id,
        source_program=flight.source_program,
        origin=flight.origin,
        destination=flight.destination,
        airline=flight.airline,
        flight_number=flight.flight_number,
        departure_date=flight.departure_date.isoformat(),
        departure_time=flight.departure_time,
        arrival_time=flight.arrival_time,
        duration_minutes=flight.duration_minutes,
        cabin_class=flight.cabin_class.value,
        points_required=flight.points_required,
        taxes_fees=flight.taxes_fees,
        seats_available=flight.seats_available,
        stops=flight.stops,
        connection_airports=flight.connection_airports,
        scraped_at=flight.scraped_at.isoformat(),
    )


def parse_cabin_class(cabin: Optional[str]) -> Optional[CabinClass]:
    """Parse cabin class string to enum"""
    if not cabin:
        return None
    
    cabin_lower = cabin.lower()
    mapping = {
        "economy": CabinClass.ECONOMY,
        "premium_economy": CabinClass.PREMIUM_ECONOMY,
        "premium": CabinClass.PREMIUM_ECONOMY,
        "business": CabinClass.BUSINESS,
        "first": CabinClass.FIRST,
    }
    return mapping.get(cabin_lower)


# ============== Endpoints ==============

@router.post("/search", response_model=SearchResponse)
async def search_flights(request: SearchRequest):
    """
    Search for award flight availability.
    
    First checks cached data, then triggers live scrape if needed.
    """
    store = get_store()
    
    # Build filters
    filters = SearchFilters(
        origin=request.origin.upper(),
        destination=request.destination.upper(),
        departure_date=request.departure_date,
        cabin_class=parse_cabin_class(request.cabin_class),
        programs=request.programs,
    )
    
    # Search cached data
    results = store.search(filters, sort_by="points", limit=100)
    
    if results:
        return SearchResponse(
            success=True,
            count=len(results),
            flights=[flight_to_response(f) for f in results],
            message=f"Found {len(results)} cached flights"
        )
    
    # No cached results - trigger live scrape
    logger.info(f"No cached results for {request.origin}-{request.destination}, triggering scrape")
    
    programs_to_search = request.programs or list(SCRAPER_REGISTRY.keys())
    all_flights = []
    
    for program_name in programs_to_search:
        if program_name not in SCRAPER_REGISTRY:
            continue
        
        try:
            scraper_class = SCRAPER_REGISTRY[program_name]
            scraper = scraper_class()
            
            flights = await scraper.search_availability(
                origin=request.origin.upper(),
                destination=request.destination.upper(),
                departure_date=request.departure_date,
                cabin_class=parse_cabin_class(request.cabin_class),
                passengers=request.passengers
            )
            
            # Normalize and store
            normalized = FlightNormalizer.normalize_flights(flights)
            store.add_many(normalized)
            all_flights.extend(normalized)
            
        except Exception as e:
            logger.error(f"Error scraping {program_name}: {e}")
            continue
    
    return SearchResponse(
        success=True,
        count=len(all_flights),
        flights=[flight_to_response(f) for f in all_flights],
        message=f"Scraped {len(all_flights)} flights from {len(programs_to_search)} programs"
    )


@router.get("/availability", response_model=SearchResponse)
async def get_availability(
    origin: str = Query(..., min_length=3, max_length=3, description="Origin IATA code"),
    destination: str = Query(..., min_length=3, max_length=3, description="Destination IATA code"),
    date: Optional[str] = Query(None, description="Departure date (YYYY-MM-DD)"),
    date_from: Optional[str] = Query(None, description="Date range start"),
    date_to: Optional[str] = Query(None, description="Date range end"),
    cabin: Optional[str] = Query(None, description="Cabin class"),
    max_points: Optional[int] = Query(None, description="Maximum points"),
    airlines: Optional[str] = Query(None, description="Comma-separated airline codes"),
    programs: Optional[str] = Query(None, description="Comma-separated program names"),
    direct_only: bool = Query(False, description="Direct flights only"),
    sort_by: str = Query("points", description="Sort field"),
    sort_order: str = Query("asc", description="Sort order"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    Query cached flight availability with filters.
    """
    store = get_store()
    
    # Parse date filters
    departure_date = None
    date_range_start = None
    date_range_end = None
    
    if date:
        try:
            from datetime import datetime
            departure_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")
    
    if date_from:
        try:
            from datetime import datetime
            date_range_start = datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date_from format")
    
    if date_to:
        try:
            from datetime import datetime
            date_range_end = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date_to format")
    
    # Parse list filters
    airline_list = [a.strip().upper() for a in airlines.split(",")] if airlines else None
    program_list = [p.strip() for p in programs.split(",")] if programs else None
    
    # Build filters
    filters = SearchFilters(
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        cabin_class=parse_cabin_class(cabin),
        max_points=max_points,
        airlines=airline_list,
        programs=program_list,
        direct_only=direct_only,
    )
    
    results = store.search(
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset
    )
    
    return SearchResponse(
        success=True,
        count=len(results),
        flights=[flight_to_response(f) for f in results],
    )


@router.post("/scrape", response_model=ScrapeResponse)
async def trigger_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Manually trigger a scrape for a specific route.
    Scrape runs in background, results stored for later query.
    """
    programs_to_search = request.programs or list(SCRAPER_REGISTRY.keys())
    
    async def run_scrape():
        store = get_store()
        total_flights = 0
        
        for program_name in programs_to_search:
            if program_name not in SCRAPER_REGISTRY:
                continue
            
            try:
                scraper_class = SCRAPER_REGISTRY[program_name]
                scraper = scraper_class()
                
                flights = await scraper.search_availability(
                    origin=request.origin.upper(),
                    destination=request.destination.upper(),
                    departure_date=request.departure_date,
                )
                
                normalized = FlightNormalizer.normalize_flights(flights)
                store.add_many(normalized)
                total_flights += len(normalized)
                
                logger.info(f"Scraped {len(normalized)} flights from {program_name}")
                
            except Exception as e:
                logger.error(f"Scrape error for {program_name}: {e}")
        
        logger.info(f"Scrape complete: {total_flights} total flights")
    
    # Run in background
    background_tasks.add_task(run_scrape)
    
    return ScrapeResponse(
        success=True,
        message=f"Scrape started for {request.origin}-{request.destination} on {request.departure_date}",
        flights_found=0  # Will be populated async
    )


@router.delete("/cache")
async def clear_cache():
    """Clear all cached flight data"""
    store = get_store()
    store.clear()
    return {"success": True, "message": "Cache cleared"}


@router.delete("/cache/expired")
async def clear_expired():
    """Clear expired flight data"""
    store = get_store()
    count = store.clear_expired()
    return {"success": True, "message": f"Removed {count} expired flights"}
