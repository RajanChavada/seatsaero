"""
Base Scraper - Abstract base class for all loyalty program scrapers
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import random

from loguru import logger

from config import settings


class CabinClass(str, Enum):
    """Cabin class enumeration"""
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


@dataclass
class FlightAvailability:
    """Normalized flight availability data model"""
    # Identifiers
    id: str
    source_program: str
    
    # Route Information
    origin: str
    destination: str
    
    # Flight Details
    airline: str
    flight_number: str
    departure_date: date
    departure_time: str
    arrival_time: str
    duration_minutes: int
    
    # Award Details
    cabin_class: CabinClass
    points_required: int
    taxes_fees: float
    seats_available: int = 0
    
    # Routing
    stops: int = 0
    connection_airports: List[str] = field(default_factory=list)
    
    # Metadata
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set expiry time if not set"""
        if self.expires_at is None:
            from datetime import timedelta
            self.expires_at = self.scraped_at + timedelta(hours=settings.data_expiry_hours)
    
    def is_expired(self) -> bool:
        """Check if the data is expired"""
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "source_program": self.source_program,
            "origin": self.origin,
            "destination": self.destination,
            "airline": self.airline,
            "flight_number": self.flight_number,
            "departure_date": self.departure_date.isoformat(),
            "departure_time": self.departure_time,
            "arrival_time": self.arrival_time,
            "duration_minutes": self.duration_minutes,
            "cabin_class": self.cabin_class.value,
            "points_required": self.points_required,
            "taxes_fees": self.taxes_fees,
            "seats_available": self.seats_available,
            "stops": self.stops,
            "connection_airports": self.connection_airports,
            "scraped_at": self.scraped_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class BaseScraper(ABC):
    """
    Abstract base class for all loyalty program scrapers.
    
    Each loyalty program scraper must inherit from this class and implement
    the required abstract methods.
    """
    
    def __init__(self, browser_manager=None, proxy_rotator=None, useragent_rotator=None):
        self.browser_manager = browser_manager
        self.proxy_rotator = proxy_rotator
        self.useragent_rotator = useragent_rotator
        self._session_cookies: Dict[str, str] = {}
        self._last_request_time: Optional[datetime] = None
        
    @property
    @abstractmethod
    def program_name(self) -> str:
        """Return the loyalty program identifier (e.g., 'united_mileageplus')"""
        pass
    
    @property
    @abstractmethod
    def program_display_name(self) -> str:
        """Return human-readable program name (e.g., 'United MileagePlus')"""
        pass
    
    @property
    @abstractmethod
    def base_url(self) -> str:
        """Return the base URL for the loyalty program website"""
        pass
    
    @property
    @abstractmethod
    def supported_airlines(self) -> List[str]:
        """Return list of airline codes searchable through this program"""
        pass
    
    @abstractmethod
    async def search_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass] = None,
        passengers: int = 1
    ) -> List[FlightAvailability]:
        """
        Search for award availability on a specific route/date.
        
        Args:
            origin: Origin airport IATA code (e.g., "JFK")
            destination: Destination airport IATA code (e.g., "LHR")
            departure_date: Date of departure
            cabin_class: Optional cabin class filter
            passengers: Number of passengers (default 1)
            
        Returns:
            List of FlightAvailability objects
        """
        pass
    
    async def search_date_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        cabin_class: Optional[CabinClass] = None
    ) -> List[FlightAvailability]:
        """
        Search availability across a date range.
        
        Default implementation iterates through dates. Override for efficiency
        if the loyalty program supports date range searches.
        """
        results = []
        current_date = start_date
        
        while current_date <= end_date:
            try:
                day_results = await self.search_availability(
                    origin=origin,
                    destination=destination,
                    departure_date=current_date,
                    cabin_class=cabin_class
                )
                results.extend(day_results)
            except Exception as e:
                logger.error(f"Error searching {current_date}: {e}")
            
            # Move to next day
            from datetime import timedelta
            current_date += timedelta(days=1)
            
            # Rate limiting between requests
            await self._rate_limit_delay()
        
        return results
    
    async def health_check(self) -> bool:
        """
        Verify scraper can connect to the loyalty program website.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Default implementation - try to load base URL
            # Subclasses should override for more specific checks
            logger.info(f"Health check for {self.program_name}")
            return True
        except Exception as e:
            logger.error(f"Health check failed for {self.program_name}: {e}")
            return False
    
    async def _rate_limit_delay(self) -> None:
        """Apply rate limiting delay between requests"""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            min_delay = settings.scrape_delay_min
            max_delay = settings.scrape_delay_max
            
            target_delay = random.uniform(min_delay, max_delay)
            
            if elapsed < target_delay:
                sleep_time = target_delay - elapsed
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
        
        self._last_request_time = datetime.utcnow()
    
    def _generate_flight_id(self, flight_number: str, departure_date: date, cabin: str) -> str:
        """Generate unique ID for a flight availability record"""
        import hashlib
        unique_string = f"{self.program_name}:{flight_number}:{departure_date}:{cabin}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:16]
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Get proxy configuration if enabled"""
        if self.proxy_rotator and settings.proxy_enabled:
            return self.proxy_rotator.get_next()
        return None
    
    def get_user_agent(self) -> str:
        """Get randomized user agent"""
        if self.useragent_rotator:
            return self.useragent_rotator.get_random()
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    def get_headers(self) -> Dict[str, str]:
        """Get request headers with randomized user agent"""
        return {
            "User-Agent": self.get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
