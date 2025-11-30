"""
Demo Scraper - Returns mock data for testing the application
"""
import random
import hashlib
from datetime import date, datetime, timedelta
from typing import List, Optional
from loguru import logger

from scraper.base import BaseScraper, FlightAvailability, CabinClass


class DemoScraper(BaseScraper):
    """
    Demo scraper that returns realistic mock data.
    Used for testing the application end-to-end.
    """
    
    @property
    def program_name(self) -> str:
        return "demo"
    
    @property
    def program_display_name(self) -> str:
        return "Demo Airlines (Test Mode)"
    
    @property
    def base_url(self) -> str:
        return "http://localhost"
    
    @property
    def supported_airlines(self) -> List[str]:
        return ["UA", "AC", "LH", "SQ", "NH", "EK", "QR", "BA", "DL", "AA"]
    
    # Sample airlines and their codes
    AIRLINES = [
        ("United Airlines", "UA"),
        ("Air Canada", "AC"),
        ("Lufthansa", "LH"),
        ("Singapore Airlines", "SQ"),
        ("ANA", "NH"),
        ("Emirates", "EK"),
        ("Qatar Airways", "QR"),
        ("British Airways", "BA"),
        ("Delta Air Lines", "DL"),
        ("American Airlines", "AA"),
    ]
    
    # Sample aircraft types
    AIRCRAFT = [
        "Boeing 777-300ER",
        "Boeing 787-9 Dreamliner",
        "Airbus A350-900",
        "Airbus A380-800",
        "Boeing 777-200LR",
        "Airbus A330-300",
        "Boeing 787-10",
        "Airbus A321neo",
    ]
    
    # Realistic mileage costs by cabin class
    MILEAGE_RANGES = {
        CabinClass.ECONOMY: (15000, 45000),
        CabinClass.PREMIUM_ECONOMY: (35000, 75000),
        CabinClass.BUSINESS: (60000, 150000),
        CabinClass.FIRST: (100000, 250000),
    }
    
    # Tax ranges
    TAX_RANGES = {
        CabinClass.ECONOMY: (50, 200),
        CabinClass.PREMIUM_ECONOMY: (100, 350),
        CabinClass.BUSINESS: (200, 800),
        CabinClass.FIRST: (300, 1200),
    }
    
    async def search_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date] = None,
        cabin_class: Optional[CabinClass] = None,
        passengers: int = 1
    ) -> List[FlightAvailability]:
        """Generate mock flight availability data"""
        
        logger.info(f"Demo scraper: {origin} → {destination} on {departure_date}")
        
        results = []
        
        # Generate 5-15 random flights
        num_flights = random.randint(5, 15)
        
        # Determine which cabin classes to generate
        if cabin_class:
            cabins_to_generate = [cabin_class]
        else:
            cabins_to_generate = list(CabinClass)
        
        for _ in range(num_flights):
            cabin = random.choice(cabins_to_generate)
            airline_name, airline_code = random.choice(self.AIRLINES)
            
            # Generate flight number
            flight_number = f"{airline_code}{random.randint(100, 9999)}"
            
            # Generate departure time
            hour = random.randint(6, 22)
            minute = random.choice([0, 15, 30, 45])
            dep_time = datetime.combine(departure_date, datetime.min.time()).replace(
                hour=hour, minute=minute
            )
            
            # Generate flight duration (2-16 hours depending on route)
            duration_hours = random.randint(2, 16)
            duration_minutes = random.choice([0, 15, 30, 45])
            arr_time = dep_time + timedelta(hours=duration_hours, minutes=duration_minutes)
            
            # Generate mileage cost
            min_miles, max_miles = self.MILEAGE_RANGES[cabin]
            miles = random.randint(min_miles // 1000, max_miles // 1000) * 1000
            
            # Generate taxes
            min_tax, max_tax = self.TAX_RANGES[cabin]
            taxes = round(random.uniform(min_tax, max_tax), 2)
            
            # Generate seats available (1-9, weighted toward lower numbers)
            seats = random.choices(
                [1, 2, 3, 4, 5, 6, 7, 8, 9],
                weights=[25, 20, 15, 12, 10, 8, 5, 3, 2]
            )[0]
            
            # Generate stops (0-2, weighted toward direct)
            stops = random.choices([0, 1, 2], weights=[50, 35, 15])[0]
            
            # Generate unique ID
            flight_id = hashlib.md5(
                f"{origin}{destination}{departure_date}{flight_number}{cabin.value}{random.random()}".encode()
            ).hexdigest()[:16]
            
            # Create flight availability matching the dataclass schema
            flight = FlightAvailability(
                id=flight_id,
                source_program=self.program_name,
                origin=origin.upper(),
                destination=destination.upper(),
                airline=airline_name,
                flight_number=flight_number,
                departure_date=departure_date,
                departure_time=dep_time.strftime("%H:%M"),
                arrival_time=arr_time.strftime("%H:%M"),
                duration_minutes=duration_hours * 60 + duration_minutes,
                cabin_class=cabin,
                points_required=miles,
                taxes_fees=taxes,
                seats_available=seats,
                stops=stops,
            )
            
            results.append(flight)
        
        logger.info(f"Demo scraper generated {len(results)} flights")
        return results
    
    async def check_health(self) -> bool:
        """Demo scraper is always healthy"""
        return True
