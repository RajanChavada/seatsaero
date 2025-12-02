"""
Browser Manager - Enhanced Selenium/undetected-chromedriver with stealth techniques
"""
import asyncio
import ssl
import certifi
import random
import time
from typing import Optional, Dict, Any, List, Tuple
from contextlib import asynccontextmanager
from dataclasses import dataclass

from loguru import logger

# Fix SSL certificate issues on macOS
try:
    # This is a more aggressive SSL fix for macOS
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, 
        WebDriverException,
        NoSuchElementException,
        StaleElementReferenceException
    )
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    logger.warning("Selenium/undetected-chromedriver not installed")

from config import settings
from scraper.proxy import ProxyConfig


# Realistic viewport sizes (desktop)
VIEWPORT_SIZES = [
    (1920, 1080),  # Full HD
    (1366, 768),   # Common laptop
    (1536, 864),   # Common laptop
    (1440, 900),   # MacBook
    (1680, 1050),  # Wide laptop
    (2560, 1440),  # QHD
    (1280, 720),   # HD
]

# Common timezones by region
TIMEZONES = {
    "us": ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"],
    "ca": ["America/Toronto", "America/Vancouver", "America/Montreal"],
    "eu": ["Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Amsterdam"],
    "default": ["America/New_York", "America/Chicago", "America/Los_Angeles"],
}

# Common locales
LOCALES = {
    "us": ["en-US", "en"],
    "ca": ["en-CA", "en-US", "en"],
    "eu": ["en-GB", "en"],
    "default": ["en-US", "en"],
}


@dataclass
class BrowserProfile:
    """Browser profile with fingerprint settings"""
    user_agent: str
    viewport: Tuple[int, int]
    timezone: str
    locale: str
    proxy: Optional[ProxyConfig] = None
    headless: bool = True
    
    @classmethod
    def create_for_program(cls, program: str, user_agent: str = None, proxy: ProxyConfig = None) -> "BrowserProfile":
        """Create a browser profile optimized for a specific program"""
        from scraper.useragent import UserAgentRotator
        
        # Get user agent
        if not user_agent:
            ua_rotator = UserAgentRotator()
            user_agent = ua_rotator.get_random()
        
        # Determine region based on program
        region = "us"  # Default
        if program.lower() == "aeroplan":
            region = "ca"
        
        return cls(
            user_agent=user_agent,
            viewport=random.choice(VIEWPORT_SIZES),
            timezone=random.choice(TIMEZONES.get(region, TIMEZONES["default"])),
            locale=random.choice(LOCALES.get(region, LOCALES["default"])),
            proxy=proxy,
            headless=settings.get_program_headless(program)
        )


