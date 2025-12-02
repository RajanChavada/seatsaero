"""
Search API Routes - Flight availability search with caching and fallbacks
"""
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import random
import hashlib

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from loguru import logger

from storage.memory import get_store, get_stats_tracker, SearchFilters, InMemoryStore, ScrapeStatsTracker
from scraper.base import FlightAvailability, CabinClass

router = APIRouter()

# Thread pool for running scrapers (they use Selenium which is sync)
_executor = ThreadPoolExecutor(max_workers=4)


# ============================================================================
# Request/Response Models
# ============================================================================

class CabinClassEnum(str, Enum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


class SearchRequest(BaseModel):
    """Search request model"""
    origin: str = Field(..., min_length=3, max_length=3, description="Origin airport code")
    destination: str = Field(..., min_length=3, max_length=3, description="Destination airport code")
    departure_date: date = Field(..., description="Departure date")
    cabin_class: Optional[CabinClassEnum] = None
    passengers: int = Field(default=1, ge=1, le=9)
    programs: Optional[List[str]] = Field(default=None, description="Loyalty programs to search")
    use_cache: bool = Field(default=True, description="Use cached results if available")
    max_points: Optional[int] = Field(default=None, description="Maximum points filter")
    direct_only: bool = Field(default=False, description="Only show direct flights")


class FlightResult(BaseModel):
    """Single flight result - matches FlightAvailability fields"""
    id: str
    origin: str
    destination: str
    departure_date: str
    departure_time: str
    arrival_time: str
    airline: str
    flight_number: str
    cabin_class: str
    points_required: int
    taxes_fees: float
    cash_price: Optional[float] = None  # For Google Flights cash fares
    seats_available: int
    duration_minutes: int
    stops: int
    connection_airports: List[str] = []
    source_program: str
    scraped_at: str
    
    @classmethod
    def from_flight(cls, flight: FlightAvailability) -> "FlightResult":
        """Convert FlightAvailability to FlightResult"""
        return cls(
            id=flight.id,
            origin=flight.origin,
            destination=flight.destination,
            departure_date=flight.departure_date.isoformat() if isinstance(flight.departure_date, date) else str(flight.departure_date),
            departure_time=flight.departure_time if flight.departure_time else "",
            arrival_time=flight.arrival_time if flight.arrival_time else "",
            airline=flight.airline,
            flight_number=flight.flight_number,
            cabin_class=flight.cabin_class.value if hasattr(flight.cabin_class, 'value') else str(flight.cabin_class),
            points_required=flight.points_required,
            taxes_fees=flight.taxes_fees,
            cash_price=getattr(flight, 'cash_price', None),  # Cash price for Google Flights
            seats_available=flight.seats_available,
            duration_minutes=flight.duration_minutes,
            stops=flight.stops,
            connection_airports=flight.connection_airports or [],
            source_program=flight.source_program,
            scraped_at=flight.scraped_at.isoformat() if isinstance(flight.scraped_at, datetime) else str(flight.scraped_at)
        )


class ProgramStatus(BaseModel):
    """Status of a single program's scrape"""
    program: str
    success: bool
    flights_found: int = 0
    error: Optional[str] = None
    blocked: bool = False
    cached: bool = False


class SearchResponse(BaseModel):
    """Search response model"""
    success: bool
    flights: List[FlightResult]
    total_count: int
    search_params: Dict[str, Any]
    program_status: List[ProgramStatus]
    from_cache: bool
    demo_mode: bool = False
    message: Optional[str] = None


# ============================================================================
# Demo Data Generator
# ============================================================================

def generate_demo_flights(
    origin: str,
    destination: str,
    departure_date: date,
    cabin_class: Optional[CabinClass] = None
) -> List[FlightAvailability]:
    """
    Generate realistic demo flight data.
    Uses only fields that exist in FlightAvailability dataclass.
    """
    airlines = [
        ("United Airlines", "UA", "united_mileageplus"),
        ("Air Canada", "AC", "aeroplan"),
        ("British Airways", "BA", "avios"),
        ("Lufthansa", "LH", "miles_and_more"),
        ("Emirates", "EK", "emirates_skywards"),
        ("Singapore Airlines", "SQ", "krisflyer"),
        ("ANA", "NH", "ana_mileage_club"),
        ("Delta", "DL", "delta_skymiles"),
    ]
    
    cabins = [CabinClass.ECONOMY, CabinClass.BUSINESS, CabinClass.FIRST]
    if cabin_class:
        cabins = [cabin_class]
    
    flights = []
    num_flights = random.randint(5, 15)
    
    for i in range(num_flights):
        airline_name, airline_code, program = random.choice(airlines)
        cabin = random.choice(cabins)
        
        # Generate realistic points based on cabin
        base_points = {
            CabinClass.ECONOMY: random.randint(15000, 45000),
            CabinClass.PREMIUM_ECONOMY: random.randint(40000, 80000),
            CabinClass.BUSINESS: random.randint(60000, 150000),
            CabinClass.FIRST: random.randint(100000, 250000),
        }
        
        # Generate times as strings (HH:MM format)
        hour = random.randint(6, 22)
        minute = random.choice([0, 15, 30, 45])
        dep_time_str = f"{hour:02d}:{minute:02d}"
        
        duration = random.randint(180, 900)  # 3-15 hours
        
        arrival_hour = (hour + duration // 60) % 24
        arrival_minute = (minute + duration % 60) % 60
        arr_time_str = f"{arrival_hour:02d}:{arrival_minute:02d}"
        
        stops = random.choices([0, 1, 2], weights=[0.5, 0.35, 0.15])[0]
        
        # Generate connection airports if stops > 0
        connection_airports = []
        if stops > 0:
            possible_connections = ["ORD", "LAX", "JFK", "LHR", "FRA", "DXB", "SIN", "HKG", "NRT"]
            connection_airports = random.sample(possible_connections, min(stops, len(possible_connections)))
        
        flight_number = f"{airline_code}{random.randint(100, 9999)}"
        
        # Generate unique ID
        flight_id = hashlib.md5(
            f"{origin}{destination}{departure_date}{flight_number}{cabin.value}{program}".encode()
        ).hexdigest()[:12]
        
        # Create FlightAvailability using ONLY valid fields
        flight = FlightAvailability(
            id=flight_id,
            source_program=program,
            origin=origin.upper(),
            destination=destination.upper(),
            airline=airline_name,
            flight_number=flight_number,
            departure_date=departure_date,
            departure_time=dep_time_str,
            arrival_time=arr_time_str,
            duration_minutes=duration,
            cabin_class=cabin,
            points_required=base_points[cabin],
            taxes_fees=round(random.uniform(50, 500), 2),
            seats_available=random.randint(1, 9),
            stops=stops,
            connection_airports=connection_airports,
            scraped_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=6),
            raw_data={"demo": True, "generated_at": datetime.utcnow().isoformat()}
        )
        flights.append(flight)
    
    logger.info(f"Generated {len(flights)} demo flights for {origin}->{destination}")
    return flights


# ============================================================================
# Scraper Execution
# ============================================================================

def _run_scraper_sync(
    program: str,
    origin: str,
    destination: str,
    departure_date: date,
    cabin_class: Optional[CabinClass]
) -> tuple:
    """
    Run a single scraper synchronously (for thread pool).
    Returns: (program_name, success, flights, error_message)
    """
    try:
        # Import scrapers here to avoid circular imports
        scraper = None
        
        if program == "united_mileageplus":
            from scraper.programs.united import UnitedMileagePlusScraper
            scraper = UnitedMileagePlusScraper()
        elif program == "aeroplan":
            from scraper.programs.aeroplan import AeroplanScraper
            scraper = AeroplanScraper()
        elif program == "jetblue_trueblue":
            from scraper.programs.jetblue import JetBlueTrueBlueScraper
            scraper = JetBlueTrueBlueScraper()
        elif program == "lufthansa_milesmore":
            from scraper.programs.lufthansa import LufthansaMilesMoreScraper
            scraper = LufthansaMilesMoreScraper()
        elif program == "virgin_atlantic":
            from scraper.programs.virgin_atlantic import VirginAtlanticFlyingClubScraper
            scraper = VirginAtlanticFlyingClubScraper()
        elif program == "google_flights":
            from scraper.programs.google_flights import GoogleFlightsScraper
            scraper = GoogleFlightsScraper()
        elif program == "demo":
            # Demo scraper returns synthetic data
            from scraper.programs.demo import DemoScraper
            scraper = DemoScraper()
        else:
            return (program, False, [], f"Unknown program: {program}")
        
        logger.info(f"Running {program} scraper for {origin}->{destination} on {departure_date}")
        
        # The scrapers have async search_availability, we need to run them in an event loop
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            flights = loop.run_until_complete(
                scraper.search_availability(
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    cabin_class=cabin_class
                )
            )
        finally:
            loop.close()
        
        return (program, True, list(flights) if flights else [], None)
        
    except Exception as e:
        logger.error(f"Scraper {program} failed: {e}")
        return (program, False, [], str(e))


async def execute_scrape(
    origin: str,
    destination: str,
    departure_date: date,
    cabin_class: Optional[CabinClass],
    programs: List[str],
    store: InMemoryStore,
    stats_tracker: ScrapeStatsTracker
) -> List[ProgramStatus]:
    """
    Execute scrapers for the given programs concurrently.
    """
    loop = asyncio.get_event_loop()
    program_statuses = []
    all_flights = []
    
    # Run scrapers concurrently using thread pool
    tasks = []
    for program in programs:
        task = loop.run_in_executor(
            _executor,
            _run_scraper_sync,
            program,
            origin,
            destination,
            departure_date,
            cabin_class
        )
        tasks.append((program, task))
    
    # Wait for all scrapers to complete
    for program, task in tasks:
        start_time = time.time()
        try:
            prog_name, success, flights, error = await task
            duration_ms = int((time.time() - start_time) * 1000)
            
            if success:
                all_flights.extend(flights)
                stats_tracker.record_success(
                    program=prog_name,
                    flights_found=len(flights),
                    duration_ms=duration_ms,
                    origin=origin,
                    destination=destination
                )
                program_statuses.append(ProgramStatus(
                    program=prog_name,
                    success=True,
                    flights_found=len(flights)
                ))
            else:
                blocked = "blocked" in (error or "").lower() or "captcha" in (error or "").lower()
                stats_tracker.record_failure(
                    program=prog_name,
                    error_type=error or "unknown",
                    duration_ms=duration_ms,
                    origin=origin,
                    destination=destination
                )
                program_statuses.append(ProgramStatus(
                    program=prog_name,
                    success=False,
                    error=error,
                    blocked=blocked
                ))
                
        except Exception as e:
            logger.error(f"Error running scraper {program}: {e}")
            program_statuses.append(ProgramStatus(
                program=program,
                success=False,
                error=str(e)
            ))
    
    # Store all flights
    if all_flights:
        store.add_many(all_flights)
    
    return program_statuses


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/search", response_model=SearchResponse)
async def search_flights(request: SearchRequest):
    """
    Search for award flight availability.
    
    Flow:
    1. Check cache for recent results
    2. If cache miss or stale, run scrapers
    3. If scrapers fail, fall back to demo data
    4. Return results with status information
    """
    store = get_store()
    stats_tracker = get_stats_tracker()
    
    # Convert cabin class
    cabin_class = None
    if request.cabin_class:
        cabin_class = CabinClass(request.cabin_class.value)
    
    # Import smart route-based program selection
    from scraper.programs import get_programs_for_route, SCRAPER_REGISTRY
    
    # Determine which programs to search
    # Use smart route-based selection if no specific programs requested
    if request.programs:
        # Use requested programs, filter to only available ones
        programs_to_search = [p for p in request.programs if p in SCRAPER_REGISTRY]
    else:
        # Smart selection based on route
        programs_to_search = get_programs_for_route(request.origin, request.destination)
        # Exclude demo from automatic selection (it's a fallback)
        programs_to_search = [p for p in programs_to_search if p != "demo"]
    
    # Ensure we have at least some programs to try
    if not programs_to_search:
        programs_to_search = ["demo"]
    
    logger.info(f"Programs for {request.origin}->{request.destination}: {programs_to_search}")
    
    # Build search filters
    filters = SearchFilters(
        origin=request.origin.upper(),
        destination=request.destination.upper(),
        departure_date=request.departure_date,
        cabin_class=cabin_class,
        max_points=request.max_points,
        direct_only=request.direct_only,
        programs=programs_to_search if request.programs else None
    )
    
    # Check cache first
    cached_flights = []
    cache_hit = False
    
    if request.use_cache:
        cached_flights = store.search(filters, limit=500)
        # Check if cache is fresh (less than 30 minutes old)
        if cached_flights:
            newest = max(f.scraped_at for f in cached_flights)
            cache_age = datetime.utcnow() - newest
            if cache_age < timedelta(minutes=30):
                cache_hit = True
                logger.info(f"Cache hit for {request.origin}->{request.destination}: {len(cached_flights)} flights")
    
    program_statuses = []
    demo_mode = False
    
    if cache_hit:
        # Return cached results
        program_statuses = [
            ProgramStatus(program=p, success=True, flights_found=0, cached=True)
            for p in programs_to_search
        ]
    else:
        # Cache miss - run scrapers
        logger.info(f"Cache miss for {request.origin}-{request.destination}, triggering scrape")
        
        # Try real scrapers first
        try:
            program_statuses = await execute_scrape(
                origin=request.origin.upper(),
                destination=request.destination.upper(),
                departure_date=request.departure_date,
                cabin_class=cabin_class,
                programs=programs_to_search,
                store=store,
                stats_tracker=stats_tracker
            )
        except Exception as e:
            logger.error(f"Scrape execution failed: {e}")
            program_statuses = [
                ProgramStatus(program=p, success=False, error=str(e))
                for p in programs_to_search
            ]
        
        # Check if any scraper succeeded
        any_success = any(ps.success and ps.flights_found > 0 for ps in program_statuses)
        
        if not any_success:
            # All scrapers failed - fall back to demo data
            logger.warning("All scrapers failed, falling back to demo data")
            demo_flights = generate_demo_flights(
                origin=request.origin.upper(),
                destination=request.destination.upper(),
                departure_date=request.departure_date,
                cabin_class=cabin_class
            )
            store.add_many(demo_flights)
            demo_mode = True
            
            # Update status to show demo mode
            program_statuses.append(ProgramStatus(
                program="demo",
                success=True,
                flights_found=len(demo_flights)
            ))
        
        # Fetch results from store
        cached_flights = store.search(filters, limit=500)
    
    # Convert to response format
    flight_results = [FlightResult.from_flight(f) for f in cached_flights]
    
    return SearchResponse(
        success=True,
        flights=flight_results,
        total_count=len(flight_results),
        search_params={
            "origin": request.origin.upper(),
            "destination": request.destination.upper(),
            "departure_date": request.departure_date.isoformat(),
            "cabin_class": request.cabin_class.value if request.cabin_class else None,
            "programs": programs_to_search,
        },
        program_status=program_statuses,
        from_cache=cache_hit,
        demo_mode=demo_mode,
        message="Demo data - real scrapers blocked or unavailable" if demo_mode else None
    )


@router.get("/search/quick")
async def quick_search(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: date = Query(...),
    cabin: Optional[CabinClassEnum] = Query(default=None)
):
    """Quick search endpoint with query parameters"""
    request = SearchRequest(
        origin=origin,
        destination=destination,
        departure_date=date,
        cabin_class=cabin
    )
    return await search_flights(request)


@router.get("/stats")
async def get_stats():
    """Get scraping statistics"""
    store = get_store()
    stats_tracker = get_stats_tracker()
    
    return {
        "success": True,
        "store": {
            "total_flights": store.count(),
            "routes": len(store._index_by_route),
            "stats": store.get_stats()
        },
        "scraping": {
            "summary": stats_tracker.get_summary(),
            "by_program": stats_tracker.get_program_stats(),
            "recent": stats_tracker.get_recent_stats(hours=1),
            "proxies": stats_tracker.get_proxy_stats()
        }
    }


@router.delete("/cache")
async def clear_cache():
    """Clear the flight cache"""
    store = get_store()
    store.clear()
    return {"success": True, "message": "Cache cleared"}


@router.delete("/cache/expired")
async def clear_expired():
    """Clear only expired flights from cache"""
    store = get_store()
    removed = store.clear_expired()
    return {"success": True, "removed": removed}
