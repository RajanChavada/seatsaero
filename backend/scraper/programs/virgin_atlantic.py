"""
Virgin Atlantic Flying Club Scraper - Award Flight Availability

Great for transatlantic routes, especially UK-USA.
Partner with Delta for SkyTeam access.
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Tuple
import hashlib
import re
import asyncio
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


class VirginAtlanticFlyingClubScraper(BaseScraper):
    """
    Scraper for Virgin Atlantic Flying Club award availability.
    
    Features:
    - Premium transatlantic routes
    - Upper Class (business) sweet spots
    - Delta partner availability
    - UK hub (LHR, MAN, LGW)
    """
    
    @property
    def program_name(self) -> str:
        return "virgin_atlantic"
    
    @property
    def program_display_name(self) -> str:
        return "Virgin Atlantic Flying Club"
    
    @property
    def base_url(self) -> str:
        return "https://www.virginatlantic.com"
    
    @property
    def supported_airlines(self) -> List[str]:
        return [
            "VS",  # Virgin Atlantic
            "DL",  # Delta (partner)
            "AF",  # Air France (SkyTeam)
            "KL",  # KLM (SkyTeam)
        ]
    
    # Cabin class mapping for Virgin Atlantic
    CABIN_MAP = {
        CabinClass.ECONOMY: "economy",
        CabinClass.PREMIUM_ECONOMY: "premium",  # Premium
        CabinClass.BUSINESS: "upper",           # Upper Class
        CabinClass.FIRST: "upper",              # No true first, use Upper Class
    }
    
    # Virgin Atlantic cabin names
    VA_CABINS = {
        "economy": CabinClass.ECONOMY,
        "economy classic": CabinClass.ECONOMY,
        "economy delight": CabinClass.ECONOMY,
        "premium": CabinClass.PREMIUM_ECONOMY,
        "premium economy": CabinClass.PREMIUM_ECONOMY,
        "upper class": CabinClass.BUSINESS,
        "upper": CabinClass.BUSINESS,
    }
    
    # ============== Resilient Locators ==============
    
    def _get_origin_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for origin airport input"""
        return [
            (By.ID, "origin"),
            (By.CSS_SELECTOR, "[data-testid='origin-input']"),
            (By.CSS_SELECTOR, "input[name='origin']"),
            (By.CSS_SELECTOR, "input[placeholder*='Flying from']"),
            (By.CSS_SELECTOR, "[aria-label*='From']"),
            (By.XPATH, "//input[contains(@placeholder, 'from')]"),
        ]
    
    def _get_destination_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for destination airport input"""
        return [
            (By.ID, "destination"),
            (By.CSS_SELECTOR, "[data-testid='destination-input']"),
            (By.CSS_SELECTOR, "input[name='destination']"),
            (By.CSS_SELECTOR, "input[placeholder*='Flying to']"),
            (By.CSS_SELECTOR, "[aria-label*='To']"),
            (By.XPATH, "//input[contains(@placeholder, 'to')]"),
        ]
    
    def _get_date_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for departure date"""
        return [
            (By.CSS_SELECTOR, "[data-testid='departure-date']"),
            (By.CSS_SELECTOR, "input[name='departureDate']"),
            (By.CSS_SELECTOR, "button[aria-label*='departure']"),
            (By.CSS_SELECTOR, ".date-picker-trigger"),
        ]
    
    def _get_points_toggle_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for Flying Club points toggle"""
        return [
            (By.CSS_SELECTOR, "[data-testid='points-toggle']"),
            (By.CSS_SELECTOR, "input[name='usePoints']"),
            (By.XPATH, "//label[contains(text(), 'Flying Club')]"),
            (By.XPATH, "//label[contains(text(), 'points')]"),
            (By.CSS_SELECTOR, "[aria-label*='points']"),
        ]
    
    def _get_search_button_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for search button"""
        return [
            (By.CSS_SELECTOR, "[data-testid='search-flights']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Search')]"),
            (By.XPATH, "//button[contains(text(), 'Find flights')]"),
            (By.CSS_SELECTOR, ".search-flights-btn"),
        ]
    
    def _get_flight_card_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for flight result cards"""
        return [
            (By.CSS_SELECTOR, "[data-testid='flight-card']"),
            (By.CSS_SELECTOR, ".flight-result"),
            (By.CSS_SELECTOR, "[class*='FlightCard']"),
            (By.CSS_SELECTOR, ".flight-option"),
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
        Search for Flying Club award availability.
        
        Virgin Atlantic has a clean booking interface but uses Cloudflare.
        """
        logger.info(f"Searching Virgin Atlantic: {origin} → {destination} on {departure_date}")
        
        try:
            results = await self._search_via_browser(
                origin, destination, departure_date, cabin_class, passengers
            )
            return results
        except CaptchaError:
            logger.error("CAPTCHA encountered on Virgin Atlantic")
            raise
        except BlockedError:
            logger.error("Blocked by Virgin Atlantic")
            raise
        except Exception as e:
            logger.error(f"Virgin Atlantic scraping failed: {e}")
            return []
    
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
            browser = create_browser_manager(
                program=self.program_name,
                proxy_enabled=settings.proxy_enabled
            )
            
            driver = browser.create_driver()
            if not driver:
                raise RuntimeError("Failed to create browser driver")
            
            # Build search URL - Virgin Atlantic allows direct URL construction
            search_url = self._build_search_url(origin, destination, departure_date, passengers)
            logger.debug(f"Virgin Atlantic search URL: {search_url}")
            
            driver.get(search_url)
            await browser.human_delay(3, 5)
            
            # Check for blocks
            self._check_for_blocks(driver)
            
            # Handle cookie consent
            await self._handle_cookie_consent(driver, browser)
            
            # Wait for results
            await self._wait_for_results(driver, browser)
            
            # Parse results
            results = self._parse_results(
                driver.page_source,
                origin,
                destination,
                departure_date,
                cabin_class
            )
            
            logger.info(f"Found {len(results)} Virgin Atlantic flights")
            return results
            
        finally:
            if browser:
                browser.close()
    
    def _build_search_url(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        passengers: int
    ) -> str:
        """Build Virgin Atlantic search URL"""
        date_str = departure_date.strftime("%Y-%m-%d")
        
        # Virgin Atlantic booking URL format
        url = (
            f"{self.base_url}/flight-search/book-a-flight/results"
            f"?origin={origin}"
            f"&destination={destination}"
            f"&departureDate={date_str}"
            f"&tripType=ONE_WAY"
            f"&adults={passengers}"
            f"&children=0"
            f"&infants=0"
            f"&paymentType=POINTS"  # Flying Club points
            f"&cabin=all"
        )
        
        return url
    
    def _check_for_blocks(self, driver) -> None:
        """Check if we're blocked or facing CAPTCHA"""
        html = driver.page_source.lower()
        
        block_indicators = {
            "captcha": CaptchaError,
            "cf-challenge": CaptchaError,  # Cloudflare
            "challenge-running": CaptchaError,
            "blocked": BlockedError,
            "access denied": BlockedError,
            "ray id": BlockedError,  # Cloudflare block page
        }
        
        for indicator, error_class in block_indicators.items():
            if indicator in html:
                raise error_class(f"Blocked by Virgin Atlantic: {indicator}")
    
    async def _handle_cookie_consent(self, driver, browser: BrowserManager) -> None:
        """Handle cookie consent popup"""
        try:
            consent_selectors = [
                "[data-testid='accept-cookies']",
                "button[id*='cookie'][id*='accept']",
                ".cookie-accept",
                "#onetrust-accept-btn-handler",
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
            logger.debug(f"Cookie consent handling: {e}")
    
    async def _wait_for_results(self, driver, browser: BrowserManager) -> None:
        """Wait for results to load"""
        try:
            wait = WebDriverWait(driver, 20)
            wait.until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "[data-testid='flight-card'], .flight-result, .flight-option, .no-results, .error"
                ))
            )
            await browser.human_delay(2, 3)
        except Exception as e:
            logger.warning(f"Timeout waiting for Virgin Atlantic results: {e}")
    
    # ============== Result Parsing ==============
    
    def _parse_results(
        self,
        html: str,
        origin: str,
        destination: str,
        departure_date: date,
        filter_cabin: Optional[CabinClass] = None
    ) -> List[FlightAvailability]:
        """Parse flight results from page HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        flights = []
        
        # Find flight cards
        flight_cards = soup.select('[data-testid="flight-card"], .flight-result, .flight-option')
        
        if not flight_cards:
            flight_cards = soup.find_all('div', class_=re.compile(r'flight|card|result', re.I))
        
        logger.debug(f"Found {len(flight_cards)} Virgin Atlantic flight cards")
        
        for card in flight_cards:
            try:
                flight = self._parse_flight_card(card, origin, destination, departure_date)
                if flight:
                    if filter_cabin and flight.cabin_class != filter_cabin:
                        continue
                    flights.append(flight)
            except Exception as e:
                logger.warning(f"Failed to parse VA flight card: {e}")
        
        return flights
    
    def _parse_flight_card(
        self,
        card: BeautifulSoup,
        origin: str,
        destination: str,
        departure_date: date
    ) -> Optional[FlightAvailability]:
        """Parse a single flight card"""
        
        # Extract airline and flight number
        airline = "VS"
        flight_number = "????"
        
        flight_elem = card.select_one('.flight-number, [class*="flightNumber"]')
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
        
        # Points
        points = 0
        points_elem = card.select_one('.points, [class*="points"], [class*="miles"]')
        if points_elem:
            text = points_elem.get_text(strip=True).replace(',', '')
            match = re.search(r'(\d+)', text)
            if match:
                points = int(match.group(1))
        
        # Taxes
        taxes = 0.0
        taxes_elem = card.select_one('.taxes, [class*="tax"], [class*="fee"]')
        if taxes_elem:
            match = re.search(r'[£$€]?\s*(\d+(?:\.\d{2})?)', taxes_elem.get_text())
            if match:
                taxes = float(match.group(1))
        
        # Cabin class
        cabin_class = CabinClass.ECONOMY
        card_text = card.get_text().lower()
        
        for va_cabin, cabin_enum in self.VA_CABINS.items():
            if va_cabin in card_text:
                cabin_class = cabin_enum
                break
        
        # Stops
        stops = 0
        stops_elem = card.select_one('.stops, [class*="stop"]')
        if stops_elem:
            text = stops_elem.get_text().lower()
            if 'direct' in text or 'nonstop' in text:
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
            points_required=points,
            taxes_fees=taxes,
            seats_available=1,
            stops=stops,
            connection_airports=[],
            scraped_at=datetime.utcnow(),
            raw_data={"html_snippet": str(card)[:500]}
        )
    
    # ============== Helper Methods ==============
    
    def _parse_time(self, text: str) -> str:
        """Parse time string to HH:MM format"""
        # Handle 24h format (14:30) or 12h format (2:30pm)
        match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', text, re.I)
        if match:
            hour = int(match.group(1))
            minute = match.group(2)
            period = match.group(3)
            
            if period:
                if period.lower() == 'pm' and hour != 12:
                    hour += 12
                elif period.lower() == 'am' and hour == 12:
                    hour = 0
            
            return f"{hour:02d}:{minute}"
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
