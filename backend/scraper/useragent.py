"""
User Agent Rotator - Manages random user agent strings to avoid detection
"""
import random
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

from loguru import logger

try:
    from fake_useragent import UserAgent
    HAS_FAKE_USERAGENT = True
except ImportError:
    HAS_FAKE_USERAGENT = False


class BrowserType(str, Enum):
    """Browser types for user agent"""
    CHROME = "chrome"
    FIREFOX = "firefox"
    SAFARI = "safari"
    EDGE = "edge"


class OSType(str, Enum):
    """Operating system types"""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


@dataclass
class UserAgentConfig:
    """Configuration for user agent generation"""
    browser_types: List[BrowserType]
    os_types: List[OSType]
    mobile: bool = False


class UserAgentRotator:
    """
    Generates and rotates realistic user agent strings.
    Uses fake-useragent library with fallback to curated list.
    """
    
    # Curated list of real, modern user agents (fallback)
    FALLBACK_USER_AGENTS = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        
        # Chrome on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        
        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        
        # Firefox on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        
        # Safari on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        
        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        
        # Chrome on Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    ]
    
    # User agents grouped by browser
    USER_AGENTS_BY_BROWSER = {
        BrowserType.CHROME: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ],
        BrowserType.FIREFOX: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
        ],
        BrowserType.SAFARI: [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        ],
        BrowserType.EDGE: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        ],
    }
    
    def __init__(self, use_fake_useragent: bool = True):
        """
        Initialize the user agent rotator.
        
        Args:
            use_fake_useragent: Whether to use fake-useragent library
        """
        self._fake_ua: Optional[UserAgent] = None
        self._use_fake_useragent = use_fake_useragent and HAS_FAKE_USERAGENT
        
        if self._use_fake_useragent:
            try:
                self._fake_ua = UserAgent(
                    browsers=['chrome', 'firefox', 'safari', 'edge'],
                    os=['windows', 'macos', 'linux'],
                    min_percentage=1.0
                )
                logger.info("Initialized fake-useragent library")
            except Exception as e:
                logger.warning(f"Failed to initialize fake-useragent: {e}")
                self._use_fake_useragent = False
    
    def get_random(self) -> str:
        """Get a random user agent string"""
        if self._use_fake_useragent and self._fake_ua:
            try:
                return self._fake_ua.random
            except Exception:
                pass
        
        return random.choice(self.FALLBACK_USER_AGENTS)
    
    def get_chrome(self) -> str:
        """Get a random Chrome user agent"""
        if self._use_fake_useragent and self._fake_ua:
            try:
                return self._fake_ua.chrome
            except Exception:
                pass
        
        return random.choice(self.USER_AGENTS_BY_BROWSER[BrowserType.CHROME])
    
    def get_firefox(self) -> str:
        """Get a random Firefox user agent"""
        if self._use_fake_useragent and self._fake_ua:
            try:
                return self._fake_ua.firefox
            except Exception:
                pass
        
        return random.choice(self.USER_AGENTS_BY_BROWSER[BrowserType.FIREFOX])
    
    def get_safari(self) -> str:
        """Get a random Safari user agent"""
        if self._use_fake_useragent and self._fake_ua:
            try:
                return self._fake_ua.safari
            except Exception:
                pass
        
        return random.choice(self.USER_AGENTS_BY_BROWSER[BrowserType.SAFARI])
    
    def get_for_browser(self, browser: BrowserType) -> str:
        """Get a user agent for a specific browser type"""
        if browser == BrowserType.CHROME:
            return self.get_chrome()
        elif browser == BrowserType.FIREFOX:
            return self.get_firefox()
        elif browser == BrowserType.SAFARI:
            return self.get_safari()
        elif browser == BrowserType.EDGE:
            return random.choice(self.USER_AGENTS_BY_BROWSER[BrowserType.EDGE])
        else:
            return self.get_random()
    
    def get_matching_headers(self, user_agent: Optional[str] = None) -> dict:
        """
        Get headers that match the user agent for consistency.
        This helps avoid detection from mismatched browser fingerprints.
        """
        ua = user_agent or self.get_random()
        
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
        
        # Add browser-specific headers
        if "Chrome" in ua:
            headers["sec-ch-ua"] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
            headers["sec-ch-ua-mobile"] = "?0"
            headers["sec-ch-ua-platform"] = '"Windows"' if "Windows" in ua else '"macOS"'
            headers["Sec-Fetch-Dest"] = "document"
            headers["Sec-Fetch-Mode"] = "navigate"
            headers["Sec-Fetch-Site"] = "none"
            headers["Sec-Fetch-User"] = "?1"
        
        return headers
