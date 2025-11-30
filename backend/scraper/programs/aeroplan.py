"""
Air Canada Aeroplan Scraper - Award availability search
"""
import re
import json
import asyncio
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from bs4 import BeautifulSoup

import httpx
from loguru import logger

from scraper.base import BaseScraper, FlightAvailability, CabinClass
from scraper.browser import BrowserManager


class AeroplanScraper(BaseScraper):
    """
    Scraper for Air Canada Aeroplan award availability.
    
    Aeroplan is excellent for Star Alliance redemptions and often has
    better availability than searching on United directly.
    """
    
    # Cabin class mapping
    CABIN_MAP = {
        CabinClass.ECONOMY: "economy",
        CabinClass.PREMIUM_ECONOMY: "premium-economy",
        CabinClass.BUSINESS: "business",
        CabinClass.FIRST: "first",
    }
    
    CABIN_REVERSE_MAP = {
        "eco": CabinClass.ECONOMY,
        "economy": CabinClass.ECONOMY,
        "ecoflex": CabinClass.ECONOMY,
        "pey": CabinClass.PREMIUM_ECONOMY,
        "premium economy": CabinClass.PREMIUM_ECONOMY,
        "premiumeconomy": CabinClass.PREMIUM_ECONOMY,
        "bus": CabinClass.BUSINESS,
        "business": CabinClass.BUSINESS,
        "signature": CabinClass.BUSINESS,
        "first": CabinClass.FIRST,
    }
    
    @property
    def program_name(self) -> str:
        return "aeroplan"
    
    @property
    def program_display_name(self) -> str:
        return "Air Canada Aeroplan"
    
    @property
    def base_url(self) -> str:
        return "https://www.aircanada.com"
    
    @property
    def aeroplan_url(self) -> str:
        return "https://www.aeroplan.com"
    
    @property
    def supported_airlines(self) -> List[str]:
        """Air Canada and Star Alliance partners"""
        return [
            "AC",  # Air Canada
            "UA",  # United
            "NH",  # ANA
            "LH",  # Lufthansa
            "SQ",  # Singapore Airlines
            "TK",  # Turkish Airlines
            "SK",  # SAS
            "OS",  # Austrian
            "LX",  # Swiss
            "ET",  # Ethiopian
            "TP",  # TAP Portugal
            "CA",  # Air China
            "OZ",  # Asiana
            "SA",  # South African Airways
            "BR",  # EVA Air
            "EY",  # Etihad (partner)
        ]
    
    async def search_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass] = None,
        passengers: int = 1
    ) -> List[FlightAvailability]:
        """
        Search Aeroplan for award availability.
        """
        logger.info(f"Searching Aeroplan: {origin} → {destination} on {departure_date}")
        
        await self._rate_limit_delay()
        
        try:
            # Try browser-based search (more reliable for Aeroplan)
            results = await self._search_via_browser(
                origin, destination, departure_date, cabin_class, passengers
            )
            return results
            
        except Exception as e:
            logger.error(f"Aeroplan search failed: {e}")
            return []
    
    async def _search_via_browser(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """
        Search using browser automation.
        Aeroplan requires browser rendering due to heavy JavaScript.
        """
        date_str = departure_date.strftime("%Y-%m-%d")
        cabin_param = self.CABIN_MAP.get(cabin_class, "economy") if cabin_class else ""
        
        # Aeroplan flight search URL structure
        search_url = (
            f"{self.aeroplan_url}/en/book/flights"
            f"?tripType=O"  # One-way
            f"&org0={origin.upper()}"
            f"&dest0={destination.upper()}"
            f"&departureDate0={date_str}"
            f"&lang=en-CA"
            f"&ADT={passengers}"
            f"&YTH=0&CHD=0&INF=0&INS=0"
            f"&marketCode=TNB"  # Award search
        )
        
        if cabin_param:
            search_url += f"&cabin={cabin_param}"
        
        browser = BrowserManager(
            proxy=self.get_proxy(),
            user_agent=self.get_user_agent()
        )
        
        try:
            html = await browser.fetch_page(
                search_url,
                wait_for_selector=".flight-list, .flight-results, [data-testid='flight-list']",
                wait_timeout=25
            )
            
            return self._parse_html_response(html, origin, destination, departure_date)
            
        except Exception as e:
            logger.error(f"Aeroplan browser scraping failed: {e}")
            return []
    
    def _parse_html_response(
        self,
        html: str,
        origin: str,
        destination: str,
        departure_date: date
    ) -> List[FlightAvailability]:
        """Parse Aeroplan HTML search results"""
        results = []
        
        try:
            soup = BeautifulSoup(html, "lxml")
            
            # Look for flight cards/rows
            # Note: Actual selectors depend on Aeroplan's current website structure
            flight_cards = soup.select(
                ".flight-row, .flight-card, "
                "[data-testid='flight-row'], "
                ".bound-inner, .flight-option"
            )
            
            for card in flight_cards:
                try:
                    flight = self._parse_flight_card(card, origin, destination, departure_date)
                    if flight:
                        results.append(flight)
                except Exception as e:
                    logger.warning(f"Error parsing Aeroplan flight card: {e}")
                    continue
            
            # Also try to extract from embedded JSON data
            json_results = self._extract_json_data(soup, origin, destination, departure_date)
            results.extend(json_results)
            
            # Deduplicate
            seen_ids = set()
            unique_results = []
            for r in results:
                if r.id not in seen_ids:
                    seen_ids.add(r.id)
                    unique_results.append(r)
            
        except Exception as e:
            logger.error(f"Error parsing Aeroplan HTML: {e}")
        
        logger.info(f"Parsed {len(results)} flights from Aeroplan")
        return results
    
    def _parse_flight_card(
        self,
        card,
        origin: str,
        destination: str,
        departure_date: date
    ) -> Optional[FlightAvailability]:
        """Parse a single flight card element"""
        try:
            # Flight number
            flight_elem = card.select_one(
                ".flight-number, [data-testid='flight-number'], .carrier-info"
            )
            flight_number = ""
            airline = "AC"
            
            if flight_elem:
                text = flight_elem.get_text(strip=True)
                # Extract carrier code and number (e.g., "AC 123" or "UA456")
                match = re.search(r"([A-Z]{2})\s*(\d+)", text)
                if match:
                    airline = match.group(1)
                    flight_number = f"{airline}{match.group(2)}"
                else:
                    flight_number = text
            
            # Departure/Arrival times
            time_elems = card.select(".time, .departure-time, .arrival-time, [data-testid='time']")
            dep_time = time_elems[0].get_text(strip=True) if len(time_elems) > 0 else ""
            arr_time = time_elems[1].get_text(strip=True) if len(time_elems) > 1 else ""
            
            # Duration
            duration_elem = card.select_one(".duration, [data-testid='duration'], .travel-time")
            duration = 0
            if duration_elem:
                duration = self._parse_duration(duration_elem.get_text(strip=True))
            
            # Points/Miles
            points_elem = card.select_one(
                ".points, .miles, [data-testid='points'], .aeroplan-points, .reward-points"
            )
            points = 0
            if points_elem:
                points_text = points_elem.get_text(strip=True)
                points = int(re.sub(r"[^\d]", "", points_text) or "0")
            
            # Cabin class
            cabin_elem = card.select_one(".cabin, [data-testid='cabin'], .fare-brand")
            cabin = CabinClass.ECONOMY
            if cabin_elem:
                cabin_text = cabin_elem.get_text(strip=True).lower()
                for key, value in self.CABIN_REVERSE_MAP.items():
                    if key in cabin_text:
                        cabin = value
                        break
            
            # Stops
            stops_elem = card.select_one(".stops, [data-testid='stops'], .connection-info")
            stops = 0
            if stops_elem:
                stops_text = stops_elem.get_text(strip=True).lower()
                if "nonstop" in stops_text or "direct" in stops_text:
                    stops = 0
                else:
                    stop_match = re.search(r"(\d+)", stops_text)
                    stops = int(stop_match.group(1)) if stop_match else 1
            
            # Taxes/Fees
            taxes_elem = card.select_one(".taxes, .fees, [data-testid='taxes']")
            taxes = 0.0
            if taxes_elem:
                taxes_text = taxes_elem.get_text(strip=True)
                taxes_match = re.search(r"[\d,.]+", taxes_text.replace(",", ""))
                taxes = float(taxes_match.group()) if taxes_match else 0.0
            
            # Only return if we have meaningful data
            if points > 0 or flight_number:
                return FlightAvailability(
                    id=self._generate_flight_id(flight_number, departure_date, cabin.value),
                    source_program=self.program_name,
                    origin=origin,
                    destination=destination,
                    airline=airline,
                    flight_number=flight_number,
                    departure_date=departure_date,
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration_minutes=duration,
                    cabin_class=cabin,
                    points_required=points,
                    taxes_fees=taxes,
                    seats_available=0,
                    stops=stops,
                    connection_airports=[],
                )
            
        except Exception as e:
            logger.warning(f"Failed to parse Aeroplan flight card: {e}")
        
        return None
    
    def _extract_json_data(
        self,
        soup,
        origin: str,
        destination: str,
        departure_date: date
    ) -> List[FlightAvailability]:
        """
        Extract flight data from embedded JSON in the page.
        Many modern SPAs include data in script tags.
        """
        results = []
        
        try:
            # Look for script tags with flight data
            script_tags = soup.find_all("script", type="application/json")
            script_tags.extend(soup.find_all("script", id=re.compile(r"__NEXT_DATA__|__NUXT__|initialState")))
            
            for script in script_tags:
                try:
                    text = script.string
                    if not text:
                        continue
                    
                    data = json.loads(text)
                    
                    # Look for flight arrays in common locations
                    flights_data = self._find_flights_in_json(data)
                    
                    for flight_data in flights_data:
                        flight = self._parse_json_flight(flight_data, origin, destination, departure_date)
                        if flight:
                            results.append(flight)
                            
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting JSON flight data: {e}")
                    continue
                    
        except Exception as e:
            logger.debug(f"Error in JSON extraction: {e}")
        
        return results
    
    def _find_flights_in_json(self, data: Any, depth: int = 0) -> List[Dict]:
        """Recursively find flight data in JSON structure"""
        if depth > 10:  # Prevent infinite recursion
            return []
        
        flights = []
        
        if isinstance(data, dict):
            # Check if this looks like flight data
            if any(key in data for key in ["flightNumber", "flight_number", "segments", "points", "miles"]):
                flights.append(data)
            
            # Check common keys for flight arrays
            for key in ["flights", "results", "options", "bounds", "journeys", "itineraries"]:
                if key in data:
                    flights.extend(self._find_flights_in_json(data[key], depth + 1))
            
            # Recurse into other dict values
            for value in data.values():
                flights.extend(self._find_flights_in_json(value, depth + 1))
                
        elif isinstance(data, list):
            for item in data:
                flights.extend(self._find_flights_in_json(item, depth + 1))
        
        return flights
    
    def _parse_json_flight(
        self,
        data: Dict,
        origin: str,
        destination: str,
        departure_date: date
    ) -> Optional[FlightAvailability]:
        """Parse flight from JSON data structure"""
        try:
            # Try various key names for flight number
            flight_number = (
                data.get("flightNumber") or 
                data.get("flight_number") or 
                data.get("number") or
                ""
            )
            
            # Try to get airline code
            airline = (
                data.get("carrier") or 
                data.get("airline") or 
                data.get("operatingCarrier") or
                "AC"
            )
            
            # Get points
            points = int(
                data.get("points") or 
                data.get("miles") or 
                data.get("aeroplanPoints") or
                data.get("cost", {}).get("points") or
                0
            )
            
            if not flight_number and not points:
                return None
            
            # Get cabin
            cabin_str = str(
                data.get("cabin") or 
                data.get("cabinClass") or 
                data.get("class") or
                "economy"
            ).lower()
            
            cabin = CabinClass.ECONOMY
            for key, value in self.CABIN_REVERSE_MAP.items():
                if key in cabin_str:
                    cabin = value
                    break
            
            return FlightAvailability(
                id=self._generate_flight_id(flight_number, departure_date, cabin.value),
                source_program=self.program_name,
                origin=origin,
                destination=destination,
                airline=airline,
                flight_number=flight_number,
                departure_date=departure_date,
                departure_time=data.get("departureTime", ""),
                arrival_time=data.get("arrivalTime", ""),
                duration_minutes=int(data.get("duration", 0)),
                cabin_class=cabin,
                points_required=points,
                taxes_fees=float(data.get("taxes", 0)),
                seats_available=int(data.get("seatsAvailable", 0)),
                stops=int(data.get("stops", 0)),
                connection_airports=data.get("connections", []),
                raw_data=data
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse JSON flight: {e}")
            return None
    
    def _parse_duration(self, duration_text: str) -> int:
        """Parse duration text to minutes"""
        try:
            hours = 0
            minutes = 0
            
            hour_match = re.search(r"(\d+)\s*h", duration_text, re.IGNORECASE)
            min_match = re.search(r"(\d+)\s*m", duration_text, re.IGNORECASE)
            
            if hour_match:
                hours = int(hour_match.group(1))
            if min_match:
                minutes = int(min_match.group(1))
            
            return hours * 60 + minutes
        except:
            return 0
    
    async def health_check(self) -> bool:
        """Check if Aeroplan website is accessible"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self.aeroplan_url,
                    headers=self.get_headers()
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Aeroplan health check failed: {e}")
            return False
