"""
Aeroplan Scraper - Enhanced with resilient locators and human-like behavior
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Tuple
import hashlib
import re

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
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False


class AeroplanScraper(BaseScraper):
    """
    Scraper for Air Canada Aeroplan award availability.
    
    Features:
    - Resilient locators with multiple fallbacks
    - Human-like interactions
    - CAPTCHA and block detection
    - Canadian locale/timezone alignment
    """
    
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
    def supported_airlines(self) -> List[str]:
        return ["AC", "LH", "UA", "NH", "SQ", "TG", "OZ", "SK", "ET", "CM"]
    
    # Cabin class mapping
    CABIN_MAP = {
        CabinClass.ECONOMY: "economy",
        CabinClass.PREMIUM_ECONOMY: "premium-economy",
        CabinClass.BUSINESS: "business",
        CabinClass.FIRST: "first",
    }
    
    # ============== Resilient Locators ==============
    
    def _get_origin_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for origin airport input"""
        return [
            (By.ID, "origin"),
            (By.CSS_SELECTOR, "[data-testid='origin-input']"),
            (By.CSS_SELECTOR, "input[aria-label*='From']"),
            (By.CSS_SELECTOR, "input[placeholder*='From']"),
            (By.CSS_SELECTOR, ".origin-field input"),
            (By.XPATH, "//input[contains(@aria-label, 'origin') or contains(@aria-label, 'departure')]"),
            (By.NAME, "origin"),
        ]
    
    def _get_destination_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for destination airport input"""
        return [
            (By.ID, "destination"),
            (By.CSS_SELECTOR, "[data-testid='destination-input']"),
            (By.CSS_SELECTOR, "input[aria-label*='To']"),
            (By.CSS_SELECTOR, "input[placeholder*='To']"),
            (By.CSS_SELECTOR, ".destination-field input"),
            (By.XPATH, "//input[contains(@aria-label, 'destination') or contains(@aria-label, 'arrival')]"),
            (By.NAME, "destination"),
        ]
    
    def _get_date_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for departure date input"""
        return [
            (By.CSS_SELECTOR, "[data-testid='departure-date']"),
            (By.CSS_SELECTOR, "input[aria-label*='Departure date']"),
            (By.CSS_SELECTOR, ".date-picker input"),
            (By.XPATH, "//button[contains(@aria-label, 'departure') and contains(@aria-label, 'date')]"),
            (By.CSS_SELECTOR, "[data-testid='datepicker-trigger']"),
        ]
    
    def _get_points_toggle_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for Aeroplan points toggle"""
        return [
            (By.CSS_SELECTOR, "[data-testid='aeroplan-toggle']"),
            (By.CSS_SELECTOR, "input[type='checkbox'][aria-label*='Aeroplan']"),
            (By.XPATH, "//label[contains(text(), 'Use Aeroplan')]"),
            (By.CSS_SELECTOR, ".reward-toggle input"),
            (By.ID, "useAeroplan"),
        ]
    
    def _get_search_button_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for search button"""
        return [
            (By.CSS_SELECTOR, "[data-testid='search-flights-button']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Search')]"),
            (By.XPATH, "//button[contains(text(), 'Find flights')]"),
            (By.CSS_SELECTOR, ".search-button"),
        ]
    
    def _get_flight_results_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for flight results container"""
        return [
            (By.CSS_SELECTOR, "[data-testid='flight-list']"),
            (By.CSS_SELECTOR, ".flight-results"),
            (By.CSS_SELECTOR, "[class*='FlightList']"),
            (By.CSS_SELECTOR, ".flight-options"),
            (By.XPATH, "//div[contains(@class, 'flight')]//div[contains(@class, 'list')]"),
        ]
    
    def _get_flight_card_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for individual flight cards"""
        return [
            (By.CSS_SELECTOR, "[data-testid='flight-card']"),
            (By.CSS_SELECTOR, ".flight-option"),
            (By.CSS_SELECTOR, "[class*='FlightCard']"),
            (By.CSS_SELECTOR, ".flight-row"),
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
        Search for award availability on Aeroplan.
        
        Uses browser scraping as Aeroplan doesn't have an accessible API.
        """
        logger.info(f"Searching Aeroplan: {origin} → {destination} on {departure_date}")
        
        try:
            results = await self._search_via_browser(
                origin, destination, departure_date, cabin_class, passengers
            )
            return results
        except CaptchaError:
            logger.error("CAPTCHA encountered - aborting")
            raise
        except BlockedError:
            logger.error("Blocked by Aeroplan - aborting")
            raise
        except Exception as e:
            logger.error(f"Aeroplan scraping failed: {e}")
            return []
    
    # ============== Browser Method ==============
    
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
        
        # Get proxy
        proxy_config = None
        if settings.proxy_enabled:
            proxy_config = await get_proxy_pool().acquire(
                self.program_name,
                job_id=f"browser-{origin}-{destination}-{departure_date}"
            )
            if proxy_config:
                self._current_proxy_id = proxy_config.id
        
        # Create browser manager
        browser = create_browser_manager(
            program=self.program_name,
            proxy=proxy_config
        )
        
        try:
            async with browser.get_driver() as driver:
                # Build search URL
                cabin_param = self.CABIN_MAP.get(cabin_class, "economy")
                date_str = departure_date.strftime("%Y-%m-%d")
                
                search_url = (
                    f"{self.base_url}/aeroplan/redeem/availability/outbound"
                    f"?org0={origin.upper()}"
                    f"&dest0={destination.upper()}"
                    f"&departureDate0={date_str}"
                    f"&ADT=1&YTH=0&CHD=0&INF=0&INS=0"
                    f"&marketCode=DOM&cabinClass={cabin_param}"
                    f"&tripType=O&awardBooking=true"
                )
                
                if not await browser.navigate(search_url):
                    raise Exception("Failed to load search page")
                
                # Check for CAPTCHA
                if browser.detect_captcha():
                    raise CaptchaError("CAPTCHA detected on page load")
                
                # Check for block
                if browser.detect_block_page():
                    raise BlockedError("Blocked on page load")
                
                # Random scroll
                browser.human_scroll(random.randint(50, 150))
                
                # Wait for results
                await self._wait_for_results(browser)
                
                # Check for CAPTCHA after loading
                if browser.detect_captcha():
                    raise CaptchaError("CAPTCHA detected after search")
                
                # Parse results
                html = browser.get_page_source()
                return self._parse_html_response(html, origin, destination, departure_date)
                
        except (CaptchaError, BlockedError):
            raise
        except Exception as e:
            logger.error(f"Aeroplan browser scraping failed: {e}")
            # Screenshot for debugging
            try:
                browser.take_screenshot(f"logs/aeroplan_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            except:
                pass
            return []
    
    async def _wait_for_results(self, browser: BrowserManager) -> None:
        """Wait for flight results to load"""
        element = browser.wait_for_any_element(
            self._get_flight_results_locators(),
            timeout=30
        )
        
        if not element:
            logger.warning("Flight results not found, page may still be loading")
        
        # Extra wait for dynamic content
        browser.human_sleep(1500, 3000)
    
    def _parse_html_response(
        self,
        html: str,
        origin: str,
        destination: str,
        departure_date: date
    ) -> List[FlightAvailability]:
        """Parse HTML response from browser"""
        flights = []
        soup = BeautifulSoup(html, "lxml")
        
        # Try multiple selectors for flight cards
        flight_card_selectors = [
            "[data-testid='flight-card']",
            ".flight-option",
            "[class*='FlightCard']",
            ".flight-row",
            "[class*='flightOption']",
            ".available-flight",
        ]
        
        flight_cards = []
        for selector in flight_card_selectors:
            flight_cards = soup.select(selector)
            if flight_cards:
                logger.debug(f"Found {len(flight_cards)} flight cards with {selector}")
                break
        
        for card in flight_cards:
            try:
                flight = self._parse_flight_card(card, origin, destination, departure_date)
                if flight:
                    flights.append(flight)
            except Exception as e:
                logger.debug(f"Error parsing flight card: {e}")
                continue
        
        logger.info(f"Parsed {len(flights)} flights from Aeroplan HTML")
        return flights
    
    def _parse_flight_card(
        self,
        card,
        origin: str,
        destination: str,
        departure_date: date
    ) -> Optional[FlightAvailability]:
        """Parse a single flight card"""
        try:
            # Extract flight number
            flight_num_selectors = [
                "[data-testid='flight-number']",
                ".flight-number",
                "[class*='flightNumber']",
                ".carrier-info",
            ]
            flight_number = self._extract_text(card, flight_num_selectors) or "AC"
            
            # Extract times
            dep_time_selectors = [
                "[data-testid='departure-time']",
                ".departure-time",
                "[class*='departTime']",
                ".depart",
            ]
            arr_time_selectors = [
                "[data-testid='arrival-time']",
                ".arrival-time",
                "[class*='arrivalTime']",
                ".arrive",
            ]
            
            dep_time = self._extract_text(card, dep_time_selectors) or "00:00"
            arr_time = self._extract_text(card, arr_time_selectors) or "00:00"
            
            # Extract points
            points_selectors = [
                "[data-testid='points-cost']",
                ".points-cost",
                "[class*='points']",
                ".miles",
            ]
            points_text = self._extract_text(card, points_selectors) or "0"
            points = self._parse_points(points_text)
            
            # Extract cabin
            cabin_selectors = [
                "[data-testid='cabin-class']",
                ".cabin-class",
                "[class*='cabin']",
            ]
            cabin_text = self._extract_text(card, cabin_selectors) or "economy"
            cabin = self._map_cabin_class(cabin_text)
            
            # Generate ID
            flight_id = self._generate_flight_id(flight_number, departure_date, cabin.value)
            
            return FlightAvailability(
                id=flight_id,
                source_program=self.program_name,
                origin=origin.upper(),
                destination=destination.upper(),
                airline="Air Canada",
                flight_number=flight_number,
                departure_date=departure_date,
                departure_time=self._normalize_time(dep_time),
                arrival_time=self._normalize_time(arr_time),
                duration_minutes=0,
                cabin_class=cabin,
                points_required=points,
                taxes_fees=0,
                seats_available=0,
                stops=0,
            )
            
        except Exception as e:
            logger.debug(f"Error parsing flight card: {e}")
            return None
    
    # ============== Helper Methods ==============
    
    def _extract_text(self, element, selectors: List[str]) -> Optional[str]:
        """Extract text using multiple fallback selectors"""
        for selector in selectors:
            try:
                found = element.select_one(selector)
                if found:
                    return found.get_text(strip=True)
            except Exception:
                continue
        return None
    
    def _map_cabin_class(self, cabin_str: str) -> CabinClass:
        """Map cabin string to CabinClass enum"""
        cabin_lower = cabin_str.lower()
        if "first" in cabin_lower or "signature" in cabin_lower:
            return CabinClass.FIRST
        elif "business" in cabin_lower:
            return CabinClass.BUSINESS
        elif "premium" in cabin_lower:
            return CabinClass.PREMIUM_ECONOMY
        return CabinClass.ECONOMY
    
    def _normalize_time(self, time_str: str) -> str:
        """Normalize time string to HH:MM format"""
        try:
            time_str = time_str.upper().replace("AM", "").replace("PM", "").strip()
            
            patterns = [
                r"(\d{1,2}):(\d{2})",
                r"(\d{1,2})(\d{2})",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, time_str)
                if match:
                    hour, minute = match.groups()
                    return f"{int(hour):02d}:{minute}"
            
            return time_str
        except Exception:
            return time_str
    
    def _parse_points(self, points_text: str) -> int:
        """Parse points from text"""
        try:
            cleaned = re.sub(r"[^\d]", "", points_text)
            if cleaned:
                points = int(cleaned)
                if "k" in points_text.lower() and points < 1000:
                    points *= 1000
                return points
        except Exception:
            pass
        return 0


import random
