"""
Google Flights Scraper - Cash fare aggregator

Google Flights provides aggregated flight prices from multiple airlines.
This scraper extracts cash fares which can be used for:
1. Price comparison
2. Fallback when direct airline scraping fails
3. Discovering available routes and schedules

Note: Google Flights shows cash prices, not points/miles.
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any
import hashlib
import re
import asyncio

from loguru import logger

from scraper.base import (
    BaseScraper, 
    FlightAvailability, 
    CabinClass,
    ScrapeResult,
    BlockedError,
)


class GoogleFlightsScraper(BaseScraper):
    """
    Scraper for Google Flights.
    
    Extracts cash fares from multiple airlines.
    Works well as a fallback or for price comparison.
    """
    
    @property
    def program_name(self) -> str:
        return "google_flights"
    
    @property
    def program_display_name(self) -> str:
        return "Google Flights"
    
    @property
    def base_url(self) -> str:
        return "https://www.google.com/travel/flights"
    
    @property
    def supported_airlines(self) -> List[str]:
        # Google Flights shows many airlines
        return ["*"]  # All airlines
    
    async def search_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass] = None,
        passengers: int = 1
    ) -> List[FlightAvailability]:
        """
        Search for flights on Google Flights.
        
        Returns cash fares from multiple airlines.
        """
        logger.info(f"Searching Google Flights: {origin} → {destination} on {departure_date}")
        
        try:
            results = await self._search_via_playwright(
                origin, destination, departure_date, cabin_class, passengers
            )
            return results
        except Exception as e:
            logger.error(f"Google Flights search failed: {e}")
            return []
    
    async def _search_via_playwright(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """Search using Playwright with stealth browser"""
        from ..playwright_browser import AsyncPlaywrightStealthBrowser
        
        async with AsyncPlaywrightStealthBrowser() as browser:
            page = await browser.new_page()
            
            # Build search URL
            search_url = self._build_search_url(origin, destination, departure_date, cabin_class)
            logger.debug(f"Google Flights URL: {search_url}")
            
            await page.goto(search_url, wait_until='networkidle', timeout=30000)
            
            # Wait for results to load
            await asyncio.sleep(5)
            
            # Get page content
            text = await page.evaluate('document.body.innerText')
            
            # Check for blocks
            if 'unusual traffic' in text.lower() or 'access denied' in text.lower():
                raise BlockedError("Blocked by Google")
            
            # Check for browser upgrade message
            if 'time for an upgrade' in text.lower():
                raise BlockedError("Google detected outdated browser")
            
            # Parse results
            results = self._parse_results(text, origin, destination, departure_date)
            
            logger.info(f"Found {len(results)} flights on Google Flights")
            return results
    
    def _build_search_url(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass] = None
    ) -> str:
        """Build Google Flights search URL"""
        
        date_str = departure_date.strftime("%Y-%m-%d")
        
        # Cabin class mapping
        cabin_param = "1"  # Economy
        if cabin_class == CabinClass.PREMIUM_ECONOMY:
            cabin_param = "2"
        elif cabin_class == CabinClass.BUSINESS:
            cabin_param = "3"
        elif cabin_class == CabinClass.FIRST:
            cabin_param = "4"
        
        # Simple URL format
        url = (
            f"https://www.google.com/travel/flights/search"
            f"?tfs=CBwQAhoeEgp7ZGVwYXJ0dXJlfWoHCAESA3tvcn1yBwgBEgN7ZHN9"
            f"&hl=en&gl=us&curr=USD"
        )
        
        # Alternative simpler approach - use the explore page with params
        url = (
            f"https://www.google.com/travel/flights?q=Flights%20to%20{destination}%20from%20{origin}%20on%20{date_str}"
            f"&curr=USD&hl=en"
        )
        
        return url
    
    def _parse_results(
        self,
        text: str,
        origin: str,
        destination: str,
        departure_date: date
    ) -> List[FlightAvailability]:
        """Parse Google Flights text results"""
        flights = []
        
        # Split into lines
        lines = text.split('\n')
        
        # Clean up lines - remove empty and whitespace-only
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        
        i = 0
        while i < len(cleaned_lines):
            line = cleaned_lines[i]
            
            # Look for departure time pattern (e.g., "6:28 AM")
            dep_time_match = re.match(r'^(\d{1,2}:\d{2}\s*(?:AM|PM))$', line, re.I)
            
            if dep_time_match:
                # Found a departure time, now look for arrival time
                # Format is: "6:28 AM" then " – " then "3:00 PM"
                if i + 2 < len(cleaned_lines):
                    # Check if next line is separator
                    if cleaned_lines[i + 1] in ['–', '-', '—']:
                        # Check for arrival time
                        arr_time_match = re.match(r'^(\d{1,2}:\d{2}\s*(?:AM|PM))(\+\d)?$', cleaned_lines[i + 2], re.I)
                        if arr_time_match:
                            # Found a flight! Now parse the following lines for details
                            flight_data = {
                                'departure_time': dep_time_match.group(1),
                                'arrival_time': arr_time_match.group(1),
                            }
                            
                            # Look at next 10 lines for airline, duration, stops, price
                            for j in range(i + 3, min(i + 15, len(cleaned_lines))):
                                detail_line = cleaned_lines[j]
                                
                                # Stop if we hit another flight (another time)
                                if re.match(r'^(\d{1,2}:\d{2}\s*(?:AM|PM))$', detail_line, re.I):
                                    break
                                
                                # Airline detection
                                if not flight_data.get('airline'):
                                    airlines = ['United', 'Delta', 'American', 'JetBlue', 'Alaska', 'Southwest', 
                                               'Spirit', 'Frontier', 'Hawaiian', 'Air Canada', 'British Airways',
                                               'Lufthansa', 'Virgin Atlantic', 'Emirates', 'Qatar', 'Singapore',
                                               'AlaskaHawaiian', 'Multiple airlines']
                                    for airline in airlines:
                                        if airline.lower() in detail_line.lower():
                                            flight_data['airline'] = airline.replace('AlaskaHawaiian', 'Alaska')
                                            break
                                
                                # Duration (e.g., "5 hr 32 min")
                                duration_match = re.search(r'(\d+)\s*hr\s*(\d+)?\s*min', detail_line, re.I)
                                if duration_match and not flight_data.get('duration'):
                                    hours = int(duration_match.group(1))
                                    mins = int(duration_match.group(2) or 0)
                                    flight_data['duration'] = hours * 60 + mins
                                
                                # Route (e.g., "SFO–JFK")
                                route_match = re.search(r'([A-Z]{3})[–-]([A-Z]{3})', detail_line)
                                if route_match:
                                    flight_data['route'] = f"{route_match.group(1)}-{route_match.group(2)}"
                                
                                # Stops
                                if 'nonstop' in detail_line.lower():
                                    flight_data['stops'] = 0
                                elif '1 stop' in detail_line.lower():
                                    flight_data['stops'] = 1
                                elif '2 stop' in detail_line.lower():
                                    flight_data['stops'] = 2
                                
                                # Price (e.g., "$420")
                                price_match = re.match(r'^\$(\d{1,3}(?:,\d{3})*)$', detail_line)
                                if price_match:
                                    flight_data['price'] = float(price_match.group(1).replace(',', ''))
                            
                            # If we have the essential data, create the flight
                            if flight_data.get('price'):
                                flight = self._create_flight(flight_data, origin, destination, departure_date)
                                if flight:
                                    flights.append(flight)
                            
                            i += 3  # Skip the time lines we processed
                            continue
            
            i += 1
        
        return flights
    
    def _create_flight(
        self,
        data: Dict[str, Any],
        origin: str,
        destination: str,
        departure_date: date
    ) -> Optional[FlightAvailability]:
        """Create FlightAvailability from parsed data"""
        
        try:
            # Parse times
            dep_time = self._parse_time(data.get('departure_time', ''))
            arr_time = self._parse_time(data.get('arrival_time', ''))
            
            # Get airline code
            airline = data.get('airline', 'Unknown')
            airline_code = self._get_airline_code(airline)
            
            # Generate ID
            flight_id = hashlib.md5(
                f"google:{origin}:{destination}:{departure_date}:{dep_time}:{airline}".encode()
            ).hexdigest()[:12]
            
            return FlightAvailability(
                id=flight_id,
                source_program=self.program_name,
                origin=origin,
                destination=destination,
                airline=airline_code,
                flight_number=f"{airline_code}???",  # Google doesn't always show flight numbers
                departure_date=departure_date,
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=data.get('duration', 0),
                cabin_class=CabinClass.ECONOMY,
                points_required=0,  # Google shows cash only
                cash_price=data.get('price', 0),
                taxes_fees=0,
                seats_available=0,
                stops=data.get('stops', 0),
                connection_airports=[],
                scraped_at=datetime.utcnow(),
                raw_data={
                    'source': 'google_flights',
                    'airline_name': airline,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to create flight: {e}")
            return None
    
    def _parse_time(self, time_str: str) -> str:
        """Parse time string to HH:MM format"""
        if not time_str:
            return "00:00"
        
        match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)?', time_str, re.I)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            period = match.group(3)
            
            if period:
                if period.upper() == 'PM' and hour != 12:
                    hour += 12
                elif period.upper() == 'AM' and hour == 12:
                    hour = 0
            
            return f"{hour:02d}:{minute:02d}"
        
        return "00:00"
    
    def _get_airline_code(self, airline_name: str) -> str:
        """Map airline name to IATA code"""
        codes = {
            'united': 'UA',
            'delta': 'DL',
            'american': 'AA',
            'jetblue': 'B6',
            'alaska': 'AS',
            'southwest': 'WN',
            'spirit': 'NK',
            'frontier': 'F9',
            'hawaiian': 'HA',
            'air canada': 'AC',
            'british airways': 'BA',
            'lufthansa': 'LH',
            'virgin': 'VS',
            'emirates': 'EK',
            'qatar': 'QR',
            'singapore': 'SQ',
        }
        
        name_lower = airline_name.lower()
        for name, code in codes.items():
            if name in name_lower:
                return code
        
        return airline_name[:2].upper()


# Test function
async def test_google_flights():
    """Test the Google Flights scraper"""
    scraper = GoogleFlightsScraper()
    
    results = await scraper.search_availability(
        origin="SFO",
        destination="JFK",
        departure_date=date(2025, 12, 15)
    )
    
    print(f"\n✅ Found {len(results)} flights!")
    for flight in results[:5]:
        print(f"\n{flight.airline} - {flight.departure_time} → {flight.arrival_time}")
        print(f"  Duration: {flight.duration_minutes} min, Stops: {flight.stops}")
        print(f"  Price: ${flight.cash_price:.2f}")


if __name__ == "__main__":
    asyncio.run(test_google_flights())
