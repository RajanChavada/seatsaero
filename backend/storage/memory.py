"""
In-Memory Store - Simple storage for MVP with scrape statistics
Future: Replace with PostgreSQL/Aurora
"""
from typing import List, Dict, Optional, Any
from datetime import datetime, date, timedelta
from collections import defaultdict
import threading
from dataclasses import dataclass, field

from loguru import logger

from scraper.base import FlightAvailability, CabinClass


@dataclass
class SearchFilters:
    """Filters for flight search"""
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[date] = None
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None
    cabin_class: Optional[CabinClass] = None
    max_points: Optional[int] = None
    min_points: Optional[int] = None
    airlines: Optional[List[str]] = None
    programs: Optional[List[str]] = None
    direct_only: bool = False
    max_stops: Optional[int] = None


@dataclass
class ScrapeStats:
    """Statistics for a single scrape operation"""
    program: str
    timestamp: datetime
    success: bool
    flights_found: int = 0
    duration_ms: int = 0
    error_type: Optional[str] = None  # captcha, rate_limit, blocked, timeout, etc.
    http_status: Optional[int] = None
    proxy_id: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None


@dataclass
class ProgramStats:
    """Aggregated statistics for a program"""
    program: str
    total_scrapes: int = 0
    successful_scrapes: int = 0
    failed_scrapes: int = 0
    total_flights_found: int = 0
    captcha_count: int = 0
    rate_limit_count: int = 0
    blocked_count: int = 0
    timeout_count: int = 0
    other_error_count: int = 0
    avg_duration_ms: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        if self.total_scrapes == 0:
            return 0.0
        return (self.successful_scrapes / self.total_scrapes) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "program": self.program,
            "total_scrapes": self.total_scrapes,
            "successful_scrapes": self.successful_scrapes,
            "failed_scrapes": self.failed_scrapes,
            "success_rate": round(self.success_rate, 2),
            "total_flights_found": self.total_flights_found,
            "captcha_count": self.captcha_count,
            "rate_limit_count": self.rate_limit_count,
            "blocked_count": self.blocked_count,
            "timeout_count": self.timeout_count,
            "other_error_count": self.other_error_count,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
        }


