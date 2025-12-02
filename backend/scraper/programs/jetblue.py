"""
JetBlue TrueBlue Scraper - Award Flight Availability

JetBlue has relatively lighter anti-bot measures compared to legacy carriers.
Supports routes to USA, Mexico, Caribbean, and select transatlantic.

Now uses Playwright with stealth for better bot evasion.
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Tuple
import hashlib
import re
import asyncio
import time

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
from config import settings

# Try Playwright first (preferred), fall back to Selenium
try:
    from scraper.playwright_browser import (
        PlaywrightStealthBrowser, 
        create_stealth_browser,
        HumanBehavior,
        HAS_PLAYWRIGHT
    )
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from scraper.browser import create_browser_manager, BrowserManager
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False


class JetBlueTrueBlueScraper(BaseScraper):
    """
    Scraper for JetBlue TrueBlue award availability.
    
    Features:
    - Direct website scraping
    - Points + cash pricing
    - Mint class (business) availability
    - Relatively lighter bot detection
    """
    
    @property
    def program_name(self) -> str:
        return "jetblue_trueblue"
    
    @property
    def program_display_name(self) -> str:
        return "JetBlue TrueBlue"
    
    @property
    def base_url(self) -> str:
        return "https://www.jetblue.com"
    
    @property
    def supported_airlines(self) -> List[str]:
        return ["B6"]  # JetBlue only
    
    # Cabin class mapping for JetBlue
    CABIN_MAP = {
        CabinClass.ECONOMY: "COACH",     # Blue Basic, Blue, Blue Plus
        CabinClass.PREMIUM_ECONOMY: "COACH",  # Blue Extra
        CabinClass.BUSINESS: "MINT",     # Mint
        CabinClass.FIRST: "MINT",        # Mint (no first class)
    }
    
    # JetBlue fare families
    FARE_FAMILIES = {
        "BLUE_BASIC": CabinClass.ECONOMY,
        "BLUE": CabinClass.ECONOMY,
        "BLUE_PLUS": CabinClass.ECONOMY,
        "BLUE_EXTRA": CabinClass.PREMIUM_ECONOMY,
        "MINT": CabinClass.BUSINESS,
    }
    
    # ============== Resilient Locators ==============
    
    def _get_origin_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for origin airport input"""
        return [
            (By.ID, "jb-autocomplete-1-search"),
            (By.CSS_SELECTOR, "[data-qaid='depart']"),
            (By.CSS_SELECTOR, "input[placeholder*='From']"),
            (By.CSS_SELECTOR, "[aria-label*='From']"),
            (By.CSS_SELECTOR, ".origin-input input"),
            (By.XPATH, "//input[contains(@placeholder, 'city') and contains(@placeholder, 'from')]"),
        ]
    
    def _get_destination_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for destination airport input"""
        return [
            (By.ID, "jb-autocomplete-2-search"),
            (By.CSS_SELECTOR, "[data-qaid='arrive']"),
            (By.CSS_SELECTOR, "input[placeholder*='To']"),
            (By.CSS_SELECTOR, "[aria-label*='To']"),
            (By.CSS_SELECTOR, ".destination-input input"),
            (By.XPATH, "//input[contains(@placeholder, 'city') and contains(@placeholder, 'to')]"),
        ]
    
    def _get_date_input_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for departure date"""
        return [
            (By.CSS_SELECTOR, "[data-qaid='departCalendarTrigger']"),
            (By.CSS_SELECTOR, "button[aria-label*='depart']"),
            (By.CSS_SELECTOR, ".depart-date-trigger"),
            (By.XPATH, "//button[contains(@aria-label, 'Depart')]"),
        ]
    
    def _get_points_toggle_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for TrueBlue points toggle"""
        return [
            (By.CSS_SELECTOR, "[data-qaid='usePoints']"),
            (By.CSS_SELECTOR, "input[name='usePoints']"),
            (By.XPATH, "//label[contains(text(), 'Use TrueBlue points')]"),
            (By.CSS_SELECTOR, "[aria-label*='TrueBlue']"),
            (By.ID, "usePoints"),
        ]
    
    def _get_search_button_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for search button"""
        return [
            (By.CSS_SELECTOR, "[data-qaid='searchFlightsBtn']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Search flights')]"),
            (By.CSS_SELECTOR, ".search-submit"),
        ]
    
    def _get_flight_card_locators(self) -> List[Tuple[Any, str]]:
        """Get locators for flight result cards"""
        return [
            (By.CSS_SELECTOR, "[data-qaid='flightCard']"),
            (By.CSS_SELECTOR, ".flight-result-card"),
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
        Search for TrueBlue award availability.
        
        Uses Playwright stealth first (better evasion), 
        falls back to Selenium if not available.
        """
        logger.info(f"Searching JetBlue TrueBlue: {origin} → {destination} on {departure_date}")
        
        # Try Playwright stealth first (preferred)
        if HAS_PLAYWRIGHT:
            try:
                results = await self._search_via_playwright(
                    origin, destination, departure_date, cabin_class, passengers
                )
                if results:
                    return results
            except Exception as e:
                logger.warning(f"Playwright search failed, trying Selenium: {e}")
        
        # Fall back to Selenium
        if HAS_SELENIUM:
            try:
                results = await self._search_via_selenium(
                    origin, destination, departure_date, cabin_class, passengers
                )
                return results
            except CaptchaError:
                logger.error("CAPTCHA encountered on JetBlue")
                raise
            except BlockedError:
                logger.error("Blocked by JetBlue")
                raise
        
        logger.error("No browser automation available (install playwright or selenium)")
        return []
    
    # ============== Playwright Stealth Search (Preferred) ==============
    
    async def _search_via_playwright(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """Search using Playwright with stealth patches (async version)"""
        from scraper.playwright_browser import AsyncPlaywrightStealthBrowser, StealthConfig
        
        browser = None
        try:
            # Create async stealth browser configured for JetBlue
            config = StealthConfig(
                headless=getattr(settings, 'jetblue_headless', False),
                min_delay=2.0,
                max_delay=6.0,
                locale="en-US",
                timezone="America/New_York",
                page_load_timeout=90000
            )
            
            browser = AsyncPlaywrightStealthBrowser(config)
            await browser.start()
            
            page = await browser.new_page()
            
            # Build search URL
            search_url = self._build_search_url(origin, destination, departure_date, passengers)
            logger.debug(f"JetBlue search URL: {search_url}")
            
            # Navigate to search page
            await page.goto(search_url, wait_until='domcontentloaded', timeout=90000)
            
            # Wait for initial page load
            await asyncio.sleep(3)
            
            # Handle cookie consent popup (TrustArc)
            await self._handle_cookie_consent(page)
            
            # Check for blocks early
            html = await page.content()
            html_lower = html.lower()
            
            if 'px-captcha' in html_lower or 'perimeterx' in html_lower:
                raise CaptchaError("PerimeterX CAPTCHA detected on JetBlue")
            if 'access denied' in html_lower:
                raise BlockedError("Blocked by JetBlue")
            
            # Wait for flight results to load - JetBlue uses .flight-result-item
            # Also check for "no flights" or error messages
            logger.debug("Waiting for JetBlue flight results to load...")
            
            try:
                # Wait for either flight results OR no flights message
                await page.wait_for_selector(
                    '.flight-result-item, .no-flights-found, [class*="NoFlights"], .error-message',
                    timeout=30000
                )
            except Exception as e:
                logger.debug(f"Initial selector wait timed out: {e}")
            
            # Additional wait for all results to load
            await asyncio.sleep(5)
            
            # Scroll to trigger lazy loading
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
            await asyncio.sleep(2)
            
            # Get final HTML
            html = await page.content()
            
            # Count what we found
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            flight_cards = soup.select('.flight-result-item')
            logger.debug(f"Found {len(flight_cards)} .flight-result-item elements")
            
            # Parse results
            results = self._parse_results(
                html, origin, destination, departure_date, cabin_class
            )
            
            logger.info(f"Found {len(results)} JetBlue flights via Playwright")
            return results
            
        finally:
            if browser:
                await browser.close()
    
    async def _handle_cookie_consent(self, page) -> None:
        """Handle TrustArc cookie consent popup on JetBlue"""
        try:
            logger.debug("Checking for cookie consent popup...")
            
            # Wait briefly to see if popup appears
            await asyncio.sleep(2)
            
            # Try multiple selectors for the Accept button
            accept_selectors = [
                'a.call:has-text("Accept All Cookies")',  # Primary TrustArc button
                'a.call[role="button"]',  # Fallback - the "call" class button
                'text="Accept All Cookies"',
                '.pdynamicbutton a.call',
                '[aria-modal="true"] a.call',
            ]
            
            for selector in accept_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.is_visible(timeout=2000):
                        logger.debug(f"Found cookie consent button with selector: {selector}")
                        await button.click()
                        logger.info("Cookie consent accepted")
                        await asyncio.sleep(1)  # Wait for popup to close
                        return
                except Exception:
                    continue
            
            # Alternative: Try to remove the overlay via JavaScript
            try:
                # Check if TrustArc overlay exists
                overlay_exists = await page.evaluate('''() => {
                    const overlay = document.querySelector('[aria-modal="true"]');
                    return overlay !== null;
                }''')
                
                if overlay_exists:
                    logger.debug("Removing cookie overlay via JavaScript")
                    await page.evaluate('''() => {
                        // Remove the modal overlay
                        const modal = document.querySelector('[aria-modal="true"]');
                        if (modal) modal.remove();
                        
                        // Remove any backdrop/overlay
                        const overlays = document.querySelectorAll('.truste_overlay, .truste_box_overlay, [class*="overlay"]');
                        overlays.forEach(el => el.remove());
                        
                        // Re-enable body scrolling
                        document.body.style.overflow = 'auto';
                    }''')
                    logger.info("Cookie overlay removed via JS")
                    await asyncio.sleep(1)
            except Exception as e:
                logger.debug(f"JS overlay removal failed: {e}")
            
            logger.debug("No cookie consent popup found or already dismissed")
            
        except Exception as e:
            logger.debug(f"Cookie consent handling error (non-fatal): {e}")
    
    # ============== Selenium Fallback ==============
    
    async def _search_via_selenium(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass],
        passengers: int
    ) -> List[FlightAvailability]:
        """Search using Selenium (fallback)"""
        
        if not HAS_SELENIUM:
            raise RuntimeError("Selenium not installed")
        
        browser = None
        driver = None
        
        try:
            # Create browser manager
            browser = create_browser_manager(program=self.program_name)
            
            driver = browser.create_driver()
            if not driver:
                raise RuntimeError("Failed to create browser driver")
            
            # Build search URL with parameters
            search_url = self._build_search_url(origin, destination, departure_date, passengers)
            logger.debug(f"JetBlue search URL: {search_url}")
            
            # Navigate with human-like behavior
            driver.get(search_url)
            await browser.human_delay(2, 4)
            
            # Check for blocks/captcha
            self._check_for_blocks(driver)
            
            # Wait for results to load
            await self._wait_for_results(driver, browser)
            
            # Parse results
            results = self._parse_results(
                driver.page_source, 
                origin, 
                destination, 
                departure_date,
                cabin_class
            )
            
            logger.info(f"Found {len(results)} JetBlue flights")
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
        """
        Build JetBlue search URL.
        
        Note: Points/award search requires TrueBlue login.
        For now, we scrape cash fares which work without authentication.
        URL params usePoints=true and redemPoint=true can be added when
        logged in session is available.
        """
        date_str = departure_date.strftime("%Y-%m-%d")
        
        # JetBlue URL format - basic search (no login required)
        url = (
            f"{self.base_url}/booking/flights"
            f"?from={origin}"
            f"&to={destination}"
            f"&depart={date_str}"
            f"&isMultiCity=false"
            f"&noOfRoute=1"
            f"&lang=en"
            f"&adults={passengers}"
            f"&children=0"
            f"&infants=0"
            f"&fareFamily=any"
        )
        
        return url
    
    def _check_for_blocks(self, driver) -> None:
        """Check if we're blocked or facing CAPTCHA"""
        html = driver.page_source.lower()
        
        block_indicators = [
            "captcha",
            "challenge",
            "blocked",
            "access denied",
            "please verify",
            "security check",
        ]
        
        for indicator in block_indicators:
            if indicator in html:
                if "captcha" in indicator or "challenge" in indicator:
                    raise CaptchaError(f"CAPTCHA detected on JetBlue")
                raise BlockedError(f"Blocked by JetBlue: {indicator}")
    
    async def _wait_for_results(self, driver, browser: BrowserManager) -> None:
        """Wait for flight results to load"""
        try:
            wait = WebDriverWait(driver, 15)
            
            # Wait for either results or no-flights message
            wait.until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, 
                    "[data-qaid='flightCard'], .no-flights, .flight-results, .error-message"
                ))
            )
            
            # Additional wait for dynamic content
            await browser.human_delay(2, 3)
            
        except Exception as e:
            logger.warning(f"Timeout waiting for JetBlue results: {e}")
    
    # ============== Result Parsing ==============
    
    def _parse_results(
        self,
        html: str,
        origin: str,
        destination: str,
        departure_date: date,
        filter_cabin: Optional[CabinClass] = None
    ) -> List[FlightAvailability]:
        """Parse flight results from JetBlue page"""
        soup = BeautifulSoup(html, 'html.parser')
        flights = []
        
        # Find flight cards - JetBlue uses .flight-result-item class
        flight_cards = soup.select('.flight-result-item')
        
        if not flight_cards:
            # Fallback selectors
            flight_cards = soup.select('[data-qaid="flightCard"], .flight-result-card, .flight-option')
        
        if not flight_cards:
            # Try alternative selectors
            flight_cards = soup.find_all('div', class_=re.compile(r'flight-result', re.I))
        
        logger.debug(f"Found {len(flight_cards)} flight cards in HTML")
        
        for card in flight_cards:
            try:
                flight = self._parse_flight_card(card, origin, destination, departure_date)
                if flight:
                    # Apply cabin filter if specified
                    if filter_cabin and flight.cabin_class != filter_cabin:
                        continue
                    flights.append(flight)
            except Exception as e:
                logger.warning(f"Failed to parse JetBlue flight card: {e}")
                continue
        
        return flights
    
    def _parse_flight_card(
        self,
        card: BeautifulSoup,
        origin: str,
        destination: str,
        departure_date: date
    ) -> Optional[FlightAvailability]:
        """Parse a single flight card from JetBlue results"""
        
        # Extract flight number - JetBlue shows it in .flight-duration__button span
        # Format: "B6 583" or in flight-duration area
        flight_number = "B6????"
        flight_num_elem = card.select_one('.flight-duration__button span')
        if flight_num_elem:
            text = flight_num_elem.get_text(strip=True)
            match = re.search(r'B6\s*(\d+)', text)
            if match:
                flight_number = f"B6{match.group(1)}"
        else:
            # Fallback: search the whole card text
            card_text = card.get_text()
            match = re.search(r'B6\s*(\d+)', card_text)
            if match:
                flight_number = f"B6{match.group(1)}"
        
        # Extract times - JetBlue puts them in .flight-times__item .core-blue.body
        # Format: "5:45am", "4:24pm"
        departure_time = "00:00"
        arrival_time = "00:00"
        
        time_elems = card.select('.flight-times__item .core-blue.body')
        if len(time_elems) >= 2:
            departure_time = self._parse_time(time_elems[0].get_text(strip=True))
            arrival_time = self._parse_time(time_elems[1].get_text(strip=True))
        else:
            # Fallback: look for any time pattern in the card
            card_text = card.get_text()
            time_matches = re.findall(r'\d{1,2}:\d{2}\s*(?:am|pm)', card_text, re.I)
            if len(time_matches) >= 2:
                departure_time = self._parse_time(time_matches[0])
                arrival_time = self._parse_time(time_matches[1])
        
        # Extract duration - .flight-duration__time shows "10h 39m" or "5h 52m"
        duration_elem = card.select_one('.flight-duration__time')
        duration_minutes = 0
        if duration_elem:
            duration_minutes = self._parse_duration(duration_elem.get_text(strip=True))
        else:
            # Fallback: look for duration pattern
            card_text = card.get_text()
            match = re.search(r'(\d+)h\s*(\d+)m', card_text)
            if match:
                duration_minutes = int(match.group(1)) * 60 + int(match.group(2))
        
        # Extract points price
        # Note: Points search may require login. Check for points or cash price
        points = 0
        cash_price = 0.0
        
        # Try to find points price first
        points_elem = card.select_one('.points-price, [class*="points"]')
        if points_elem:
            text = points_elem.get_text(strip=True)
            points = self._extract_points(text)
        
        # If no points, get cash price from .cb-bundle-price__price span
        if points == 0:
            cash_elem = card.select_one('.cb-bundle-price__price span')
            if cash_elem:
                text = cash_elem.get_text(strip=True)
                cash_price = self._extract_currency(text)
            
            # Fallback: look for $XXX pattern
            if cash_price == 0:
                card_text = card.get_text()
                match = re.search(r'\$(\d{1,3}(?:,\d{3})*)', card_text)
                if match:
                    cash_price = float(match.group(1).replace(',', ''))
        
        # If we have cash price but no points, estimate points value
        # JetBlue typically values points at ~1.3 cents each
        if points == 0 and cash_price > 0:
            # Cash fares found - store the cash value, we'll note points are unavailable
            points = 0  # Leave as 0 to indicate cash-only fare
        
        # Search for any number that looks like points in card
        if points == 0:
            card_text = card.get_text()
            match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*(?:points|pts)', card_text, re.I)
            if match:
                points = int(match.group(1).replace(',', ''))
        
        # Extract taxes/fees
        taxes_elem = card.select_one('.taxes, .fees, [class*="tax"]')
        taxes = 5.60  # Default JetBlue tax
        if taxes_elem:
            taxes = self._extract_currency(taxes_elem.get_text(strip=True))
        
        # Determine cabin class - look for Mint designation
        # .body.mb0.core-blue b contains "Economy" or cabin info
        cabin_class = CabinClass.ECONOMY
        cabin_elem = card.select_one('.body.mb0.core-blue b')
        if cabin_elem:
            cabin_text = cabin_elem.get_text(strip=True).lower()
            if 'mint' in cabin_text:
                cabin_class = CabinClass.BUSINESS
            elif 'even more space' in cabin_text or 'extra' in cabin_text:
                cabin_class = CabinClass.PREMIUM_ECONOMY
        
        # Also check for Mint class marker
        if card.select_one('[class*="mint"]') or 'mint' in card.get_text().lower():
            if cabin_class == CabinClass.ECONOMY:
                # Only upgrade if we detect Mint
                card_text = card.get_text().lower()
                if 'mint class' in card_text or 'mint lie-flat' in card_text:
                    cabin_class = CabinClass.BUSINESS
        
        # Extract stops - .flight-duration__button may show "1 stop" info
        stops = 0
        card_text = card.get_text().lower()
        if 'nonstop' in card_text or 'direct' in card_text:
            stops = 0
        elif '1 stop' in card_text:
            stops = 1
        elif '2 stop' in card_text:
            stops = 2
        elif '3 stop' in card_text:
            stops = 3
        else:
            # Check for multiple flight numbers (indicates connection)
            flight_matches = re.findall(r'B6\s*\d+', card.get_text())
            if len(flight_matches) > 1:
                stops = len(flight_matches) - 1
        
        # Skip cards that don't look like valid flight results
        if departure_time == "00:00" and arrival_time == "00:00" and duration_minutes == 0:
            # Probably not a flight card
            return None
        
        # Generate unique ID
        flight_id = hashlib.md5(
            f"{self.program_name}:{flight_number}:{origin}:{destination}:{departure_date}:{cabin_class.value}:{departure_time}".encode()
        ).hexdigest()[:12]
        
        return FlightAvailability(
            id=flight_id,
            source_program=self.program_name,
            origin=origin,
            destination=destination,
            airline="B6",
            flight_number=flight_number,
            departure_date=departure_date,
            departure_time=departure_time,
            arrival_time=arrival_time,
            duration_minutes=duration_minutes,
            cabin_class=cabin_class,
            points_required=points,
            cash_price=cash_price,  # Store cash price when available
            taxes_fees=taxes,
            seats_available=1,  # JetBlue doesn't always show seat count
            stops=stops,
            connection_airports=[],
            scraped_at=datetime.utcnow(),
            raw_data={
                "html_snippet": str(card)[:500],
                "points_available": points > 0,
                "cash_fare_found": cash_price > 0,
            }
        )
    
    # ============== Helper Methods ==============
    
    def _parse_time(self, text: str) -> str:
        """Parse time string to HH:MM format"""
        # Handle formats like "6:45am", "11:30 PM", etc.
        match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', text, re.I)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            period = match.group(3)
            
            if period:
                if period.lower() == 'pm' and hour != 12:
                    hour += 12
                elif period.lower() == 'am' and hour == 12:
                    hour = 0
            
            return f"{hour:02d}:{minute:02d}"
        return "00:00"
    
    def _parse_duration(self, text: str) -> int:
        """Parse duration string to minutes"""
        total = 0
        
        # Match hours
        hours_match = re.search(r'(\d+)\s*h', text, re.I)
        if hours_match:
            total += int(hours_match.group(1)) * 60
        
        # Match minutes
        mins_match = re.search(r'(\d+)\s*m', text, re.I)
        if mins_match:
            total += int(mins_match.group(1))
        
        return total
    
    def _extract_points(self, text: str) -> int:
        """Extract points value from text"""
        # Remove commas and find numbers
        text = text.replace(',', '')
        match = re.search(r'(\d+)', text)
        if match:
            return int(match.group(1))
        return 0
    
    def _extract_currency(self, text: str) -> float:
        """Extract currency value from text"""
        match = re.search(r'\$?\s*(\d+(?:\.\d{2})?)', text)
        if match:
            return float(match.group(1))
        return 0.0