class BrowserManager:
    """
    Enhanced browser manager with stealth techniques and human-like behavior.
    
    Features:
    - Per-program headless toggle
    - Randomized viewport and fingerprints
    - Timezone/locale alignment with proxy
    - Selenium-stealth techniques
    - Human-like interactions
    """
    
    def __init__(
        self,
        profile: Optional[BrowserProfile] = None,
        program: str = "default"
    ):
        self.profile = profile or BrowserProfile.create_for_program(program)
        self.program = program
        self.driver = None
        self._action_chain = None
    
    def _get_chrome_options(self) -> Any:
        """Configure Chrome options with stealth settings"""
        options = uc.ChromeOptions()
        
        # Headless mode - use --headless=new for Chrome 109+
        # This is more compatible than passing headless=True to uc.Chrome()
        if self.profile.headless:
            options.add_argument("--headless=new")
        
        # Basic options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Viewport size
        width, height = self.profile.viewport
        options.add_argument(f"--window-size={width},{height}")
        
        # User agent
        if self.profile.user_agent:
            options.add_argument(f"--user-agent={self.profile.user_agent}")
        
        # Locale/language
        if self.profile.locale:
            options.add_argument(f"--lang={self.profile.locale}")
        
        # Proxy configuration
        if self.profile.proxy:
            proxy_arg = self.profile.proxy.to_selenium_arg()
            options.add_argument(f"--proxy-server={proxy_arg}")
        
        return options
    
    def create_driver(self) -> Any:
        """Create a new browser driver instance with stealth"""
        if not HAS_SELENIUM:
            raise RuntimeError("Selenium not installed")
        
        options = self._get_chrome_options()
        
        try:
            # For Chrome 109+, we use --headless=new in options instead of headless param
            # This is more compatible with newer Chrome versions
            driver = uc.Chrome(
                options=options,
                use_subprocess=True,  # More stable on macOS
            )
            
            # Set page load timeout
            driver.set_page_load_timeout(settings.browser_timeout)
            
            # Apply stealth scripts (with error handling)
            try:
                self._apply_stealth_scripts(driver)
            except Exception as e:
                logger.warning(f"Could not apply stealth scripts: {e}")
            
            # Set viewport properly
            width, height = self.profile.viewport
            try:
                driver.set_window_size(width, height)
            except Exception as e:
                logger.warning(f"Could not set window size: {e}")
            
            self.driver = driver
            self._action_chain = ActionChains(driver)
            
            logger.info(f"Browser driver created (headless={self.profile.headless}, viewport={width}x{height})")
            return driver
            
        except Exception as e:
            logger.error(f"Failed to create browser driver: {e}")
            raise
    
    def _apply_stealth_scripts(self, driver) -> None:
        """Apply JavaScript to mask automation detection"""
        # Check if driver is still valid
        try:
            _ = driver.current_url
        except Exception:
            logger.debug("Driver not ready for stealth scripts")
            return
        
        stealth_scripts = [
            # Override webdriver property
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            """,
            
            # Override plugins
            """
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ]
            });
            """,
            
            # Override languages
            f"""
            Object.defineProperty(navigator, 'languages', {{
                get: () => ['{self.profile.locale}']
            }});
            """,
            
            # Override platform
            """
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });
            """,
            
            # Override hardware concurrency (common values)
            """
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            """,
            
            # Override deviceMemory
            """
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            """,
            
            # Mock WebGL vendor/renderer
            """
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.apply(this, arguments);
            };
            """,
            
            # Override permissions
            """
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            """,
            
            # Remove chrome runtime
            """
            window.chrome = {
                runtime: {},
            };
            """,
            
            # Override screen properties
            f"""
            Object.defineProperty(screen, 'width', {{ get: () => {self.profile.viewport[0]} }});
            Object.defineProperty(screen, 'height', {{ get: () => {self.profile.viewport[1]} }});
            Object.defineProperty(screen, 'availWidth', {{ get: () => {self.profile.viewport[0]} }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => {self.profile.viewport[1] - 40} }});
            """,
        ]
        
        for script in stealth_scripts:
            try:
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": script
                })
            except Exception as e:
                logger.debug(f"Failed to inject stealth script: {e}")
    
    def close(self) -> None:
        """Close the browser driver"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self._action_chain = None
            logger.debug("Browser driver closed")
    
    @asynccontextmanager
    async def get_driver(self):
        """Context manager for browser driver"""
        driver = self.create_driver()
        try:
            yield driver
        finally:
            self.close()
    
    # ============== Human-like Interaction Methods ==============
    
    def human_sleep(self, min_ms: int = None, max_ms: int = None) -> None:
        """Sleep for a random human-like duration"""
        min_ms = min_ms or settings.human_delay_min_ms
        max_ms = max_ms or settings.human_delay_max_ms
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        time.sleep(delay)
    
    def human_move_to(self, element) -> None:
        """Move mouse to element with human-like movement"""
        if not self._action_chain:
            self._action_chain = ActionChains(self.driver)
        
        # Small random offset
        offset_x = random.randint(-5, 5)
        offset_y = random.randint(-5, 5)
        
        self._action_chain.move_to_element_with_offset(
            element, offset_x, offset_y
        ).perform()
        self.human_sleep(100, 300)
    
    def human_click(self, element) -> None:
        """Click element with human-like behavior"""
        # Scroll into view if needed
        self.driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
            element
        )
        self.human_sleep(200, 500)
        
        # Move to element
        self.human_move_to(element)
        
        # Click with small delay
        self.human_sleep(50, 150)
        element.click()
    
    def human_type(self, element, text: str, clear_first: bool = True) -> None:
        """Type text with human-like speed and occasional mistakes"""
        if clear_first:
            element.clear()
            self.human_sleep(100, 200)
        
        for char in text:
            element.send_keys(char)
            # Random typing delay (30-100ms per character)
            time.sleep(random.uniform(0.03, 0.1))
            
            # Occasional longer pause (thinking)
            if random.random() < 0.05:
                time.sleep(random.uniform(0.2, 0.5))
    
    def human_scroll(self, pixels: int = None, direction: str = "down") -> None:
        """Scroll page with human-like behavior"""
        if pixels is None:
            pixels = random.randint(200, 600)
        
        if direction == "up":
            pixels = -pixels
        
        # Smooth scroll using JavaScript
        self.driver.execute_script(f"""
            window.scrollBy({{
                top: {pixels},
                behavior: 'smooth'
            }});
        """)
        
        # Wait for scroll to complete
        time.sleep(random.uniform(
            settings.scroll_delay_min_ms / 1000,
            settings.scroll_delay_max_ms / 1000
        ))
    
    def random_mouse_movement(self) -> None:
        """Perform random mouse movement to appear human"""
        if not self._action_chain or not self.driver:
            return
        
        try:
            # Get viewport size
            viewport = self.driver.execute_script(
                "return {width: window.innerWidth, height: window.innerHeight};"
            )
            
            # Random movement
            x = random.randint(100, viewport['width'] - 100)
            y = random.randint(100, viewport['height'] - 100)
            
            self._action_chain.move_by_offset(x, y).perform()
            self.human_sleep(50, 150)
            
            # Reset position
            self._action_chain.move_by_offset(-x, -y).perform()
        except Exception:
            pass
    
    # ============== Element Finding with Fallbacks ==============
    
    def find_element_with_fallbacks(
        self,
        locators: List[Tuple[str, str]],
        timeout: int = 10,
        description: str = "element"
    ) -> Optional[Any]:
        """
        Find element using multiple fallback locators.
        
        Args:
            locators: List of (By.XXX, value) tuples to try
            timeout: Wait timeout per locator
            description: Description for logging
            
        Returns:
            WebElement or None
        """
        for by, value in locators:
            try:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                logger.debug(f"Found {description} using {by}='{value}'")
                return element
            except TimeoutException:
                logger.debug(f"Locator failed for {description}: {by}='{value}'")
                continue
            except Exception as e:
                logger.debug(f"Error finding {description}: {e}")
                continue
        
        logger.warning(f"Failed to find {description} with any locator")
        return None
    
    def find_elements_with_fallbacks(
        self,
        locators: List[Tuple[str, str]],
        timeout: int = 10,
        description: str = "elements"
    ) -> List[Any]:
        """
        Find elements using multiple fallback locators.
        
        Args:
            locators: List of (By.XXX, value) tuples to try
            timeout: Wait timeout per locator
            description: Description for logging
            
        Returns:
            List of WebElements (may be empty)
        """
        for by, value in locators:
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                elements = self.driver.find_elements(by, value)
                if elements:
                    logger.debug(f"Found {len(elements)} {description} using {by}='{value}'")
                    return elements
            except TimeoutException:
                logger.debug(f"Locator failed for {description}: {by}='{value}'")
                continue
            except Exception as e:
                logger.debug(f"Error finding {description}: {e}")
                continue
        
        logger.warning(f"Failed to find {description} with any locator")
        return []
    
    def wait_for_any_element(
        self,
        locators: List[Tuple[str, str]],
        timeout: int = 30
    ) -> Optional[Any]:
        """Wait for any of the given elements to appear"""
        end_time = time.time() + timeout
        
        while time.time() < end_time:
            for by, value in locators:
                try:
                    element = self.driver.find_element(by, value)
                    if element.is_displayed():
                        return element
                except (NoSuchElementException, StaleElementReferenceException):
                    continue
            time.sleep(0.5)
        
        return None
    
    # ============== Page Navigation ==============
    
    async def navigate(self, url: str, wait_for: List[Tuple[str, str]] = None) -> bool:
        """
        Navigate to URL with optional element wait.
        
        Args:
            url: URL to navigate to
            wait_for: Optional list of locators to wait for
            
        Returns:
            True if navigation successful
        """
        try:
            self.driver.get(url)
            self.human_sleep(500, 1500)
            
            # Random scroll to appear human
            if random.random() < 0.3:
                self.human_scroll(random.randint(50, 200))
            
            # Wait for specific elements if requested
            if wait_for:
                element = self.wait_for_any_element(wait_for, timeout=30)
                if not element:
                    logger.warning(f"Wait elements not found after navigating to {url}")
                    return False
            
            return True
            
        except TimeoutException:
            logger.error(f"Timeout navigating to {url}")
            return False
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            return False
    
    def get_page_source(self) -> str:
        """Get current page source"""
        return self.driver.page_source if self.driver else ""
    
    def take_screenshot(self, filename: str) -> bool:
        """Take screenshot for debugging"""
        try:
            if self.driver:
                self.driver.save_screenshot(filename)
                logger.debug(f"Screenshot saved: {filename}")
                return True
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
        return False
    
    # ============== CAPTCHA Detection ==============
    
    def detect_captcha(self) -> bool:
        """
        Detect if current page has a CAPTCHA.
        
        Returns:
            True if CAPTCHA detected
        """
        if not self.driver:
            return False
        
        captcha_indicators = [
            # reCAPTCHA
            (By.CSS_SELECTOR, "iframe[src*='recaptcha']"),
            (By.CSS_SELECTOR, ".g-recaptcha"),
            (By.ID, "recaptcha"),
            
            # hCaptcha
            (By.CSS_SELECTOR, "iframe[src*='hcaptcha']"),
            (By.CSS_SELECTOR, ".h-captcha"),
            
            # Cloudflare
            (By.CSS_SELECTOR, "iframe[src*='challenges.cloudflare']"),
            (By.ID, "challenge-running"),
            (By.CSS_SELECTOR, ".cf-browser-verification"),
            
            # PerimeterX
            (By.CSS_SELECTOR, "iframe[src*='captcha.px']"),
            (By.ID, "px-captcha"),
            
            # Generic
            (By.XPATH, "//*[contains(text(), 'verify you are human')]"),
            (By.XPATH, "//*[contains(text(), 'are you a robot')]"),
            (By.XPATH, "//*[contains(text(), 'security check')]"),
            (By.XPATH, "//*[contains(text(), 'unusual traffic')]"),
        ]
        
        for by, value in captcha_indicators:
            try:
                elements = self.driver.find_elements(by, value)
                if elements:
                    logger.warning(f"CAPTCHA detected: {by}='{value}'")
                    return True
            except Exception:
                continue
        
        # Check page source for common CAPTCHA patterns
        try:
            source = self.driver.page_source.lower()
            captcha_patterns = [
                "captcha",
                "challenge-running",
                "verify you are human",
                "security verification",
                "access denied",
                "bot detection",
            ]
            for pattern in captcha_patterns:
                if pattern in source:
                    logger.warning(f"CAPTCHA pattern in source: '{pattern}'")
                    return True
        except Exception:
            pass
        
        return False
    
    def detect_block_page(self) -> bool:
        """
        Detect if we've been blocked (403, 429, WAF page).
        
        Returns:
            True if block detected
        """
        if not self.driver:
            return False
        
        block_indicators = [
            # HTTP status in title
            "403 forbidden",
            "429 too many requests",
            "access denied",
            "blocked",
            
            # WAF messages
            "web application firewall",
            "request blocked",
            "suspicious activity",
            "rate limit exceeded",
        ]
        
        try:
            # Check title
            title = self.driver.title.lower()
            for indicator in block_indicators:
                if indicator in title:
                    logger.warning(f"Block detected in title: '{indicator}'")
                    return True
            
            # Check page source
            source = self.driver.page_source.lower()
            for indicator in block_indicators:
                if indicator in source:
                    logger.warning(f"Block detected in source: '{indicator}'")
                    return True
        except Exception:
            pass
        
        return False


# ============== Factory Functions ==============

def create_browser_manager(
    program: str,
    proxy: ProxyConfig = None,
    user_agent: str = None
) -> BrowserManager:
    """
    Create a browser manager for a specific program.
    
    Args:
        program: Program name (united, aeroplan, etc.)
        proxy: Optional proxy config
        user_agent: Optional user agent override
        
    Returns:
        Configured BrowserManager
    """
    profile = BrowserProfile.create_for_program(
        program=program,
        user_agent=user_agent,
        proxy=proxy
    )
    return BrowserManager(profile=profile, program=program)


async def create_stealth_driver(
    program: str,
    proxy: ProxyConfig = None
) -> Tuple[Any, BrowserManager]:
    """
    Create a stealth browser driver for scraping.
    
    Args:
        program: Program name
        proxy: Optional proxy
        
    Returns:
        Tuple of (driver, manager)
    """
    manager = create_browser_manager(program, proxy)
    driver = manager.create_driver()
    return driver, manager
