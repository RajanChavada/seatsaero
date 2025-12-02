"""
Playwright Stealth Browser - Advanced anti-detection browser automation

Uses Playwright with stealth patches for better evasion of:
- Cloudflare
- PerimeterX  
- DataDome
- Akamai Bot Manager

Features:
- Human-like mouse movements
- Random delays and scrolling
- Fingerprint randomization
- Non-headless mode for best results
"""
import asyncio
import random
import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import math

from loguru import logger

try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    from playwright.async_api import async_playwright, Page as AsyncPage
    from playwright_stealth import Stealth
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("Playwright not installed. Run: pip install playwright playwright-stealth")


@dataclass
class StealthConfig:
    """Configuration for stealth browser"""
    headless: bool = False  # Non-headless evades better
    slow_mo: int = 50  # Milliseconds to slow down operations
    
    # Viewport randomization
    viewport_width: int = field(default_factory=lambda: random.randint(1280, 1920))
    viewport_height: int = field(default_factory=lambda: random.randint(800, 1080))
    
    # Timing
    min_delay: float = 2.0  # Minimum delay between actions
    max_delay: float = 8.0  # Maximum delay
    page_load_timeout: int = 30000  # 30 seconds
    
    # Human behavior
    enable_mouse_movement: bool = True
    enable_scrolling: bool = True
    enable_typing_delay: bool = True
    
    # Browser settings
    locale: str = "en-US"
    timezone: str = "America/New_York"
    
    # User agent (None = use stealth default)
    user_agent: Optional[str] = None


