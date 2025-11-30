"""
In-Memory Store - Simple storage for MVP
Future: Replace with PostgreSQL/Aurora
"""
from typing import List, Dict, Optional, Any
from datetime import datetime, date
from collections import defaultdict
import threading
from dataclasses import dataclass

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
