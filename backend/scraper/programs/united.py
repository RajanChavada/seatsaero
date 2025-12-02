"""
United MileagePlus Scraper - Enhanced with resilient locators and human-like behavior
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Tuple
import hashlib
import re

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from scraper.base import (
    BaseScraper, 
    FlightAvailability, 
    CabinClass,
    ScrapeResult,
    CaptchaError,
    BlockedError,
    RateLimitError,
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


class UnitedMileagePlusScraper(BaseScraper):
    """
    Scraper for United MileagePlus award availability.
    
    Features:
    - Resilient locators with multiple fallbacks
    - Human-like interactions
    - CAPTCHA and block detection
    - Rate limiting and retries
    """
    
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
        return ["UA", "LH", "AC", "NH", "SQ", "TG", "OZ", "SK", "LO", "OS", "SN", "TP"]
    
    # Cabin class mapping
    CABIN_MAP = {
        CabinClass.ECONOMY: "ECONOMY",
        CabinClass.PREMIUM_ECONOMY: "PREMIUM_ECONOMY", 
        CabinClass.BUSINESS: "BUSINESS",
        CabinClass.FIRST: "FIRST",
    }
    
    # ============== Resilient Locators ==============
    # Each method returns a list of (By, value) tuples to try in order
    
    def _get_origin_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for origin airport input"""
        return [
            (By.ID, "bookFlightOriginInput"),
            (By.CSS_SELECTOR, "[data-testid='AutocompleteBox-origin'] input"),
            (By.CSS_SELECTOR, "input[aria-label*='From']"),
            (By.CSS_SELECTOR, "input[placeholder*='From']"),
            (By.XPATH, "//input[contains(@aria-label, 'origin') or contains(@aria-label, 'From')]"),
            (By.CSS_SELECTOR, ".origin-airport input"),
            (By.NAME, "origin"),
        ]
    
    def _get_destination_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for destination airport input"""
        return [
            (By.ID, "bookFlightDestinationInput"),
            (By.CSS_SELECTOR, "[data-testid='AutocompleteBox-destination'] input"),
            (By.CSS_SELECTOR, "input[aria-label*='To']"),
            (By.CSS_SELECTOR, "input[placeholder*='To']"),
            (By.XPATH, "//input[contains(@aria-label, 'destination') or contains(@aria-label, 'To')]"),
            (By.CSS_SELECTOR, ".destination-airport input"),
            (By.NAME, "destination"),
        ]
    
    def _get_date_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for departure date input"""
        return [
            (By.ID, "bookFlightDateLbl"),
            (By.CSS_SELECTOR, "[data-testid='DepartDate']"),
            (By.CSS_SELECTOR, "input[aria-label*='Depart']"),
            (By.CSS_SELECTOR, ".date-picker input"),
            (By.XPATH, "//button[contains(@aria-label, 'departure date')]"),
            (By.CSS_SELECTOR, "[data-testid='flexible-dates-calendar']"),
        ]
    
    def _get_award_toggle_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for award travel toggle"""
        return [
            (By.ID, "awardTravel"),
            (By.CSS_SELECTOR, "[data-testid='award-travel-toggle']"),
            (By.CSS_SELECTOR, "input[type='checkbox'][aria-label*='award']"),
            (By.XPATH, "//label[contains(text(), 'Book with miles')]"),
            (By.CSS_SELECTOR, ".award-travel-checkbox"),
        ]
    
    def _get_search_button_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for search button"""
        return [
            (By.CSS_SELECTOR, "[data-testid='search-button']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Search')]"),
            (By.CSS_SELECTOR, ".search-button"),
            (By.ID, "bookFlightForm__submit"),
        ]
    
    def _get_flight_results_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for flight results container"""
        return [
            (By.CSS_SELECTOR, "[data-testid='flight-list']"),
            (By.CSS_SELECTOR, ".flight-result-list"),
            (By.CSS_SELECTOR, "[class*='FlightResultsList']"),
            (By.CSS_SELECTOR, ".flight-card"),
            (By.XPATH, "//div[contains(@class, 'flight')]//div[contains(@class, 'result')]"),
        ]
    
    def _get_flight_card_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for individual flight cards"""
        return [
            (By.CSS_SELECTOR, "[data-testid='flight-card']"),
            (By.CSS_SELECTOR, ".flight-result-card"),
            (By.CSS_SELECTOR, "[class*='FlightCard']"),
            (By.CSS_SELECTOR, ".flight-row"),
            (By.XPATH, "//div[contains(@class, 'flight') and contains(@class, 'card')]"),
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
        Search for award availability on United.
        
        Tries API first, falls back to browser scraping.
        """
        logger.info(f"Searching United: {origin} → {destination} on {departure_date}")
        
        # Try API method first (faster, less detectable)
        try:
            results = await self._search_via_api(
                origin, destination, departure_date, cabin_class, passengers
            )
            if results:
                return results
        except Exception as e:
            logger.warning(f"API method failed: {e}")
        
        # Fall back to browser scraping
        logger.info("API method failed, falling back to browser scraping")
        try:
            results = await self._search_via_browser(
                origin, destination, departure_date, cabin_class, passengers
            )
            return results
        except CaptchaError:
            logger.error("CAPTCHA encountered - aborting")
            raise
        except BlockedError:
            logger.error("Blocked by United - aborting")
            raise
        except Exception as e:
            logger.error(f"Browser scraping failed: {e}")
            return []
    
    # ============== API Method ==============
    
    async def _search_via_api(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """Search using United's API (less detectable but may be blocked)"""
        
        search_url = f"{self.base_url}/api/flight/FetchFlights"
        
        payload = {
            "Trips": [{
                "Origin": origin.upper(),
                "Destination": destination.upper(),
                "DepartDate": departure_date.strftime("%Y-%m-%d"),
            }],
            "Passengers": {
                "Adults": passengers,
                "Children": 0,
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
        
        # Get proxy if available
        proxy_config = None
        if settings.proxy_enabled:
            proxy_config = await get_proxy_pool().acquire(
                self.program_name,
                job_id=f"{origin}-{destination}-{departure_date}"
            )
        
        try:
            client_kwargs = {
                "timeout": 30,
                "follow_redirects": True,
                "verify": False,
            }
            if proxy_config:
                client_kwargs["proxy"] = proxy_config.to_httpx_proxy()
                self._current_proxy_id = proxy_config.id
            
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.post(
                    search_url,
                    json=payload,
                    headers=headers
                )
                
                # Check for errors
                self.check_http_status(response.status_code)
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_api_response(data, origin, destination, departure_date)
                else:
                    logger.warning(f"United API returned {response.status_code}")
                    return []
                    
        except (RateLimitError, BlockedError):
            raise
        except Exception as e:
            logger.error(f"United API request failed: {e}")
            return []
    
    def _parse_api_response(
        self,
        data: Dict[str, Any],
        origin: str,
        destination: str,
        departure_date: date
    ) -> List[FlightAvailability]:
        """Parse API JSON response"""
        flights = []
        
        try:
            trip_data = data.get("data", {}).get("Trips", [])
            if not trip_data:
                return []
            
            for trip in trip_data:
                for flight_option in trip.get("Flights", []):
                    for product in flight_option.get("Products", []):
                        if not product.get("AwardAvailable"):
                            continue
                        
                        try:
                            # Parse cabin class
                            cabin_str = product.get("CabinType", "").lower()
                            cabin = self._map_cabin_class(cabin_str)
                            
                            # Parse times
                            dep_time = flight_option.get("DepartDateTime", "")
                            arr_time = flight_option.get("ArrivalDateTime", "")
                            
                            # Parse duration
                            duration = flight_option.get("TravelMinutes", 0)
                            
                            # Generate ID
                            flight_num = flight_option.get("FlightNumber", "")
                            flight_id = self._generate_flight_id(
                                flight_num, departure_date, cabin.value
                            )
                            
                            flight = FlightAvailability(
                                id=flight_id,
                                source_program=self.program_name,
                                origin=origin.upper(),
                                destination=destination.upper(),
                                airline="United Airlines",
                                flight_number=f"UA{flight_num}",
                                departure_date=departure_date,
                                departure_time=self._format_time(dep_time),
                                arrival_time=self._format_time(arr_time),
                                duration_minutes=duration,
                                cabin_class=cabin,
                                points_required=product.get("Miles", 0),
                                taxes_fees=product.get("TaxAndFees", {}).get("Amount", 0),
                                seats_available=product.get("BookingCount", 0),
                                stops=flight_option.get("StopCount", 0),
                            )
                            flights.append(flight)
                            
                        except Exception as e:
                            logger.debug(f"Error parsing flight: {e}")
                            continue
            
        except Exception as e:
            logger.error(f"Error parsing API response: {e}")
        
        logger.info(f"Parsed {len(flights)} flights from United API")
        return flights
    
    # ============== Browser Method ==============
    
    async def _search_via_browser(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """Search using browser automation with human-like behavior"""
        
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
                # Navigate to search page
                search_url = f"{self.base_url}/en/us/book-flight/find-flights"
                
                if not await browser.navigate(search_url):
                    raise Exception("Failed to load search page")
                
                # Check for CAPTCHA immediately
                if browser.detect_captcha():
                    raise CaptchaError("CAPTCHA detected on page load")
                
                # Check for block
                if browser.detect_block_page():
                    raise BlockedError("Blocked on page load")
                
                # Random initial scroll
                browser.human_scroll(random.randint(50, 150))
                
                # Enable award travel
                await self._enable_award_travel(browser)
                
                # Fill origin
                await self._fill_airport(browser, "origin", origin)
                
                # Fill destination
                await self._fill_airport(browser, "destination", destination)
                
                # Set date
                await self._set_date(browser, departure_date)
                
                # Click search
                await self._click_search(browser)
                
                # Wait for results
                await self._wait_for_results(browser)
                
                # Check for CAPTCHA after search
                if browser.detect_captcha():
                    raise CaptchaError("CAPTCHA detected after search")
                
                # Parse results
                html = browser.get_page_source()
                return self._parse_html_response(html, origin, destination, departure_date)
                
        except (CaptchaError, BlockedError):
            raise
        except Exception as e:
            logger.error(f"United browser scraping failed: {e}")
            # Take screenshot for debugging
            try:
                browser.take_screenshot(f"logs/united_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            except:
                pass
            return []
    
    async def _enable_award_travel(self, browser: BrowserManager) -> None:
        """Enable award travel toggle"""
        element = browser.find_element_with_fallbacks(
            self._get_award_toggle_locators(),
            timeout=10,
            description="award toggle"
        )
        
        if element:
            try:
                if not element.is_selected():
                    browser.human_click(browser.driver, element)
                    browser.human_sleep(300, 600)
            except Exception as e:
                logger.debug(f"Award toggle interaction failed: {e}")
    
    async def _fill_airport(self, browser: BrowserManager, field_type: str, code: str) -> None:
        """Fill airport input with human-like typing"""
        locators = (
            self._get_origin_input_locators() 
            if field_type == "origin" 
            else self._get_destination_input_locators()
        )
        
        element = browser.find_element_with_fallbacks(
            locators,
            timeout=10,
            description=f"{field_type} input"
        )
        
        if element:
            browser.human_click(browser.driver, element)
            browser.human_sleep(200, 400)
            browser.human_type(element, code.upper())
            browser.human_sleep(500, 1000)
            
            # Press Enter to select first suggestion
            element.send_keys(Keys.ENTER)
            browser.human_sleep(300, 600)
    
    async def _set_date(self, browser: BrowserManager, departure_date: date) -> None:
        """Set departure date"""
        element = browser.find_element_with_fallbacks(
            self._get_date_input_locators(),
            timeout=10,
            description="date input"
        )
        
        if element:
            browser.human_click(browser.driver, element)
            browser.human_sleep(300, 600)
            
            # Try to input date directly or use date picker
            date_str = departure_date.strftime("%m/%d/%Y")
            try:
                element.clear()
                browser.human_type(element, date_str)
                element.send_keys(Keys.ENTER)
            except Exception:
                # Date picker may need different interaction
                pass
            
            browser.human_sleep(300, 600)
    
    async def _click_search(self, browser: BrowserManager) -> None:
        """Click search button"""
        element = browser.find_element_with_fallbacks(
            self._get_search_button_locators(),
            timeout=10,
            description="search button"
        )
        
        if element:
            browser.human_scroll(random.randint(100, 200))
            browser.human_sleep(200, 500)
            browser.human_click(browser.driver, element)
    
    async def _wait_for_results(self, browser: BrowserManager) -> None:
        """Wait for flight results to load"""
        element = browser.wait_for_any_element(
            self._get_flight_results_locators(),
            timeout=30
        )
        
        if not element:
            logger.warning("Flight results container not found")
        
        # Extra wait for dynamic content
        browser.human_sleep(1000, 2000)
    
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
            ".flight-result-card",
            "[class*='FlightCard']",
            ".flight-row",
            "[class*='flightResult']",
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
        
        logger.info(f"Parsed {len(flights)} flights from United HTML")
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
            ]
            flight_number = self._extract_text(card, flight_num_selectors) or "UA"
            
            # Extract times
            dep_time_selectors = [
                "[data-testid='departure-time']",
                ".departure-time",
                "[class*='departTime']",
            ]
            arr_time_selectors = [
                "[data-testid='arrival-time']",
                ".arrival-time", 
                "[class*='arrivalTime']",
            ]
            
            dep_time = self._extract_text(card, dep_time_selectors) or "00:00"
            arr_time = self._extract_text(card, arr_time_selectors) or "00:00"
            
            # Extract miles
            miles_selectors = [
                "[data-testid='miles-cost']",
                ".miles-cost",
                "[class*='miles']",
            ]
            miles_text = self._extract_text(card, miles_selectors) or "0"
            miles = self._parse_miles(miles_text)
            
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
                airline="United Airlines",
                flight_number=flight_number,
                departure_date=departure_date,
                departure_time=self._normalize_time(dep_time),
                arrival_time=self._normalize_time(arr_time),
                duration_minutes=0,  # Would need to calculate
                cabin_class=cabin,
                points_required=miles,
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
        if "first" in cabin_lower:
            return CabinClass.FIRST
        elif "business" in cabin_lower or "polaris" in cabin_lower:
            return CabinClass.BUSINESS
        elif "premium" in cabin_lower:
            return CabinClass.PREMIUM_ECONOMY
        return CabinClass.ECONOMY
    
    def _format_time(self, time_str: str) -> str:
        """Format time string to HH:MM"""
        try:
            if "T" in time_str:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                return dt.strftime("%H:%M")
            return time_str[:5] if len(time_str) >= 5 else time_str
        except Exception:
            return time_str
    
    def _normalize_time(self, time_str: str) -> str:
        """Normalize time string to HH:MM format"""
        try:
            # Remove AM/PM and normalize
            time_str = time_str.upper().replace("AM", "").replace("PM", "").strip()
            
            # Handle various formats
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
    
    def _parse_miles(self, miles_text: str) -> int:
        """Parse miles from text"""
        try:
            # Remove commas, 'K', 'miles', etc.
            cleaned = re.sub(r"[^\d]", "", miles_text)
            if cleaned:
                miles = int(cleaned)
                # Handle 'K' notation
                if "k" in miles_text.lower() and miles < 1000:
                    miles *= 1000
                return miles
        except Exception:
            pass
        return 0


# For backwards compatibility
import random