class ScrapeStatsTracker:
    """
    Tracks scrape statistics per program.
    
    Features:
    - Per-program success/failure tracking
    - CAPTCHA and block detection counts
    - Proxy performance tracking
    - Rolling window stats
    """
    
    def __init__(self, window_hours: int = 24):
        self._stats: List[ScrapeStats] = []
        self._program_stats: Dict[str, ProgramStats] = {}
        self._proxy_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"success": 0, "failure": 0})
        self._lock = threading.RLock()
        self._window_hours = window_hours
    
    def record(self, stats: ScrapeStats) -> None:
        """Record a scrape operation"""
        with self._lock:
            self._stats.append(stats)
            
            # Update program stats
            if stats.program not in self._program_stats:
                self._program_stats[stats.program] = ProgramStats(program=stats.program)
            
            prog_stats = self._program_stats[stats.program]
            prog_stats.total_scrapes += 1
            
            if stats.success:
                prog_stats.successful_scrapes += 1
                prog_stats.total_flights_found += stats.flights_found
                prog_stats.last_success = stats.timestamp
                
                # Update average duration
                if prog_stats.successful_scrapes > 0:
                    total_duration = (prog_stats.avg_duration_ms * (prog_stats.successful_scrapes - 1) 
                                     + stats.duration_ms)
                    prog_stats.avg_duration_ms = total_duration / prog_stats.successful_scrapes
            else:
                prog_stats.failed_scrapes += 1
                prog_stats.last_failure = stats.timestamp
                
                # Track error types
                if stats.error_type:
                    error_type = stats.error_type.lower()
                    if "captcha" in error_type:
                        prog_stats.captcha_count += 1
                    elif "rate_limit" in error_type or "429" in str(stats.http_status or ""):
                        prog_stats.rate_limit_count += 1
                    elif "blocked" in error_type or stats.http_status in [403, 428]:
                        prog_stats.blocked_count += 1
                    elif "timeout" in error_type:
                        prog_stats.timeout_count += 1
                    else:
                        prog_stats.other_error_count += 1
            
            # Track proxy stats
            if stats.proxy_id:
                if stats.success:
                    self._proxy_stats[stats.proxy_id]["success"] += 1
                else:
                    self._proxy_stats[stats.proxy_id]["failure"] += 1
    
    def record_success(
        self,
        program: str,
        flights_found: int,
        duration_ms: int = 0,
        proxy_id: str = None,
        origin: str = None,
        destination: str = None
    ) -> None:
        """Record a successful scrape"""
        self.record(ScrapeStats(
            program=program,
            timestamp=datetime.utcnow(),
            success=True,
            flights_found=flights_found,
            duration_ms=duration_ms,
            proxy_id=proxy_id,
            origin=origin,
            destination=destination
        ))
    
    def record_failure(
        self,
        program: str,
        error_type: str,
        http_status: int = None,
        duration_ms: int = 0,
        proxy_id: str = None,
        origin: str = None,
        destination: str = None
    ) -> None:
        """Record a failed scrape"""
        self.record(ScrapeStats(
            program=program,
            timestamp=datetime.utcnow(),
            success=False,
            error_type=error_type,
            http_status=http_status,
            duration_ms=duration_ms,
            proxy_id=proxy_id,
            origin=origin,
            destination=destination
        ))
    
    def get_program_stats(self, program: str = None) -> Dict[str, Any]:
        """Get stats for a specific program or all programs"""
        with self._lock:
            if program:
                if program in self._program_stats:
                    return self._program_stats[program].to_dict()
                return {}
            
            return {
                name: stats.to_dict() 
                for name, stats in self._program_stats.items()
            }
    
    def get_recent_stats(self, hours: int = None) -> Dict[str, Any]:
        """Get stats from the last N hours"""
        hours = hours or self._window_hours
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        with self._lock:
            recent = [s for s in self._stats if s.timestamp > cutoff]
            
            # Aggregate by program
            by_program = defaultdict(lambda: {
                "total": 0, "success": 0, "failure": 0, "flights": 0
            })
            
            for stat in recent:
                by_program[stat.program]["total"] += 1
                if stat.success:
                    by_program[stat.program]["success"] += 1
                    by_program[stat.program]["flights"] += stat.flights_found
                else:
                    by_program[stat.program]["failure"] += 1
            
            return {
                "window_hours": hours,
                "total_scrapes": len(recent),
                "by_program": dict(by_program),
            }
    
    def get_proxy_stats(self) -> Dict[str, Dict[str, int]]:
        """Get proxy performance stats"""
        with self._lock:
            return dict(self._proxy_stats)
    
    def cleanup_old_stats(self, hours: int = None) -> int:
        """Remove stats older than N hours"""
        hours = hours or self._window_hours * 2
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        with self._lock:
            original_count = len(self._stats)
            self._stats = [s for s in self._stats if s.timestamp > cutoff]
            removed = original_count - len(self._stats)
            
            if removed:
                logger.debug(f"Cleaned up {removed} old scrape stats")
            
            return removed
    
    def get_summary(self) -> Dict[str, Any]:
        """Get overall summary stats"""
        with self._lock:
            total_scrapes = sum(s.total_scrapes for s in self._program_stats.values())
            total_success = sum(s.successful_scrapes for s in self._program_stats.values())
            total_flights = sum(s.total_flights_found for s in self._program_stats.values())
            total_captcha = sum(s.captcha_count for s in self._program_stats.values())
            total_blocked = sum(s.blocked_count for s in self._program_stats.values())
            
            return {
                "total_scrapes": total_scrapes,
                "total_success": total_success,
                "total_flights_found": total_flights,
                "overall_success_rate": (total_success / total_scrapes * 100) if total_scrapes > 0 else 0,
                "total_captchas": total_captcha,
                "total_blocks": total_blocked,
                "programs_tracked": len(self._program_stats),
                "proxies_tracked": len(self._proxy_stats),
            }


# Global stats tracker instance
_stats_tracker: Optional[ScrapeStatsTracker] = None


def get_stats_tracker() -> ScrapeStatsTracker:
    """Get the global stats tracker instance"""
    global _stats_tracker
    if _stats_tracker is None:
        _stats_tracker = ScrapeStatsTracker()
    return _stats_tracker


