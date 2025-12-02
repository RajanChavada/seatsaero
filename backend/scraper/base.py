"""
Base Scraper - Abstract base class with rate limiting, retries, and human-like behavior
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable, Tuple
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import asyncio
import random
import time
import hashlib

from loguru import logger

from config import settings


class CabinClass(str, Enum):
    """Cabin class enumeration"""
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


class ScrapeError(Exception):
    """Base exception for scraper errors"""
    pass


class RateLimitError(ScrapeError):
    """Raised when rate limited by the target site"""
    pass


class CaptchaError(ScrapeError):
    """Raised when CAPTCHA is detected"""
    pass


class BlockedError(ScrapeError):
    """Raised when blocked by WAF or bot detection"""
    pass


class SessionExpiredError(ScrapeError):
    """Raised when session is expired or invalid"""
    pass


@dataclass
class ScrapeResult:
    """Result of a scrape operation with metadata"""
    success: bool
    flights: List["FlightAvailability"] = field(default_factory=list)
    error: Optional[str] = None
    error_type: Optional[str] = None  # rate_limit, captcha, blocked, timeout, etc.
    retry_after: Optional[int] = None  # Seconds to wait before retry
    proxy_id: Optional[str] = None
    duration_ms: int = 0


@dataclass
class FlightAvailability:
    """Normalized flight availability data model"""
    # Identifiers
    id: str
    source_program: str
    
    # Route Information
    origin: str
    destination: str
    
    # Flight Details
    airline: str
    flight_number: str
    departure_date: date
    departure_time: str
    arrival_time: str
    duration_minutes: int
    
    # Award Details
    cabin_class: CabinClass
    points_required: int
    taxes_fees: float
    seats_available: int = 0
    cash_price: float = 0.0  # Cash fare when points not available
    
    # Routing
    stops: int = 0
    connection_airports: List[str] = field(default_factory=list)
    
    # Metadata
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set expiry time if not set"""
        if self.expires_at is None:
            self.expires_at = self.scraped_at + timedelta(hours=settings.data_expiry_hours)
    
    def is_expired(self) -> bool:
        """Check if the data is expired"""
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "source_program": self.source_program,
            "origin": self.origin,
            "destination": self.destination,
            "airline": self.airline,
            "flight_number": self.flight_number,
            "departure_date": self.departure_date.isoformat(),
            "departure_time": self.departure_time,
            "arrival_time": self.arrival_time,
            "duration_minutes": self.duration_minutes,
            "cabin_class": self.cabin_class.value,
            "points_required": self.points_required,
            "taxes_fees": self.taxes_fees,
            "seats_available": self.seats_available,
            "stops": self.stops,
            "connection_airports": self.connection_airports,
            "scraped_at": self.scraped_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class RateLimiter:
    """
    Per-program rate limiter with sliding window.
    
    Features:
    - Sliding window rate limiting
    - Exponential backoff on errors
    - Per-program limits
    """
    
    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self._requests: List[datetime] = []
        self._lock = asyncio.Lock()
        self._backoff_until: Optional[datetime] = None
        self._consecutive_errors = 0
    
    async def acquire(self) -> bool:
        """
        Acquire permission to make a request.
        
        Returns:
            True if request allowed, False if should wait
        """
        async with self._lock:
            now = datetime.utcnow()
            
            # Check backoff
            if self._backoff_until and now < self._backoff_until:
                wait_secs = (self._backoff_until - now).total_seconds()
                logger.debug(f"Rate limiter in backoff for {wait_secs:.1f}s")
                await asyncio.sleep(wait_secs)
            
            # Clean old requests outside the window
            window_start = now - timedelta(minutes=1)
            self._requests = [r for r in self._requests if r > window_start]
            
            # Check if at limit
            if len(self._requests) >= self.requests_per_minute:
                oldest = self._requests[0]
                wait_secs = (oldest + timedelta(minutes=1) - now).total_seconds()
                if wait_secs > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_secs:.1f}s")
                    await asyncio.sleep(wait_secs)
            
            # Record request
            self._requests.append(now)
            return True
    
    def record_success(self) -> None:
        """Record a successful request"""
        self._consecutive_errors = 0
        self._backoff_until = None
    
    def record_error(self, error_type: str = "unknown") -> None:
        """
        Record an error and apply backoff.
        
        Args:
            error_type: Type of error (rate_limit, captcha, blocked)
        """
        self._consecutive_errors += 1
        
        # Calculate backoff with jitter
        base_delay = settings.base_retry_delay_secs
        backoff = base_delay * (2 ** min(self._consecutive_errors, 6))  # Cap at 64x
        jitter = random.uniform(0.5, 1.5)
        delay = backoff * jitter
        
        # Longer backoff for certain errors
        if error_type == "captcha":
            delay *= 2
        elif error_type == "blocked":
            delay *= 3
        
        self._backoff_until = datetime.utcnow() + timedelta(seconds=delay)
        logger.warning(f"Rate limiter backoff: {delay:.1f}s (errors: {self._consecutive_errors})")
    
    @property
    def is_in_backoff(self) -> bool:
        """Check if currently in backoff period"""
        if self._backoff_until is None:
            return False
        return datetime.utcnow() < self._backoff_until


