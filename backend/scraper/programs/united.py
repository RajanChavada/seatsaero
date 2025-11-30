"""
United MileagePlus Scraper - Award availability search for United Airlines
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


class UnitedMileagePlusScraper(BaseScraper):
    """
    Scraper for United MileagePlus award availability.
    
    United's award search is available at:
    https://www.united.com/en/us/book-flight/find-flights
    
    The search uses an API endpoint that returns JSON data.
    """
    
    # Cabin class mapping for United
    CABIN_MAP = {
        CabinClass.ECONOMY: "ECONOMY",
        CabinClass.PREMIUM_ECONOMY: "PREMIUM_ECONOMY", 
        CabinClass.BUSINESS: "BUSINESS",
        CabinClass.FIRST: "FIRST",
    }
    
    # Reverse mapping
    CABIN_REVERSE_MAP = {
        "economy": CabinClass.ECONOMY,
        "econ": CabinClass.ECONOMY,
        "premium economy": CabinClass.PREMIUM_ECONOMY,
        "premium": CabinClass.PREMIUM_ECONOMY,
        "business": CabinClass.BUSINESS,
        "polaris": CabinClass.BUSINESS,
        "first": CabinClass.FIRST,
        "global first": CabinClass.FIRST,
    }
    
    @property
    def program_name(self) -> str:
        return "united_mileageplus"
    
    @property
    def program_display_name(self) -> str:
        return "United MileagePlus"
    
    @property
    def base_url(self) -> str:
        return "https://www.united.com"
    
    @property
    def supported_airlines(self) -> List[str]:
        """United and Star Alliance partners"""
        return [
            "UA",  # United
            "AC",  # Air Canada
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
        Search United MileagePlus for award availability.
        """
        logger.info(f"Searching United: {origin} → {destination} on {departure_date}")
        
        await self._rate_limit_delay()
        
        try:
            # Method 1: Try direct API call (faster but may get blocked)
            results = await self._search_via_api(
                origin, destination, departure_date, cabin_class, passengers
            )
            
            if results:
                return results
            
            # Method 2: Fallback to browser scraping
            logger.info("API method failed, falling back to browser scraping")
            return await self._search_via_browser(
                origin, destination, departure_date, cabin_class, passengers
            )
            
        except Exception as e:
            logger.error(f"United search failed: {e}")
            return []
    
    async def _search_via_api(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """
        Search using United's internal API endpoint.
        This is faster but may be more likely to get blocked.
        """
        search_url = f"{self.base_url}/api/flight/FetchFlights"
        
        # Format date as United expects
        date_str = departure_date.strftime("%Y-%m-%d")
        
        # Build request payload
        payload = {
            "Origin": origin.upper(),
            "Destination": destination.upper(),
            "DepartDate": date_str,
            "ReturnDate": "",
            "Travelers": {
                "Adult": passengers,
                "Child": 0,
                "Infant": 0,
                "InfantOnLap": 0
            },
            "TripType": "OneWay",
            "AwardTravel": True,
            "CabinPreference": self.CABIN_MAP.get(cabin_class, ""),
            "NonStop": False,
            "MaxConnections": 2,
            "SearchType": "Award",
        }
        
        headers = self.get_headers()
        headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/en/us/book-flight/find-flights",
        })
        
        proxy = self.get_proxy()
        
        try:
            # Build client kwargs - httpx uses 'proxy' (singular) not 'proxies'
            client_kwargs = {
                "timeout": 30,
                "follow_redirects": True,
                "verify": False,  # Skip SSL verification for now
            }
            if proxy:
                client_kwargs["proxy"] = proxy
            
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.post(
                    search_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_api_response(data, origin, destination, departure_date)
                else:
                    logger.warning(f"United API returned {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"United API request failed: {e}")
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
        Search using browser automation (Selenium).
        More reliable but slower.
        """
        # Build search URL
        date_str = departure_date.strftime("%Y-%m-%d")
        cabin_param = self.CABIN_MAP.get(cabin_class, "ECONOMY")
        
        search_url = (
            f"{self.base_url}/ual/en/us/flight-search/book-a-flight/results/awd"
            f"?f={origin}&t={destination}&d={date_str}&tt=1&at=1&sc=7"
            f"&px={passengers}&taxng=1&newHP=True&clm=7&st=bestmatches"
        )
        
        browser = BrowserManager(
            proxy=self.get_proxy(),
            user_agent=self.get_user_agent()
        )
        
        try:
            html = await browser.fetch_page(
                search_url,
                wait_for_selector=".flight-result-list, .app-components-Shopping-FlightResultsList-styles__flightResultsList",
                wait_timeout=20
            )
            
            return self._parse_html_response(html, origin, destination, departure_date)
            
        except Exception as e:
            logger.error(f"United browser scraping failed: {e}")
            return []
    
    def _parse_api_response(
        self,
        data: Dict[str, Any],
        origin: str,
        destination: str,
        departure_date: date
    ) -> List[FlightAvailability]:
        """Parse United API JSON response"""
        results = []
        
        try:
            flights = data.get("data", {}).get("Trips", [])
            
            for trip in flights:
                for product in trip.get("Products", []):
                    # Skip non-award products
                    if not product.get("IsAward"):
                        continue
                    
                    # Extract flight info
                    segments = product.get("Segments", [])
                    if not segments:
                        continue
                    
                    first_segment = segments[0]
                    last_segment = segments[-1]
                    
                    # Parse cabin class
                    cabin_str = product.get("CabinType", "economy").lower()
                    cabin = self.CABIN_REVERSE_MAP.get(cabin_str, CabinClass.ECONOMY)
                    
                    # Calculate total duration
                    duration = product.get("TotalTravelMinutes", 0)
                    
                    # Build connection airports
                    connections = []
                    if len(segments) > 1:
                        connections = [seg.get("Destination") for seg in segments[:-1]]
                    
                    flight = FlightAvailability(
                        id=self._generate_flight_id(
                            first_segment.get("FlightNumber", ""),
                            departure_date,
                            cabin.value
                        ),
                        source_program=self.program_name,
                        origin=origin,
                        destination=destination,
                        airline=first_segment.get("OperatingCarrier", "UA"),
                        flight_number=first_segment.get("FlightNumber", ""),
                        departure_date=departure_date,
                        departure_time=first_segment.get("DepartureTime", ""),
                        arrival_time=last_segment.get("ArrivalTime", ""),
                        duration_minutes=duration,
                        cabin_class=cabin,
                        points_required=int(product.get("Miles", 0)),
                        taxes_fees=float(product.get("TaxesAndFees", {}).get("Amount", 0)),
                        seats_available=int(product.get("SeatsRemaining", 0)),
                        stops=len(segments) - 1,
                        connection_airports=connections,
                        raw_data=product
                    )
                    results.append(flight)
                    
        except Exception as e:
            logger.error(f"Error parsing United API response: {e}")
        
        logger.info(f"Found {len(results)} United award flights")
        return results
    
    def _parse_html_response(
        self,
        html: str,
        origin: str,
        destination: str,
        departure_date: date
    ) -> List[FlightAvailability]:
        """Parse United HTML search results page"""
        results = []
        
        try:
            soup = BeautifulSoup(html, "lxml")
            
            # Find flight result cards
            flight_cards = soup.select(
                ".flight-result-list .flight-card, "
                "[data-testid='flight-card'], "
                ".app-components-Shopping-FlightCard-styles__flightCard"
            )
            
            for card in flight_cards:
                try:
                    # Extract flight details
                    # Note: Selectors need to be updated based on current United website
                    
                    # Flight number
                    flight_num_elem = card.select_one(
                        ".flight-number, [data-testid='flight-number']"
                    )
                    flight_number = flight_num_elem.get_text(strip=True) if flight_num_elem else "Unknown"
                    
                    # Times
                    time_elems = card.select(".departure-time, .arrival-time")
                    dep_time = time_elems[0].get_text(strip=True) if len(time_elems) > 0 else ""
                    arr_time = time_elems[1].get_text(strip=True) if len(time_elems) > 1 else ""
                    
                    # Duration
                    duration_elem = card.select_one(".duration, [data-testid='duration']")
                    duration_text = duration_elem.get_text(strip=True) if duration_elem else "0h 0m"
                    duration = self._parse_duration(duration_text)
                    
                    # Miles required
                    miles_elem = card.select_one(".miles-value, [data-testid='miles']")
                    miles_text = miles_elem.get_text(strip=True) if miles_elem else "0"
                    miles = int(re.sub(r"[^\d]", "", miles_text) or "0")
                    
                    # Cabin class
                    cabin_elem = card.select_one(".cabin-type, [data-testid='cabin']")
                    cabin_text = cabin_elem.get_text(strip=True).lower() if cabin_elem else "economy"
                    cabin = self.CABIN_REVERSE_MAP.get(cabin_text, CabinClass.ECONOMY)
                    
                    # Stops
                    stops_elem = card.select_one(".stops, [data-testid='stops']")
                    stops_text = stops_elem.get_text(strip=True).lower() if stops_elem else "nonstop"
                    stops = 0 if "nonstop" in stops_text or "direct" in stops_text else int(re.sub(r"[^\d]", "", stops_text) or "1")
                    
                    if miles > 0:  # Only add if we found valid mileage data
                        flight = FlightAvailability(
                            id=self._generate_flight_id(flight_number, departure_date, cabin.value),
                            source_program=self.program_name,
                            origin=origin,
                            destination=destination,
                            airline="UA",
                            flight_number=flight_number,
                            departure_date=departure_date,
                            departure_time=dep_time,
                            arrival_time=arr_time,
                            duration_minutes=duration,
                            cabin_class=cabin,
                            points_required=miles,
                            taxes_fees=0.0,  # Would need additional parsing
                            seats_available=0,
                            stops=stops,
                            connection_airports=[],
                        )
                        results.append(flight)
                        
                except Exception as e:
                    logger.warning(f"Error parsing flight card: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing United HTML: {e}")
        
        logger.info(f"Parsed {len(results)} flights from United HTML")
        return results
    
    def _parse_duration(self, duration_text: str) -> int:
        """Parse duration text like '5h 30m' to minutes"""
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
        """Check if United website is accessible"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/en/us",
                    headers=self.get_headers()
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"United health check failed: {e}")
            return False