class InMemoryStore:
    """
    Thread-safe in-memory storage for flight availability data.
    
    Indexes:
    - By route (origin-destination)
    - By date
    - By program
    
    Future: Replace with SQLAlchemy + PostgreSQL
    """
    
    def __init__(self):
        self._flights: Dict[str, FlightAvailability] = {}
        self._index_by_route: Dict[str, List[str]] = defaultdict(list)
        self._index_by_date: Dict[str, List[str]] = defaultdict(list)
        self._index_by_program: Dict[str, List[str]] = defaultdict(list)
        self._lock = threading.RLock()
        
        logger.info("Initialized in-memory flight store")
    
    def _make_route_key(self, origin: str, destination: str) -> str:
        """Create route key from origin and destination"""
        return f"{origin.upper()}-{destination.upper()}"
    
    def _make_date_key(self, d: date) -> str:
        """Create date key"""
        return d.isoformat()
    
    def add(self, flight: FlightAvailability) -> None:
        """Add a flight to the store"""
        with self._lock:
            flight_id = flight.id
            
            # Remove from indexes if updating existing flight
            if flight_id in self._flights:
                self._remove_from_indexes(flight_id)
            
            # Store the flight
            self._flights[flight_id] = flight
            
            # Update indexes
            route_key = self._make_route_key(flight.origin, flight.destination)
            self._index_by_route[route_key].append(flight_id)
            
            date_key = self._make_date_key(flight.departure_date)
            self._index_by_date[date_key].append(flight_id)
            
            self._index_by_program[flight.source_program].append(flight_id)
    
    def add_many(self, flights: List[FlightAvailability]) -> int:
        """Add multiple flights. Returns count added."""
        count = 0
        for flight in flights:
            self.add(flight)
            count += 1
        logger.info(f"Added {count} flights to store")
        return count
    
    def get(self, flight_id: str) -> Optional[FlightAvailability]:
        """Get a flight by ID"""
        with self._lock:
            return self._flights.get(flight_id)
    
    def _remove_from_indexes(self, flight_id: str) -> None:
        """Remove flight ID from all indexes"""
        flight = self._flights.get(flight_id)
        if not flight:
            return
        
        route_key = self._make_route_key(flight.origin, flight.destination)
        if flight_id in self._index_by_route[route_key]:
            self._index_by_route[route_key].remove(flight_id)
        
        date_key = self._make_date_key(flight.departure_date)
        if flight_id in self._index_by_date[date_key]:
            self._index_by_date[date_key].remove(flight_id)
        
        if flight_id in self._index_by_program[flight.source_program]:
            self._index_by_program[flight.source_program].remove(flight_id)
    
    def remove(self, flight_id: str) -> bool:
        """Remove a flight by ID"""
        with self._lock:
            if flight_id not in self._flights:
                return False
            
            self._remove_from_indexes(flight_id)
            del self._flights[flight_id]
            return True
    
    def search(
        self,
        filters: SearchFilters,
        sort_by: str = "points",
        sort_order: str = "asc",
        limit: int = 100,
        offset: int = 0
    ) -> List[FlightAvailability]:
        """
        Search flights with filters.
        
        Args:
            filters: SearchFilters object
            sort_by: Field to sort by (points, duration, departure_time)
            sort_order: asc or desc
            limit: Max results to return
            offset: Offset for pagination
            
        Returns:
            List of matching FlightAvailability objects
        """
        with self._lock:
            # Start with candidate IDs based on route index
            candidate_ids: Optional[set] = None
            
            # Use route index if origin/destination provided
            if filters.origin and filters.destination:
                route_key = self._make_route_key(filters.origin, filters.destination)
                candidate_ids = set(self._index_by_route.get(route_key, []))
            
            # Narrow by date if provided
            if filters.departure_date:
                date_key = self._make_date_key(filters.departure_date)
                date_ids = set(self._index_by_date.get(date_key, []))
                if candidate_ids is not None:
                    candidate_ids &= date_ids
                else:
                    candidate_ids = date_ids
            
            # Narrow by program if provided
            if filters.programs:
                program_ids = set()
                for program in filters.programs:
                    program_ids.update(self._index_by_program.get(program, []))
                if candidate_ids is not None:
                    candidate_ids &= program_ids
                else:
                    candidate_ids = program_ids
            
            # If no indexes used, search all
            if candidate_ids is None:
                candidate_ids = set(self._flights.keys())
            
            # Filter candidates
            results = []
            for flight_id in candidate_ids:
                flight = self._flights.get(flight_id)
                if not flight:
                    continue
                
                if not self._matches_filters(flight, filters):
                    continue
                
                results.append(flight)
            
            # Sort results
            results = self._sort_results(results, sort_by, sort_order)
            
            # Apply pagination
            return results[offset:offset + limit]
    
    def _matches_filters(self, flight: FlightAvailability, filters: SearchFilters) -> bool:
        """Check if flight matches all filters"""
        # Origin
        if filters.origin and flight.origin.upper() != filters.origin.upper():
            return False
        
        # Destination
        if filters.destination and flight.destination.upper() != filters.destination.upper():
            return False
        
        # Date range
        if filters.date_range_start and flight.departure_date < filters.date_range_start:
            return False
        if filters.date_range_end and flight.departure_date > filters.date_range_end:
            return False
        
        # Cabin class
        if filters.cabin_class and flight.cabin_class != filters.cabin_class:
            return False
        
        # Points range
        if filters.max_points and flight.points_required > filters.max_points:
            return False
        if filters.min_points and flight.points_required < filters.min_points:
            return False
        
        # Airlines
        if filters.airlines and flight.airline not in filters.airlines:
            return False
        
        # Programs
        if filters.programs and flight.source_program not in filters.programs:
            return False
        
        # Direct only
        if filters.direct_only and flight.stops > 0:
            return False
        
        # Max stops
        if filters.max_stops is not None and flight.stops > filters.max_stops:
            return False
        
        # Not expired
        if flight.is_expired():
            return False
        
        return True
    
    def _sort_results(
        self,
        results: List[FlightAvailability],
        sort_by: str,
        sort_order: str
    ) -> List[FlightAvailability]:
        """Sort results by specified field"""
        reverse = sort_order.lower() == "desc"
        
        if sort_by == "points":
            return sorted(results, key=lambda f: f.points_required, reverse=reverse)
        elif sort_by == "duration":
            return sorted(results, key=lambda f: f.duration_minutes, reverse=reverse)
        elif sort_by == "departure_time":
            return sorted(results, key=lambda f: f.departure_time, reverse=reverse)
        elif sort_by == "date":
            return sorted(results, key=lambda f: f.departure_date, reverse=reverse)
        elif sort_by == "stops":
            return sorted(results, key=lambda f: f.stops, reverse=reverse)
        else:
            return results
    
    def get_by_route(self, origin: str, destination: str) -> List[FlightAvailability]:
        """Get all flights for a route"""
        with self._lock:
            route_key = self._make_route_key(origin, destination)
            flight_ids = self._index_by_route.get(route_key, [])
            return [self._flights[fid] for fid in flight_ids if fid in self._flights]
    
    def get_by_date(self, d: date) -> List[FlightAvailability]:
        """Get all flights for a date"""
        with self._lock:
            date_key = self._make_date_key(d)
            flight_ids = self._index_by_date.get(date_key, [])
            return [self._flights[fid] for fid in flight_ids if fid in self._flights]
    
    def get_by_program(self, program: str) -> List[FlightAvailability]:
        """Get all flights from a program"""
        with self._lock:
            flight_ids = self._index_by_program.get(program, [])
            return [self._flights[fid] for fid in flight_ids if fid in self._flights]
    
    def get_all(self) -> List[FlightAvailability]:
        """Get all flights"""
        with self._lock:
            return list(self._flights.values())
    
    def count(self) -> int:
        """Get total number of stored flights"""
        with self._lock:
            return len(self._flights)
    
    def __len__(self) -> int:
        """Support len() on store"""
        return self.count()
    
    def clear(self) -> None:
        """Clear all data"""
        with self._lock:
            self._flights.clear()
            self._index_by_route.clear()
            self._index_by_date.clear()
            self._index_by_program.clear()
        logger.info("Cleared flight store")
    
    def clear_expired(self) -> int:
        """Remove expired flights. Returns count removed."""
        with self._lock:
            expired_ids = [
                fid for fid, flight in self._flights.items()
                if flight.is_expired()
            ]
            
            for fid in expired_ids:
                self.remove(fid)
            
            if expired_ids:
                logger.info(f"Removed {len(expired_ids)} expired flights")
            
            return len(expired_ids)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics"""
        with self._lock:
            programs = defaultdict(int)
            for flight in self._flights.values():
                programs[flight.source_program] += 1
            
            return {
                "total_flights": len(self._flights),
                "routes": len(self._index_by_route),
                "dates": len(self._index_by_date),
                "programs": dict(programs),
            }


# Global store instance (singleton for MVP)
_store: Optional[InMemoryStore] = None


def get_store() -> InMemoryStore:
    """Get the global store instance"""
    global _store
    if _store is None:
        _store = InMemoryStore()
    return _store