# Global rate limiters per program
_rate_limiters: Dict[str, RateLimiter] = {}


def get_rate_limiter(program: str) -> RateLimiter:
    """Get or create rate limiter for a program"""
    if program not in _rate_limiters:
        limit = settings.get_program_rate_limit(program)
        _rate_limiters[program] = RateLimiter(requests_per_minute=limit)
    return _rate_limiters[program]


class BaseScraper(ABC):
    """
    Abstract base class for all loyalty program scrapers.
    
    Features:
    - Rate limiting per program
    - Exponential backoff with retries
    - Human-like interaction helpers
    - CAPTCHA and block detection
    - Proxy and session management
    """
    
    def __init__(self, browser_manager=None, proxy_rotator=None, useragent_rotator=None):
        self.browser_manager = browser_manager
        self.proxy_rotator = proxy_rotator
        self.useragent_rotator = useragent_rotator
        self._session_cookies: Dict[str, str] = {}
        self._last_request_time: Optional[datetime] = None
        self._rate_limiter: Optional[RateLimiter] = None
        self._current_proxy_id: Optional[str] = None
    
    @property
    def rate_limiter(self) -> RateLimiter:
        """Get rate limiter for this scraper"""
        if self._rate_limiter is None:
            self._rate_limiter = get_rate_limiter(self.program_name)
        return self._rate_limiter
    
    @property
    @abstractmethod
    def program_name(self) -> str:
        """Return the loyalty program identifier (e.g., 'united_mileageplus')"""
        pass
    
    @property
    @abstractmethod
    def program_display_name(self) -> str:
        """Return human-readable program name (e.g., 'United MileagePlus')"""
        pass
    
    @property
    @abstractmethod
    def base_url(self) -> str:
        """Return the base URL for the loyalty program website"""
        pass
    
    @property
    @abstractmethod
    def supported_airlines(self) -> List[str]:
        """Return list of airline codes searchable through this program"""
        pass
    
    @abstractmethod
    async def search_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[CabinClass] = None,
        passengers: int = 1
    ) -> List[FlightAvailability]:
        """
        Search for award availability on a specific route/date.
        """
        pass
    
    # ============== Retry Wrapper ==============
    
    async def with_retry(
        self,
        operation: Callable,
        *args,
        max_retries: int = None,
        **kwargs
    ) -> ScrapeResult:
        """
        Execute operation with retry logic and error handling.
        
        Args:
            operation: Async function to execute
            max_retries: Override max retries
            
        Returns:
            ScrapeResult with success/failure info
        """
        max_retries = max_retries or settings.max_retries_per_job
        last_error = None
        
        for attempt in range(max_retries + 1):
            start_time = time.time()
            
            try:
                # Acquire rate limit
                await self.rate_limiter.acquire()
                
                # Execute operation
                result = await operation(*args, **kwargs)
                
                # Success
                self.rate_limiter.record_success()
                duration_ms = int((time.time() - start_time) * 1000)
                
                return ScrapeResult(
                    success=True,
                    flights=result if isinstance(result, list) else [],
                    duration_ms=duration_ms,
                    proxy_id=self._current_proxy_id
                )
                
            except CaptchaError as e:
                last_error = str(e)
                self.rate_limiter.record_error("captcha")
                logger.warning(f"CAPTCHA detected (attempt {attempt + 1}/{max_retries + 1})")
                
                # Mark proxy as hot if using one
                if self._current_proxy_id:
                    from scraper.proxy import get_proxy_pool
                    get_proxy_pool().mark_hot(self.program_name, self._current_proxy_id)
                
                if attempt < max_retries:
                    await self._backoff_sleep(attempt, "captcha")
                    
            except RateLimitError as e:
                last_error = str(e)
                self.rate_limiter.record_error("rate_limit")
                logger.warning(f"Rate limited (attempt {attempt + 1}/{max_retries + 1})")
                
                if attempt < max_retries:
                    await self._backoff_sleep(attempt, "rate_limit")
                    
            except BlockedError as e:
                last_error = str(e)
                self.rate_limiter.record_error("blocked")
                logger.warning(f"Blocked (attempt {attempt + 1}/{max_retries + 1})")
                
                # Mark proxy as hot
                if self._current_proxy_id:
                    from scraper.proxy import get_proxy_pool
                    get_proxy_pool().mark_hot(self.program_name, self._current_proxy_id)
                
                if attempt < max_retries:
                    await self._backoff_sleep(attempt, "blocked")
                    
            except Exception as e:
                last_error = str(e)
                self.rate_limiter.record_error("unknown")
                logger.error(f"Scrape error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                
                if attempt < max_retries:
                    await self._backoff_sleep(attempt)
        
        # All retries exhausted
        duration_ms = int((time.time() - start_time) * 1000)
        return ScrapeResult(
            success=False,
            error=last_error,
            error_type="max_retries_exceeded",
            duration_ms=duration_ms,
            proxy_id=self._current_proxy_id
        )
    
    async def _backoff_sleep(self, attempt: int, error_type: str = "unknown") -> None:
        """Sleep with exponential backoff"""
        base = settings.base_retry_delay_secs
        delay = base * (2 ** attempt) * random.uniform(0.5, 1.5)
        
        if error_type == "captcha":
            delay *= 2
        elif error_type == "blocked":
            delay *= 3
        
        logger.debug(f"Backing off for {delay:.1f}s before retry")
        await asyncio.sleep(delay)
    
    # ============== Human-like Behavior Helpers ==============
    
    @staticmethod
    def human_sleep(min_ms: int = None, max_ms: int = None) -> None:
        """Sleep for random human-like duration (synchronous)"""
        min_ms = min_ms or settings.human_delay_min_ms
        max_ms = max_ms or settings.human_delay_max_ms
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        time.sleep(delay)
    
    @staticmethod
    async def human_sleep_async(min_ms: int = None, max_ms: int = None) -> None:
        """Sleep for random human-like duration (async)"""
        min_ms = min_ms or settings.human_delay_min_ms
        max_ms = max_ms or settings.human_delay_max_ms
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        await asyncio.sleep(delay)
    
    @staticmethod
    def jittered_sleep(base_ms: int, jitter_pct: float = 0.3) -> None:
        """Sleep with jitter around a base duration"""
        jitter = base_ms * jitter_pct
        delay = base_ms + random.uniform(-jitter, jitter)
        time.sleep(max(0, delay / 1000))
    
    # ============== Browser Interaction Helpers ==============
    
    def human_click(self, driver, element) -> None:
        """Click element with human-like behavior"""
        from selenium.webdriver.common.action_chains import ActionChains
        
        # Scroll into view
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
            element
        )
        self.human_sleep(200, 500)
        
        # Move to element with offset
        actions = ActionChains(driver)
        offset_x = random.randint(-3, 3)
        offset_y = random.randint(-3, 3)
        actions.move_to_element_with_offset(element, offset_x, offset_y).perform()
        self.human_sleep(50, 150)
        
        # Click
        element.click()
    
    def human_type(self, element, text: str, clear_first: bool = True) -> None:
        """Type text with human-like speed"""
        if clear_first:
            element.clear()
            self.human_sleep(50, 150)
        
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.03, 0.12))
            
            # Occasional pause
            if random.random() < 0.05:
                time.sleep(random.uniform(0.2, 0.5))
    
    def human_scroll(self, driver, pixels: int = None, direction: str = "down") -> None:
        """Scroll with human-like behavior"""
        if pixels is None:
            pixels = random.randint(200, 500)
        
        if direction == "up":
            pixels = -pixels
        
        driver.execute_script(f"""
            window.scrollBy({{
                top: {pixels},
                behavior: 'smooth'
            }});
        """)
        self.human_sleep(
            settings.scroll_delay_min_ms,
            settings.scroll_delay_max_ms
        )
    
    # ============== Detection Helpers ==============
    
    def detect_captcha_page(self, driver) -> bool:
        """
        Detect if current page has CAPTCHA.
        
        Returns:
            True if CAPTCHA detected
        """
        from selenium.webdriver.common.by import By
        
        captcha_indicators = [
            (By.CSS_SELECTOR, "iframe[src*='recaptcha']"),
            (By.CSS_SELECTOR, ".g-recaptcha"),
            (By.CSS_SELECTOR, "iframe[src*='hcaptcha']"),
            (By.CSS_SELECTOR, ".h-captcha"),
            (By.CSS_SELECTOR, "iframe[src*='challenges.cloudflare']"),
            (By.ID, "challenge-running"),
            (By.XPATH, "//*[contains(text(), 'verify you are human')]"),
            (By.XPATH, "//*[contains(text(), 'security check')]"),
        ]
        
        for by, value in captcha_indicators:
            try:
                elements = driver.find_elements(by, value)
                if elements:
                    logger.warning(f"CAPTCHA detected: {value}")
                    return True
            except Exception:
                continue
        
        # Check page source
        try:
            source = driver.page_source.lower()
            if any(p in source for p in ["captcha", "challenge-running", "verify you are human"]):
                return True
        except Exception:
            pass
        
        return False
    
    def detect_block_page(self, driver) -> bool:
        """
        Detect if blocked (403, 429, WAF).
        
        Returns:
            True if blocked
        """
        try:
            title = driver.title.lower()
            source = driver.page_source.lower()
            
            block_indicators = [
                "403 forbidden",
                "429 too many",
                "access denied",
                "request blocked",
                "rate limit",
            ]
            
            for indicator in block_indicators:
                if indicator in title or indicator in source:
                    logger.warning(f"Block detected: {indicator}")
                    return True
        except Exception:
            pass
        
        return False
    
    def check_http_status(self, status_code: int) -> None:
        """Check HTTP status and raise appropriate error"""
        if status_code == 429:
            raise RateLimitError(f"Rate limited: HTTP {status_code}")
        elif status_code == 403:
            raise BlockedError(f"Blocked: HTTP {status_code}")
        elif status_code == 428:
            raise BlockedError(f"Precondition required (bot detection): HTTP {status_code}")
        elif status_code >= 400:
            raise ScrapeError(f"HTTP error: {status_code}")
    
    # ============== Utility Methods ==============
    
    async def search_date_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        cabin_class: Optional[CabinClass] = None
    ) -> List[FlightAvailability]:
        """Search availability across a date range"""
        results = []
        current_date = start_date
        
        while current_date <= end_date:
            try:
                day_results = await self.search_availability(
                    origin=origin,
                    destination=destination,
                    departure_date=current_date,
                    cabin_class=cabin_class
                )
                results.extend(day_results)
            except Exception as e:
                logger.error(f"Error searching {current_date}: {e}")
            
            current_date += timedelta(days=1)
            await self._rate_limit_delay()
        
        return results
    
    async def health_check(self) -> bool:
        """Verify scraper can connect to the website"""
        try:
            logger.info(f"Health check for {self.program_name}")
            return True
        except Exception as e:
            logger.error(f"Health check failed for {self.program_name}: {e}")
            return False
    
    async def _rate_limit_delay(self) -> None:
        """Apply rate limiting delay"""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            min_delay = settings.scrape_delay_min
            max_delay = settings.scrape_delay_max
            
            target_delay = random.uniform(min_delay, max_delay)
            
            if elapsed < target_delay:
                sleep_time = target_delay - elapsed
                await asyncio.sleep(sleep_time)
        
        self._last_request_time = datetime.utcnow()
    
    def _generate_flight_id(self, flight_number: str, departure_date: date, cabin: str) -> str:
        """Generate unique ID for a flight"""
        unique_string = f"{self.program_name}:{flight_number}:{departure_date}:{cabin}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:16]
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Get proxy configuration if enabled"""
        if self.proxy_rotator and settings.proxy_enabled:
            return self.proxy_rotator.get_next()
        return None
    
    def get_user_agent(self) -> str:
        """Get randomized user agent"""
        if self.useragent_rotator:
            return self.useragent_rotator.get_random()
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    def get_headers(self) -> Dict[str, str]:
        """Get request headers"""
        return {
            "User-Agent": self.get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
