"""
Browser Manager - Selenium/undetected-chromedriver management
"""
import asyncio
import ssl
import certifi
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import random

from loguru import logger

# Fix SSL certificate issues on macOS
try:
    import urllib.request
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    # Monkey-patch SSL for urllib
    ssl._create_default_https_context = lambda: ssl_context
except Exception:
    pass

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False
    logger.warning("Selenium/undetected-chromedriver not installed")

from config import settings


class BrowserManager:
    """
    Manages browser instances for web scraping.
    Uses undetected-chromedriver to avoid bot detection.
    """
    
    # Viewport sizes to randomize
    VIEWPORT_SIZES = [
        (1920, 1080),
        (1366, 768),
        (1536, 864),
        (1440, 900),
        (1280, 720),
    ]
    
    def __init__(
        self,
        headless: bool = None,
        proxy: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None
    ):
        self.headless = headless if headless is not None else settings.headless_mode
        self.proxy = proxy
        self.user_agent = user_agent
        self._driver = None
        
    def _get_chrome_options(self) -> Any:
        """Configure Chrome options for stealth"""
        if not HAS_SELENIUM:
            raise RuntimeError("Selenium not installed. Run: pip install undetected-chromedriver")
        
        options = uc.ChromeOptions()
        
        # Headless mode
        if self.headless:
            options.add_argument("--headless=new")
        
        # Basic stealth options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        
        # Randomize viewport
        width, height = random.choice(self.VIEWPORT_SIZES)
        options.add_argument(f"--window-size={width},{height}")
        
        # User agent
        if self.user_agent:
            options.add_argument(f"--user-agent={self.user_agent}")
        
        # Proxy configuration
        if self.proxy:
            proxy_str = self.proxy.get("http") or self.proxy.get("https")
            if proxy_str:
                options.add_argument(f"--proxy-server={proxy_str}")
        
        # Additional privacy options
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")
        
        return options
    
    def create_driver(self) -> Any:
        """Create a new browser driver instance"""
        if not HAS_SELENIUM:
            raise RuntimeError("Selenium not installed")
        
        options = self._get_chrome_options()
        
        try:
            driver = uc.Chrome(
                options=options,
                driver_executable_path=settings.chrome_driver_path,
                version_main=None  # Auto-detect Chrome version
            )
            
            # Set page load timeout
            driver.set_page_load_timeout(settings.browser_timeout)
            
            # Execute stealth scripts
            self._apply_stealth_scripts(driver)
            
            logger.info("Browser driver created successfully")
            return driver
            
        except Exception as e:
            logger.error(f"Failed to create browser driver: {e}")
            raise
    
    def _apply_stealth_scripts(self, driver) -> None:
        """Apply JavaScript to further mask automation"""
        stealth_js = """
        // Override webdriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Override plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Override platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });
        
        // Override chrome property
        window.chrome = {
            runtime: {}
        };
        """
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": stealth_js
            })
        except Exception as e:
            logger.warning(f"Could not apply stealth scripts: {e}")
    
    @asynccontextmanager
    async def get_driver(self):
        """
        Async context manager for browser driver.
        Ensures proper cleanup of browser resources.
        """
        driver = None
        try:
            # Run driver creation in executor to not block event loop
            loop = asyncio.get_event_loop()
            driver = await loop.run_in_executor(None, self.create_driver)
            yield driver
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.debug("Browser driver closed")
                except Exception as e:
                    logger.warning(f"Error closing driver: {e}")
    
    async def fetch_page(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
        wait_timeout: int = 10
    ) -> str:
        """
        Fetch a page and return its HTML content.
        
        Args:
            url: URL to fetch
            wait_for_selector: Optional CSS selector to wait for
            wait_timeout: Timeout for waiting (seconds)
            
        Returns:
            Page HTML content
        """
        async with self.get_driver() as driver:
            loop = asyncio.get_event_loop()
            
            # Navigate to URL
            await loop.run_in_executor(None, driver.get, url)
            
            # Wait for element if specified
            if wait_for_selector:
                try:
                    wait = WebDriverWait(driver, wait_timeout)
                    await loop.run_in_executor(
                        None,
                        wait.until,
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                    )
                except TimeoutException:
                    logger.warning(f"Timeout waiting for {wait_for_selector}")
            
            # Get page source
            html = await loop.run_in_executor(None, lambda: driver.page_source)
            return html
    
    async def execute_with_driver(self, func, *args, **kwargs) -> Any:
        """
        Execute a function with a browser driver.
        
        The function receives the driver as first argument.
        """
        async with self.get_driver() as driver:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, driver, *args, **kwargs)


class BrowserPool:
    """
    Pool of browser instances for concurrent scraping.
    """
    
    def __init__(self, max_browsers: int = 3):
        self.max_browsers = max_browsers
        self._semaphore = asyncio.Semaphore(max_browsers)
        self._managers: list = []
    
    @asynccontextmanager
    async def acquire(
        self,
        proxy: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None
    ):
        """Acquire a browser from the pool"""
        async with self._semaphore:
            manager = BrowserManager(proxy=proxy, user_agent=user_agent)
            try:
                async with manager.get_driver() as driver:
                    yield driver
            finally:
                pass  # Manager handles cleanup
