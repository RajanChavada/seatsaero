"""
Flight Data Normalizer - Standardize data from different sources
"""
from typing import List, Dict, Any, Optional
from datetime import date, datetime
import re

from loguru import logger

from scraper.base import FlightAvailability, CabinClass


# IATA airport code validation pattern
IATA_PATTERN = re.compile(r"^[A-Z]{3}$")

# Airline code pattern
AIRLINE_PATTERN = re.compile(r"^[A-Z0-9]{2}$")


class FlightNormalizer:
    """
    Normalizes and validates flight availability data from various sources.
    Ensures data consistency across different loyalty program scrapers.
    """
    
    # Common airline name to code mappings
    AIRLINE_NAMES = {
        "united": "UA",
        "united airlines": "UA",
        "air canada": "AC",
        "american": "AA",
        "american airlines": "AA",
        "delta": "DL",
        "delta air lines": "DL",
        "lufthansa": "LH",
        "british airways": "BA",
        "emirates": "EK",
        "singapore airlines": "SQ",
        "singapore": "SQ",
        "ana": "NH",
        "all nippon": "NH",
        "turkish": "TK",
        "turkish airlines": "TK",
        "swiss": "LX",
        "austrian": "OS",
        "tap": "TP",
        "tap portugal": "TP",
        "ethiopian": "ET",
        "qantas": "QF",
        "air china": "CA",
        "asiana": "OZ",
        "eva air": "BR",
        "eva": "BR",
    }
    
    # Cabin class aliases
    CABIN_ALIASES = {
        # Economy
        "y": CabinClass.ECONOMY,
        "economy": CabinClass.ECONOMY,
        "eco": CabinClass.ECONOMY,
        "coach": CabinClass.ECONOMY,
        "main cabin": CabinClass.ECONOMY,
        
        # Premium Economy
        "w": CabinClass.PREMIUM_ECONOMY,
        "premium economy": CabinClass.PREMIUM_ECONOMY,
        "premium eco": CabinClass.PREMIUM_ECONOMY,
        "premium": CabinClass.PREMIUM_ECONOMY,
        "economy plus": CabinClass.PREMIUM_ECONOMY,
        
        # Business
        "j": CabinClass.BUSINESS,
        "c": CabinClass.BUSINESS,
        "business": CabinClass.BUSINESS,
        "business class": CabinClass.BUSINESS,
        "polaris": CabinClass.BUSINESS,
        "signature": CabinClass.BUSINESS,
        "club": CabinClass.BUSINESS,
        
        # First
        "f": CabinClass.FIRST,
        "first": CabinClass.FIRST,
        "first class": CabinClass.FIRST,
        "global first": CabinClass.FIRST,
        "suites": CabinClass.FIRST,
    }
    
    @classmethod
    def normalize_airport_code(cls, code: str) -> Optional[str]:
        """
        Normalize and validate airport IATA code.
        
        Args:
            code: Airport code string
            
        Returns:
            Normalized 3-letter IATA code or None if invalid
        """
        if not code:
            return None
        
        code = code.strip().upper()
        
        if IATA_PATTERN.match(code):
            return code
        
        logger.warning(f"Invalid airport code: {code}")
        return None
    
    @classmethod
    def normalize_airline_code(cls, code_or_name: str) -> str:
        """
        Normalize airline code from code or name.
        
        Args:
            code_or_name: Airline code (e.g., "UA") or name (e.g., "United Airlines")
            
        Returns:
            2-character airline code
        """
        if not code_or_name:
            return "XX"  # Unknown
        
        value = code_or_name.strip()
        
        # Check if it's already a code
        if AIRLINE_PATTERN.match(value.upper()):
            return value.upper()
        
        # Try to find in name mappings
        normalized_name = value.lower()
        if normalized_name in cls.AIRLINE_NAMES:
            return cls.AIRLINE_NAMES[normalized_name]
        
        # Partial match
        for name, code in cls.AIRLINE_NAMES.items():
            if name in normalized_name or normalized_name in name:
                return code
        
        logger.warning(f"Unknown airline: {code_or_name}")
        return "XX"
    
    @classmethod
    def normalize_cabin_class(cls, cabin: str) -> CabinClass:
        """
        Normalize cabin class string to enum.
        
        Args:
            cabin: Cabin class string
            
        Returns:
            CabinClass enum value
        """
        if not cabin:
            return CabinClass.ECONOMY
        
        normalized = cabin.strip().lower()
        
        if normalized in cls.CABIN_ALIASES:
            return cls.CABIN_ALIASES[normalized]
        
        # Partial match
        for alias, cabin_class in cls.CABIN_ALIASES.items():
            if alias in normalized or normalized in alias:
                return cabin_class
        
        return CabinClass.ECONOMY
    
    @classmethod
    def normalize_points(cls, points: Any) -> int:
        """
        Normalize points value.
        
        Args:
            points: Points value (int, str, or float)
            
        Returns:
            Integer points value
        """
        if points is None:
            return 0
        
        if isinstance(points, int):
            return max(0, points)
        
        if isinstance(points, float):
            return max(0, int(points))
        
        if isinstance(points, str):
            # Remove commas, currency symbols, etc.
            cleaned = re.sub(r"[^\d.]", "", points)
            try:
                return max(0, int(float(cleaned)))
            except ValueError:
                return 0
        
        return 0
    
    @classmethod
    def normalize_time(cls, time_str: str) -> str:
        """
        Normalize time string to HH:MM format.
        
        Args:
            time_str: Time string in various formats
            
        Returns:
            Time in HH:MM format
        """
        if not time_str:
            return ""
        
        time_str = time_str.strip()
        
        # Already in HH:MM format
        if re.match(r"^\d{2}:\d{2}$", time_str):
            return time_str
        
        # 12-hour format (e.g., "3:30 PM")
        match = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?", time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            period = match.group(3)
            
            if period and period.upper() == "PM" and hour != 12:
                hour += 12
            elif period and period.upper() == "AM" and hour == 12:
                hour = 0
            
            return f"{hour:02d}:{minute:02d}"
        
        return time_str
    
    @classmethod
    def normalize_duration(cls, duration: Any) -> int:
        """
        Normalize flight duration to minutes.
        
        Args:
            duration: Duration as int (minutes), string ("5h 30m"), or dict
            
        Returns:
            Duration in minutes
        """
        if duration is None:
            return 0
        
        if isinstance(duration, int):
            return max(0, duration)
        
        if isinstance(duration, float):
            return max(0, int(duration))
        
        if isinstance(duration, str):
            hours = 0
            minutes = 0
            
            hour_match = re.search(r"(\d+)\s*[hH]", duration)
            min_match = re.search(r"(\d+)\s*[mM]", duration)
            
            if hour_match:
                hours = int(hour_match.group(1))
            if min_match:
                minutes = int(min_match.group(1))
            
            return hours * 60 + minutes
        
        return 0
    
    @classmethod
    def normalize_flight(cls, flight: FlightAvailability) -> FlightAvailability:
        """
        Normalize all fields of a FlightAvailability object.
        
        Args:
            flight: Raw FlightAvailability object
            
        Returns:
            Normalized FlightAvailability object
        """
        # Normalize airport codes
        origin = cls.normalize_airport_code(flight.origin) or flight.origin
        destination = cls.normalize_airport_code(flight.destination) or flight.destination
        
        # Normalize airline
        airline = cls.normalize_airline_code(flight.airline)
        
        # Normalize times
        dep_time = cls.normalize_time(flight.departure_time)
        arr_time = cls.normalize_time(flight.arrival_time)
        
        # Normalize points
        points = cls.normalize_points(flight.points_required)
        
        # Normalize duration
        duration = cls.normalize_duration(flight.duration_minutes)
        
        # Create new normalized flight
        return FlightAvailability(
            id=flight.id,
            source_program=flight.source_program,
            origin=origin,
            destination=destination,
            airline=airline,
            flight_number=flight.flight_number.upper(),
            departure_date=flight.departure_date,
            departure_time=dep_time,
            arrival_time=arr_time,
            duration_minutes=duration,
            cabin_class=flight.cabin_class,
            points_required=points,
            taxes_fees=max(0.0, flight.taxes_fees),
            seats_available=max(0, flight.seats_available),
            stops=max(0, flight.stops),
            connection_airports=[c.upper() for c in flight.connection_airports],
            scraped_at=flight.scraped_at,
            expires_at=flight.expires_at,
            raw_data=flight.raw_data,
        )
    
    @classmethod
    def normalize_flights(cls, flights: List[FlightAvailability]) -> List[FlightAvailability]:
        """
        Normalize a list of flights.
        
        Args:
            flights: List of raw FlightAvailability objects
            
        Returns:
            List of normalized FlightAvailability objects
        """
        normalized = []
        
        for flight in flights:
            try:
                normalized.append(cls.normalize_flight(flight))
            except Exception as e:
                logger.warning(f"Failed to normalize flight: {e}")
                continue
        
        return normalized
    
    @classmethod
    def deduplicate(cls, flights: List[FlightAvailability]) -> List[FlightAvailability]:
        """
        Remove duplicate flights based on ID.
        Keeps the most recently scraped version.
        
        Args:
            flights: List of flights (possibly with duplicates)
            
        Returns:
            Deduplicated list
        """
        seen: Dict[str, FlightAvailability] = {}
        
        for flight in flights:
            existing = seen.get(flight.id)
            if not existing or flight.scraped_at > existing.scraped_at:
                seen[flight.id] = flight
        
        return list(seen.values())
    
    @classmethod
    def filter_valid(cls, flights: List[FlightAvailability]) -> List[FlightAvailability]:
        """
        Filter out invalid or incomplete flight records.
        
        Args:
            flights: List of flights to filter
            
        Returns:
            List of valid flights
        """
        valid = []
        
        for flight in flights:
            # Must have origin and destination
            if not flight.origin or not flight.destination:
                continue
            
            # Must have points > 0
            if flight.points_required <= 0:
                continue
            
            # Must have departure date
            if not flight.departure_date:
                continue
            
            # Must not be expired
            if flight.is_expired():
                continue
            
            valid.append(flight)
        
        return valid