class HumanBehavior:
    """Simulate human-like behavior patterns"""
    
    @staticmethod
    def random_delay(min_sec: float = 1.0, max_sec: float = 5.0) -> None:
        """Add random human-like delay"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
    
    @staticmethod
    async def async_random_delay(min_sec: float = 1.0, max_sec: float = 5.0) -> None:
        """Async version of random delay"""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)
    
    @staticmethod
    def generate_mouse_path(
        start_x: int, start_y: int,
        end_x: int, end_y: int,
        steps: int = 20
    ) -> List[Tuple[int, int]]:
        """
        Generate a curved mouse path using Bezier curves.
        More human-like than straight lines.
        """
        # Add some randomness to the control points
        ctrl1_x = start_x + (end_x - start_x) / 3 + random.randint(-50, 50)
        ctrl1_y = start_y + (end_y - start_y) / 3 + random.randint(-50, 50)
        ctrl2_x = start_x + 2 * (end_x - start_x) / 3 + random.randint(-50, 50)
        ctrl2_y = start_y + 2 * (end_y - start_y) / 3 + random.randint(-50, 50)
        
        path = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier curve
            x = (1-t)**3 * start_x + 3*(1-t)**2*t * ctrl1_x + 3*(1-t)*t**2 * ctrl2_x + t**3 * end_x
            y = (1-t)**3 * start_y + 3*(1-t)**2*t * ctrl1_y + 3*(1-t)*t**2 * ctrl2_y + t**3 * end_y
            path.append((int(x), int(y)))
        
        return path
    
    @staticmethod
    def typing_delay() -> float:
        """Get random delay between keystrokes (human typing speed)"""
        # Average typing speed: 40-60 WPM = 200-300ms per character
        return random.uniform(0.05, 0.2)


class PlaywrightStealthBrowser:
    """
    Stealth browser using Playwright with anti-detection.
    
    Usage:
        browser = PlaywrightStealthBrowser()
        page = browser.new_page()
        browser.goto(page, "https://example.com")
        # ... do scraping
        browser.close()
    """
    
    def __init__(self, config: Optional[StealthConfig] = None):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed. Run: pip install playwright playwright-stealth")
        
        self.config = config or StealthConfig()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: List[Page] = []
        self._mouse_pos = (0, 0)
    
    def start(self) -> "PlaywrightStealthBrowser":
        """Start the browser"""
        logger.info(f"Starting Playwright browser (headless={self.config.headless})")
        
        self._playwright = sync_playwright().start()
        
        # Launch arguments for better stealth
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            f"--window-size={self.config.viewport_width},{self.config.viewport_height}",
        ]
        
        self._browser = self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
            args=launch_args
        )
        
        # Create context with fingerprint settings
        self._context = self._browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height
            },
            locale=self.config.locale,
            timezone_id=self.config.timezone,
            user_agent=self.config.user_agent,
            # Permissions
            permissions=["geolocation"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060},  # NYC
        )
        
        logger.info(f"Browser started with viewport {self.config.viewport_width}x{self.config.viewport_height}")
        return self
    
    def new_page(self) -> Page:
        """Create a new page with stealth applied"""
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        
        page = self._context.new_page()
        
        # Apply stealth patches using the Stealth class
        stealth = Stealth()
        stealth.apply_stealth_sync(page)
        
        # Set default timeout
        page.set_default_timeout(self.config.page_load_timeout)
        
        self._pages.append(page)
        logger.debug("New stealth page created")
        return page
    
    def goto(self, page: Page, url: str, wait_for: str = "networkidle") -> None:
        """
        Navigate to URL with human-like behavior.
        
        Args:
            page: Playwright page
            url: URL to navigate to
            wait_for: Wait strategy - 'networkidle', 'load', 'domcontentloaded'
        """
        logger.info(f"Navigating to: {url}")
        
        # Random delay before navigation
        if self.config.enable_mouse_movement:
            HumanBehavior.random_delay(0.5, 1.5)
        
        page.goto(url, wait_until=wait_for)
        
        # Wait after page load
        HumanBehavior.random_delay(self.config.min_delay, self.config.max_delay)
        
        # Simulate human behavior
        if self.config.enable_scrolling:
            self._human_scroll(page)
        
        if self.config.enable_mouse_movement:
            self._human_mouse_move(page)
    
    def _human_scroll(self, page: Page) -> None:
        """Perform human-like scrolling"""
        try:
            # Get page height
            height = page.evaluate("document.body.scrollHeight")
            viewport_height = self.config.viewport_height
            
            # Scroll down a bit (not too much, like a human would)
            scroll_amount = random.randint(100, min(500, height // 4))
            
            # Smooth scroll
            page.evaluate(f"window.scrollBy({{top: {scroll_amount}, behavior: 'smooth'}})")
            HumanBehavior.random_delay(0.5, 1.5)
            
            # Maybe scroll back up a little
            if random.random() > 0.6:
                scroll_back = random.randint(50, scroll_amount // 2)
                page.evaluate(f"window.scrollBy({{top: -{scroll_back}, behavior: 'smooth'}})")
                HumanBehavior.random_delay(0.3, 0.8)
                
        except Exception as e:
            logger.debug(f"Scroll failed (non-critical): {e}")
    
    def _human_mouse_move(self, page: Page) -> None:
        """Perform human-like mouse movement"""
        try:
            # Get current position
            start_x, start_y = self._mouse_pos
            
            # Generate random target position
            end_x = random.randint(100, self.config.viewport_width - 100)
            end_y = random.randint(100, self.config.viewport_height - 100)
            
            # Generate curved path
            path = HumanBehavior.generate_mouse_path(start_x, start_y, end_x, end_y)
            
            # Move along path
            for x, y in path:
                page.mouse.move(x, y)
                time.sleep(random.uniform(0.01, 0.03))
            
            self._mouse_pos = (end_x, end_y)
            
        except Exception as e:
            logger.debug(f"Mouse move failed (non-critical): {e}")
    
    def human_click(self, page: Page, selector: str) -> None:
        """Click element with human-like behavior"""
        try:
            element = page.locator(selector)
            
            # Get element position
            box = element.bounding_box()
            if box:
                # Move mouse to element with curve
                target_x = int(box["x"] + box["width"] / 2 + random.randint(-5, 5))
                target_y = int(box["y"] + box["height"] / 2 + random.randint(-5, 5))
                
                if self.config.enable_mouse_movement:
                    path = HumanBehavior.generate_mouse_path(
                        self._mouse_pos[0], self._mouse_pos[1],
                        target_x, target_y
                    )
                    for x, y in path:
                        page.mouse.move(x, y)
                        time.sleep(random.uniform(0.01, 0.02))
                    
                    self._mouse_pos = (target_x, target_y)
                
                # Small delay before click
                HumanBehavior.random_delay(0.1, 0.3)
            
            # Click
            element.click()
            HumanBehavior.random_delay(0.5, 1.5)
            
        except Exception as e:
            logger.warning(f"Human click failed, using direct click: {e}")
            page.click(selector)
    
    def human_type(self, page: Page, selector: str, text: str, clear_first: bool = True) -> None:
        """Type text with human-like delays between keystrokes"""
        element = page.locator(selector)
        
        # Click to focus
        self.human_click(page, selector)
        
        if clear_first:
            element.clear()
            HumanBehavior.random_delay(0.2, 0.5)
        
        # Type with delays
        if self.config.enable_typing_delay:
            for char in text:
                element.type(char, delay=int(HumanBehavior.typing_delay() * 1000))
        else:
            element.fill(text)
        
        HumanBehavior.random_delay(0.3, 0.8)
    
    def wait_for_element(
        self, 
        page: Page, 
        selector: str, 
        timeout: int = 10000,
        state: str = "visible"
    ) -> bool:
        """Wait for element with human-like patience"""
        try:
            page.wait_for_selector(selector, timeout=timeout, state=state)
            HumanBehavior.random_delay(0.5, 1.0)
            return True
        except Exception as e:
            logger.debug(f"Element not found: {selector}")
            return False
    
    def check_for_blocks(self, page: Page) -> Dict[str, bool]:
        """Check for common bot detection indicators"""
        html = page.content().lower()
        
        checks = {
            "captcha": any(x in html for x in ["captcha", "recaptcha", "hcaptcha"]),
            "cloudflare": any(x in html for x in ["cf-challenge", "cloudflare", "ray id"]),
            "perimeter_x": any(x in html for x in ["perimeterx", "px-captcha", "_pxhd"]),
            "datadome": "datadome" in html,
            "access_denied": any(x in html for x in ["access denied", "blocked", "forbidden"]),
            "rate_limited": any(x in html for x in ["rate limit", "too many requests"]),
        }
        
        blocked = any(checks.values())
        if blocked:
            detected = [k for k, v in checks.items() if v]
            logger.warning(f"Bot detection triggered: {detected}")
        
        return checks
    
    def get_page_content(self, page: Page) -> str:
        """Get page HTML content"""
        return page.content()
    
    def screenshot(self, page: Page, path: str) -> None:
        """Take screenshot for debugging"""
        page.screenshot(path=path)
        logger.debug(f"Screenshot saved to {path}")
    
    def close(self) -> None:
        """Close browser and cleanup"""
        try:
            for page in self._pages:
                try:
                    page.close()
                except:
                    pass
            
            if self._context:
                self._context.close()
            
            if self._browser:
                self._browser.close()
            
            if self._playwright:
                self._playwright.stop()
            
            logger.debug("Playwright browser closed")
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
    
    def __enter__(self):
        return self.start()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============== Async Version ==============

class AsyncPlaywrightStealthBrowser:
    """Async version of PlaywrightStealthBrowser"""
    
    def __init__(self, config: Optional[StealthConfig] = None):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed")
        
        self.config = config or StealthConfig()
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages = []
        self._mouse_pos = (0, 0)
    
    async def start(self) -> "AsyncPlaywrightStealthBrowser":
        """Start the browser"""
        logger.info(f"Starting async Playwright browser (headless={self.config.headless})")
        
        self._playwright = await async_playwright().start()
        
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ]
        
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
            args=launch_args
        )
        
        self._context = await self._browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height
            },
            locale=self.config.locale,
            timezone_id=self.config.timezone,
            user_agent=self.config.user_agent,
        )
        
        return self
    
    async def new_page(self) -> AsyncPage:
        """Create new page with stealth"""
        page = await self._context.new_page()
        
        # Apply stealth patches using the Stealth class
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        page.set_default_timeout(self.config.page_load_timeout)
        self._pages.append(page)
        return page
    
    async def goto(self, page: AsyncPage, url: str) -> None:
        """Navigate with human behavior"""
        logger.info(f"Navigating to: {url}")
        await HumanBehavior.async_random_delay(0.5, 1.5)
        await page.goto(url, wait_until="networkidle")
        await HumanBehavior.async_random_delay(self.config.min_delay, self.config.max_delay)
        
        # Human-like scroll
        if self.config.enable_scrolling:
            await self._human_scroll(page)
    
    async def _human_scroll(self, page: AsyncPage) -> None:
        """Async human scroll"""
        try:
            scroll_amount = random.randint(100, 500)
            await page.evaluate(f"window.scrollBy({{top: {scroll_amount}, behavior: 'smooth'}})")
            await HumanBehavior.async_random_delay(0.5, 1.5)
        except:
            pass
    
    async def human_click(self, page: AsyncPage, selector: str) -> None:
        """Async human click"""
        await HumanBehavior.async_random_delay(0.1, 0.3)
        await page.click(selector)
        await HumanBehavior.async_random_delay(0.5, 1.0)
    
    async def human_type(self, page: AsyncPage, selector: str, text: str) -> None:
        """Async human type"""
        await self.human_click(page, selector)
        for char in text:
            await page.type(selector, char, delay=int(HumanBehavior.typing_delay() * 1000))
        await HumanBehavior.async_random_delay(0.3, 0.8)
    
    def check_for_blocks(self, page: AsyncPage) -> Dict[str, bool]:
        """Check for blocks (sync method, call after getting content)"""
        # This needs to be called with page.content() result
        pass
    
    async def close(self) -> None:
        """Close browser"""
        try:
            for page in self._pages:
                await page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.debug("Async Playwright browser closed")
        except Exception as e:
            logger.warning(f"Error closing: {e}")
    
    async def __aenter__(self):
        return await self.start()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# ============== Factory Function ==============

def create_stealth_browser(
    program: str = "default",
    headless: bool = False,
    **kwargs
) -> PlaywrightStealthBrowser:
    """
    Create a stealth browser configured for a specific program.
    
    Args:
        program: Target program name (affects timing/behavior)
        headless: Whether to run headless (False recommended for stealth)
        **kwargs: Additional StealthConfig options
    """
    # Program-specific configurations
    program_configs = {
        "jetblue_trueblue": {
            "min_delay": 2.0,
            "max_delay": 6.0,
            "locale": "en-US",
            "timezone": "America/New_York",
        },
        "lufthansa_milesmore": {
            "min_delay": 3.0,
            "max_delay": 8.0,
            "locale": "en-US",
            "timezone": "Europe/Berlin",
        },
        "virgin_atlantic": {
            "min_delay": 2.5,
            "max_delay": 7.0,
            "locale": "en-GB",
            "timezone": "Europe/London",
        },
        "aeroplan": {
            "min_delay": 2.0,
            "max_delay": 6.0,
            "locale": "en-CA",
            "timezone": "America/Toronto",
        },
        "united_mileageplus": {
            "min_delay": 3.0,
            "max_delay": 10.0,  # United is aggressive
            "locale": "en-US",
            "timezone": "America/Chicago",
        },
    }
    
    # Get program config or defaults
    config_dict = program_configs.get(program, {})
    config_dict["headless"] = headless
    config_dict.update(kwargs)
    
    config = StealthConfig(**config_dict)
    return PlaywrightStealthBrowser(config)
