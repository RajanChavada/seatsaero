"""
Lufthansa Miles & More Scraper - Award Flight Availability

Primary program for European routes, especially Germany.
Star Alliance member - can show partner awards.
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Tuple
import hashlib
import re
import asyncio
import time
import json

from bs4 import BeautifulSoup
from loguru import logger

from scraper.base import (
    BaseScraper, 
    FlightAvailability, 
    CabinClass,
    ScrapeResult,
    CaptchaError,
    BlockedError,
)
from scraper.browser import create_browser_manager, BrowserManager
from scraper.proxy import get_proxy_pool
from config import settings

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class LufthansaMilesMoreScraper(BaseScraper):
    """
    Scraper for Lufthansa Miles & More award availability.
    
    Features:
    - API-first approach with browser fallback
    - Star Alliance partner availability
    - Business and First class sweet spots
    - European hub coverage (FRA, MUC)
    """
    
    @property
    def program_name(self) -> str:
        return "lufthansa_milesmore"
    
    @property
    def program_display_name(self) -> str:
        return "Lufthansa Miles & More"
    
    @property
    def base_url(self) -> str:
        return "https://www.lufthansa.com"
    
    @property
    def mileage_bargains_url(self) -> str:
        return "https://www.miles-and-more.com"
    
    @property
    def supported_airlines(self) -> List[str]:
        # Lufthansa Group + Star Alliance
        return [
            "LH",  # Lufthansa
            "LX",  # Swiss
            "OS",  # Austrian
            "SN",  # Brussels Airlines
            "UA",  # United
            "AC",  # Air Canada
            "NH",  # ANA
            "SQ",  # Singapore
            "TG",  # Thai
            "SK",  # SAS
            "TP",  # TAP Portugal
            "TK",  # Turkish
        ]
    
    # Cabin class mapping for Lufthansa
    CABIN_MAP = {
        CabinClass.ECONOMY: "economy",
        CabinClass.PREMIUM_ECONOMY: "premium_economy",
        CabinClass.BUSINESS: "business",
        CabinClass.FIRST: "first",
    }
    
    # Miles & More API endpoints (discovered)
    API_ENDPOINTS = {
        "award_search": "/api/award/search",
        "availability": "/api/availability",
    }
    
    # ============== Resilient Locators ==============
    
    def _get_origin_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for origin airport input"""
        return [
            (By.ID, "flightmanageralialialialialialialialialialialialiFrom"),
            (By.CSS_SELECTOR, "[data-testid='origin-input']"),
            (By.CSS_SELECTOR, "input[name='origin']"),
            (By.CSS_SELECTOR, "input[placeholder*='From']"),
            (By.CSS_SELECTOR, "[aria-label*='From']"),
            (By.XPATH, "//input[contains(@id, 'from') or contains(@id, 'origin')]"),
        ]
    
    def _get_destination_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for destination airport input"""
        return [
            (By.ID, "flightmanageralialialialialialialialialialialialiTo"),
            (By.CSS_SELECTOR, "[data-testid='destination-input']"),
            (By.CSS_SELECTOR, "input[name='destination']"),
            (By.CSS_SELECTOR, "input[placeholder*='To']"),
            (By.CSS_SELECTOR, "[aria-label*='To']"),
            (By.XPATH, "//input[contains(@id, 'to') or contains(@id, 'destination')]"),
        ]
    
    def _get_date_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for departure date"""
        return [
            (By.CSS_SELECTOR, "[data-testid='departure-date']"),
            (By.CSS_SELECTOR, "input[name='departureDate']"),
            (By.CSS_SELECTOR, "button[aria-label*='departure']"),
            (By.XPATH, "//button[contains(@aria-label, 'Depart')]"),
        ]
    
    def _get_award_toggle_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for award/miles toggle"""
        return [
            (By.CSS_SELECTOR, "[data-testid='miles-toggle']"),
            (By.CSS_SELECTOR, "input[name='payWithMiles']"),
            (By.XPATH, "//label[contains(text(), 'Pay with miles')]"),
            (By.XPATH, "//label[contains(text(), 'Miles')]"),
            (By.CSS_SELECTOR, "[aria-label*='miles']"),
        ]
    
    def _get_search_button_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for search button"""
        return [
            (By.CSS_SELECTOR, "[data-testid='search-button']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Search')]"),
            (By.XPATH, "//button[contains(text(), 'Find flights')]"),
        ]
    
    def _get_flight_card_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for flight result cards"""
        return [
            (By.CSS_SELECTOR, "[data-testid='flight-card']"),
            (By.CSS_SELECTOR, ".flight-result"),
            (By.CSS_SELECTOR, "[class*='FlightOption']"),
            (By.CSS_SELECTOR, ".offer-card"),
        ]
    
    # ============== Main Search Method ==============
    
    async def search_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass] = None,
        passengers: int = 1
    ) -> List[FlightAvailability]:
        """
        Search for Miles & More award availability.
        
        Strategy:
        1. Try API search first (faster, more reliable when working)
        2. Fall back to browser scraping
        """
        logger.info(f"Searching Lufthansa M&M: {origin} → {destination} on {departure_date}")
        
        # Try API first
        try:
            results = await self._search_via_api(
                origin, destination, departure_date, cabin_class, passengers
            )
            if results:
                logger.info(f"Lufthansa API returned {len(results)} results")
                return results
        except Exception as e:
            logger.debug(f"Lufthansa API failed, trying browser: {e}")
        
        # Fall back to browser
        try:
            results = await self._search_via_browser(
                origin, destination, departure_date, cabin_class, passengers
            )
            return results
        except CaptchaError:
            logger.error("CAPTCHA encountered on Lufthansa")
            raise
        except BlockedError:
            logger.error("Blocked by Lufthansa")
            raise
        except Exception as e:
            logger.error(f"Lufthansa scraping failed: {e}")
            return []
    
    # ============== API Search ==============
    
    async def _search_via_api(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """Search using Lufthansa's API (if accessible)"""
        
        if not HAS_HTTPX:
            logger.debug("httpx not available for API search")
            return []
        
        # Build API request
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }
        
        # Lufthansa award search API structure (discovered)
        payload = {
            "origin": origin,
            "destination": destination,
            "departureDate": departure_date.isoformat(),
            "passengers": {
                "adults": passengers,
                "children": 0,
                "infants": 0
            },
            "cabin": self.CABIN_MAP.get(cabin_class, "economy") if cabin_class else None,
            "paymentType": "MILES",
            "tripType": "ONE_WAY",
        }
        
        try:
            async with httpx.AsyncClient(http2=True, timeout=20) as client:
                # Try award search endpoint
                api_url = f"{self.base_url}{self.API_ENDPOINTS['award_search']}"
                
                response = await client.post(
                    api_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_api_response(data, origin, destination, departure_date)
                elif response.status_code in [401, 403]:
                    logger.debug("Lufthansa API requires authentication")
                else:
                    logger.debug(f"Lufthansa API returned {response.status_code}")
                    
        except Exception as e:
            logger.debug(f"Lufthansa API error: {e}")
        
        return []
    
    def _parse_api_response(
        self,
        data: Dict,
        origin: str,
        destination: str,
        departure_date: date
    ) -> List[FlightAvailability]:
        """Parse API response into FlightAvailability objects"""
        flights = []
        
        # Handle various response structures
        offers = data.get("offers", data.get("flights", data.get("results", [])))
        
        for offer in offers:
            try:
                flight = self._parse_api_offer(offer, origin, destination, departure_date)
                if flight:
                    flights.append(flight)
            except Exception as e:
                logger.warning(f"Failed to parse Lufthansa API offer: {e}")
        
        return flights
    
    def _parse_api_offer(
        self,
        offer: Dict,
        origin: str,
        destination: str,
        departure_date: date
    ) -> Optional[FlightAvailability]:
        """Parse a single API offer"""
        
        # Extract segments
        segments = offer.get("segments", [offer])
        first_segment = segments[0] if segments else offer
        
        # Flight details
        airline = first_segment.get("carrier", first_segment.get("airline", "LH"))
        flight_number = first_segment.get("flightNumber", "????")
        
        # Times
        departure_time = first_segment.get("departureTime", "00:00")[:5]
        arrival_time = first_segment.get("arrivalTime", "00:00")[:5]
        
        # Duration
        duration_minutes = offer.get("duration", 0)
        if isinstance(duration_minutes, str):
            duration_minutes = self._parse_duration(duration_minutes)
        
        # Award details
        miles = offer.get("miles", offer.get("price", {}).get("miles", 0))
        taxes = offer.get("taxes", offer.get("price", {}).get("taxes", 0))
        if isinstance(taxes, dict):
            taxes = taxes.get("amount", 0)
        
        # Cabin
        cabin_str = offer.get("cabin", first_segment.get("cabin", "economy"))
        cabin_class = self._map_cabin_class(cabin_str)
        
        # Availability
        seats = offer.get("seatsAvailable", offer.get("availability", 1))
        
        # Stops
        stops = len(segments) - 1 if len(segments) > 1 else 0
        connection_airports = [
            s.get("destination", s.get("arrival", "")) 
            for s in segments[:-1]
        ] if stops > 0 else []
        
        # Generate ID
        flight_id = hashlib.md5(
            f"{self.program_name}:{airline}{flight_number}:{origin}:{destination}:{departure_date}:{cabin_class.value}".encode()
        ).hexdigest()[:12]
        
        return FlightAvailability(
            id=flight_id,
            source_program=self.program_name,
            origin=origin,
            destination=destination,
            airline=airline,
            flight_number=f"{airline}{flight_number}",
            departure_date=departure_date,
            departure_time=departure_time,
            arrival_time=arrival_time,
            duration_minutes=duration_minutes,
            cabin_class=cabin_class,
            points_required=miles,
            taxes_fees=float(taxes),
            seats_available=seats,
            stops=stops,
            connection_airports=connection_airports,
            scraped_at=datetime.utcnow(),
            raw_data={"api_offer": offer}
        )
    
    # ============== Browser Search ==============
    
    async def _search_via_browser(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """Search using browser automation"""
        
        if not HAS_SELENIUM:
            raise RuntimeError("Selenium not installed")
        
        browser = None
        
        try:
            # Create browser manager
            browser = create_browser_manager(
                program=self.program_name,
                proxy_enabled=settings.proxy_enabled
            )
            
            driver = browser.create_driver()
            if not driver:
                raise RuntimeError("Failed to create browser driver")
            
            # Navigate to award booking page
            award_url = f"{self.base_url}/us/en/book-and-manage/book/award-flights"
            logger.debug(f"Navigating to: {award_url}")
            
            driver.get(award_url)
            await browser.human_delay(3, 5)
            
            # Check for blocks
            self._check_for_blocks(driver)
            
            # Handle cookie consent
            await self._handle_cookie_consent(driver, browser)
            
            # Fill search form
            await self._fill_search_form(driver, browser, origin, destination, departure_date, passengers)
            
            # Submit search
            await self._submit_search(driver, browser)
            
            # Wait for results
            await self._wait_for_results(driver, browser)
            
            # Parse results
            results = self._parse_browser_results(
                driver.page_source,
                origin,
                destination,
                departure_date,
                cabin_class
            )
            
            logger.info(f"Found {len(results)} Lufthansa flights via browser")
            return results
            
        finally:
            if browser:
                browser.close()
    
    def _check_for_blocks(self, driver) -> None:
        """Check if we're blocked or facing CAPTCHA"""
        html = driver.page_source.lower()
        
        block_indicators = {
            "captcha": CaptchaError,
            "recaptcha": CaptchaError,
            "challenge": CaptchaError,
            "blocked": BlockedError,
            "access denied": BlockedError,
            "security check": BlockedError,
        }
        
        for indicator, error_class in block_indicators.items():
            if indicator in html:
                raise error_class(f"Blocked by Lufthansa: {indicator}")
    
    async def _handle_cookie_consent(self, driver, browser: BrowserManager) -> None:
        """Handle cookie consent popup"""
        try:
            consent_selectors = [
                "[data-testid='accept-cookies']",
                "button[id*='cookie'][id*='accept']",
                ".cookie-accept",
                "button.accept-all",
            ]
            
            for selector in consent_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    await browser.human_click(btn)
                    await browser.human_delay(1, 2)
                    logger.debug("Accepted cookie consent")
                    return
                except:
                    continue
        except Exception as e:
            logger.debug(f"No cookie consent or failed: {e}")
    
    async def _fill_search_form(
        self,
        driver,
        browser: BrowserManager,
        origin: str,
        destination: str,
        departure_date: date,
        passengers: int
    ) -> None:
        """Fill in the search form"""
        
        # Enable award search first
        for by, selector in self._get_award_toggle_locators():
            try:
                toggle = driver.find_element(by, selector)
                if not toggle.is_selected():
                    await browser.human_click(toggle)
                    await browser.human_delay(1, 2)
                break
            except:
                continue
        
        # Enter origin
        for by, selector in self._get_origin_input_locators():
            try:
                origin_input = driver.find_element(by, selector)
                await browser.human_click(origin_input)
                await browser.human_type(origin_input, origin, clear_first=True)
                await browser.human_delay(0.5, 1)
                
                # Select from dropdown
                origin_input.send_keys(Keys.ARROW_DOWN)
                await browser.human_delay(0.3, 0.5)
                origin_input.send_keys(Keys.ENTER)
                await browser.human_delay(0.5, 1)
                break
            except Exception as e:
                continue
        
        # Enter destination
        for by, selector in self._get_destination_input_locators():
            try:
                dest_input = driver.find_element(by, selector)
                await browser.human_click(dest_input)
                await browser.human_type(dest_input, destination, clear_first=True)
                await browser.human_delay(0.5, 1)
                
                dest_input.send_keys(Keys.ARROW_DOWN)
                await browser.human_delay(0.3, 0.5)
                dest_input.send_keys(Keys.ENTER)
                await browser.human_delay(0.5, 1)
                break
            except:
                continue
        
        # Enter date - Lufthansa typically uses a date picker
        for by, selector in self._get_date_input_locators():
            try:
                date_elem = driver.find_element(by, selector)
                await browser.human_click(date_elem)
                await browser.human_delay(0.5, 1)
                
                # Type date in expected format
                date_str = departure_date.strftime("%d/%m/%Y")
                date_input = driver.find_element(By.CSS_SELECTOR, "input[type='date'], input[placeholder*='date']")
                await browser.human_type(date_input, date_str, clear_first=True)
                await browser.human_delay(0.5, 1)
                break
            except:
                continue
    
    async def _submit_search(self, driver, browser: BrowserManager) -> None:
        """Submit the search form"""
        for by, selector in self._get_search_button_locators():
            try:
                search_btn = driver.find_element(by, selector)
                await browser.human_click(search_btn)
                logger.debug("Clicked search button")
                return
            except:
                continue
        
        logger.warning("Could not find search button")
    
    async def _wait_for_results(self, driver, browser: BrowserManager) -> None:
        """Wait for results to load"""
        try:
            wait = WebDriverWait(driver, 20)
            wait.until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "[data-testid='flight-card'], .flight-result, .offer-card, .no-results"
                ))
            )
            await browser.human_delay(2, 3)
        except Exception as e:
            logger.warning(f"Timeout waiting for Lufthansa results: {e}")
    
    # ============== Result Parsing ==============
    
    def _parse_browser_results(
        self,
        html: str,
        origin: str,
        destination: str,
        departure_date: date,
        filter_cabin: Optional[CabinClass] = None
    ) -> List[FlightAvailability]:
        """Parse flight results from browser HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        flights = []
        
        # Find flight cards using multiple selectors
        flight_cards = soup.select('[data-testid="flight-card"], .flight-result, .offer-card')
        
        if not flight_cards:
            # Try alternative patterns
            flight_cards = soup.find_all('div', class_=re.compile(r'flight|offer|result', re.I))
        
        logger.debug(f"Found {len(flight_cards)} Lufthansa flight cards")
        
        for card in flight_cards:
            try:
                flight = self._parse_flight_card(card, origin, destination, departure_date)
                if flight:
                    if filter_cabin and flight.cabin_class != filter_cabin:
                        continue
                    flights.append(flight)
            except Exception as e:
                logger.warning(f"Failed to parse Lufthansa flight card: {e}")
        
        return flights
    
    def _parse_flight_card(
        self,
        card: BeautifulSoup,
        origin: str,
        destination: str,
        departure_date: date
    ) -> Optional[FlightAvailability]:
        """Parse a single flight card from HTML"""
        
        # Extract airline and flight number
        airline = "LH"
        flight_number = "????"
        
        flight_elem = card.select_one('.flight-number, [class*="flightNumber"], [data-testid*="flight"]')
        if flight_elem:
            text = flight_elem.get_text(strip=True)
            match = re.search(r'([A-Z]{2})\s*(\d+)', text)
            if match:
                airline = match.group(1)
                flight_number = match.group(2)
        
        # Times
        time_elems = card.select('.time, [class*="time"], time')
        departure_time = "00:00"
        arrival_time = "00:00"
        
        if len(time_elems) >= 2:
            departure_time = self._parse_time(time_elems[0].get_text(strip=True))
            arrival_time = self._parse_time(time_elems[1].get_text(strip=True))
        
        # Duration
        duration_minutes = 0
        duration_elem = card.select_one('.duration, [class*="duration"]')
        if duration_elem:
            duration_minutes = self._parse_duration(duration_elem.get_text(strip=True))
        
        # Miles
        miles = 0
        miles_elem = card.select_one('.miles, [class*="miles"], [class*="price"]')
        if miles_elem:
            text = miles_elem.get_text(strip=True).replace(',', '').replace('.', '')
            match = re.search(r'(\d+)', text)
            if match:
                miles = int(match.group(1))
        
        # Taxes
        taxes = 0.0
        taxes_elem = card.select_one('.taxes, [class*="tax"], [class*="fee"]')
        if taxes_elem:
            match = re.search(r'[\$€£]?\s*(\d+(?:[.,]\d{2})?)', taxes_elem.get_text())
            if match:
                taxes = float(match.group(1).replace(',', '.'))
        
        # Cabin class
        cabin_class = CabinClass.ECONOMY
        card_text = card.get_text().lower()
        if 'first' in card_text:
            cabin_class = CabinClass.FIRST
        elif 'business' in card_text:
            cabin_class = CabinClass.BUSINESS
        elif 'premium' in card_text:
            cabin_class = CabinClass.PREMIUM_ECONOMY
        
        # Stops
        stops = 0
        stops_elem = card.select_one('.stops, [class*="stop"]')
        if stops_elem:
            text = stops_elem.get_text().lower()
            if 'nonstop' in text or 'direct' in text:
                stops = 0
            else:
                match = re.search(r'(\d+)', text)
                if match:
                    stops = int(match.group(1))
        
        # Generate ID
        flight_id = hashlib.md5(
            f"{self.program_name}:{airline}{flight_number}:{origin}:{destination}:{departure_date}:{cabin_class.value}".encode()
        ).hexdigest()[:12]
        
        return FlightAvailability(
            id=flight_id,
            source_program=self.program_name,
            origin=origin,
            destination=destination,
            airline=airline,
            flight_number=f"{airline}{flight_number}",
            departure_date=departure_date,
            departure_time=departure_time,
            arrival_time=arrival_time,
            duration_minutes=duration_minutes,
            cabin_class=cabin_class,
            points_required=miles,
            taxes_fees=taxes,
            seats_available=1,
            stops=stops,
            connection_airports=[],
            scraped_at=datetime.utcnow(),
            raw_data={"html_snippet": str(card)[:500]}
        )
    
    # ============== Helper Methods ==============
    
    def _map_cabin_class(self, cabin_str: str) -> CabinClass:
        """Map cabin string to CabinClass enum"""
        cabin_lower = cabin_str.lower()
        if 'first' in cabin_lower:
            return CabinClass.FIRST
        elif 'business' in cabin_lower:
            return CabinClass.BUSINESS
        elif 'premium' in cabin_lower:
            return CabinClass.PREMIUM_ECONOMY
        return CabinClass.ECONOMY
    
    def _parse_time(self, text: str) -> str:
        """Parse time string to HH:MM format"""
        match = re.search(r'(\d{1,2}):(\d{2})', text)
        if match:
            return f"{int(match.group(1)):02d}:{match.group(2)}"
        return "00:00"
    
    def _parse_duration(self, text: str) -> int:
        """Parse duration string to minutes"""
        total = 0
        hours_match = re.search(r'(\d+)\s*h', text, re.I)
        if hours_match:
            total += int(hours_match.group(1)) * 60
        mins_match = re.search(r'(\d+)\s*m', text, re.I)
        if mins_match:
            total += int(mins_match.group(1))
        return total
