"""
Seats Aero Clone - Configuration Settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional, Dict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # ============== General Scraper Settings ==============
    scrape_delay_min: int = Field(default=2, description="Minimum delay between requests (seconds)")
    scrape_delay_max: int = Field(default=10, description="Maximum delay between requests (seconds)")
    concurrent_scrapers: int = Field(default=3, description="Number of concurrent scraper workers")
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    
    # ============== Browser Settings ==============
    headless_mode: bool = Field(default=True, description="Default headless mode")
    chrome_driver_path: Optional[str] = Field(default=None, description="Path to ChromeDriver")
    browser_timeout: int = Field(default=30, description="Browser operation timeout")
    
    # Per-program headless overrides (False = visible browser for tough sites)
    united_headless: bool = Field(default=False, description="United headless mode")
    aeroplan_headless: bool = Field(default=False, description="Aeroplan headless mode")
    jetblue_headless: bool = Field(default=False, description="JetBlue headless mode")
    lufthansa_headless: bool = Field(default=False, description="Lufthansa headless mode")
    virgin_atlantic_headless: bool = Field(default=False, description="Virgin Atlantic headless mode")
    demo_headless: bool = Field(default=True, description="Demo headless mode")
    
    # ============== Proxy Configuration ==============
    proxy_enabled: bool = Field(default=False, description="Enable proxy rotation")
    proxy_list_url: Optional[str] = Field(default=None, description="URL to fetch proxy list")
    proxy_rotation_strategy: str = Field(default="sticky", description="per_request or sticky")
    proxy_sticky_duration_mins: int = Field(default=10, description="Sticky proxy duration")
    
    # Per-program proxy pools (comma-separated proxy URLs)
    united_proxy_pool: Optional[str] = Field(default=None, description="United proxy pool")
    aeroplan_proxy_pool: Optional[str] = Field(default=None, description="Aeroplan proxy pool")
    default_proxy_pool: Optional[str] = Field(default=None, description="Default proxy pool")
    
    # Proxy authentication (if using authenticated residential proxies)
    united_proxy_user: Optional[str] = Field(default=None, description="United proxy username")
    united_proxy_pass: Optional[str] = Field(default=None, description="United proxy password")
    aeroplan_proxy_user: Optional[str] = Field(default=None, description="Aeroplan proxy username")
    aeroplan_proxy_pass: Optional[str] = Field(default=None, description="Aeroplan proxy password")
    
    # ============== Anti-Detection Settings ==============
    max_retries_per_job: int = Field(default=3, description="Max retries per scrape job")
    base_retry_delay_secs: int = Field(default=5, description="Base delay for exponential backoff")
    max_requests_per_minute: int = Field(default=10, description="Global rate limit per minute")
    
    # Per-program rate limits
    united_requests_per_minute: int = Field(default=6, description="United rate limit")
    aeroplan_requests_per_minute: int = Field(default=6, description="Aeroplan rate limit")
    
    # Human-like behavior settings
    human_delay_min_ms: int = Field(default=300, description="Min delay for human actions (ms)")
    human_delay_max_ms: int = Field(default=1200, description="Max delay for human actions (ms)")
    scroll_delay_min_ms: int = Field(default=100, description="Min scroll delay (ms)")
    scroll_delay_max_ms: int = Field(default=500, description="Max scroll delay (ms)")
    
    # Fingerprint settings
    randomize_viewport: bool = Field(default=True, description="Randomize viewport size")
    randomize_timezone: bool = Field(default=True, description="Match timezone to proxy geo")
    use_selenium_stealth: bool = Field(default=True, description="Apply stealth techniques")
    
    # ============== CAPTCHA & Detection Handling ==============
    captcha_manual_solve: bool = Field(default=False, description="Pause for manual CAPTCHA solve")
    proxy_hot_duration_mins: int = Field(default=30, description="Duration to mark proxy as hot")
    max_captcha_per_session: int = Field(default=2, description="Max CAPTCHAs before session abort")
    
    # ============== API Settings ==============
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:8000", description="CORS origins")
    
    # ============== Logging ==============
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Optional[str] = Field(default="logs/app.log", description="Log file path")
    
    # ============== Data & Cache Settings ==============
    data_expiry_hours: int = Field(default=6, description="Hours before data is considered stale")
    max_results_per_search: int = Field(default=500, description="Maximum results per search")
    cache_first: bool = Field(default=True, description="Return cached data if available")
    fallback_to_demo: bool = Field(default=True, description="Fallback to demo on scrape failure")
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    def get_program_headless(self, program: str) -> bool:
        """Get headless mode for specific program"""
        overrides = {
            "united": self.united_headless,
            "united_mileageplus": self.united_headless,
            "aeroplan": self.aeroplan_headless,
            "demo": self.demo_headless,
        }
        return overrides.get(program.lower(), self.headless_mode)
    
    def get_program_rate_limit(self, program: str) -> int:
        """Get rate limit for specific program"""
        limits = {
            "united": self.united_requests_per_minute,
            "united_mileageplus": self.united_requests_per_minute,
            "aeroplan": self.aeroplan_requests_per_minute,
        }
        return limits.get(program.lower(), self.max_requests_per_minute)
    
    def get_program_proxy_pool(self, program: str) -> Optional[List[str]]:
        """Get proxy pool for specific program"""
        pools = {
            "united": self.united_proxy_pool,
            "united_mileageplus": self.united_proxy_pool,
            "aeroplan": self.aeroplan_proxy_pool,
        }
        pool_str = pools.get(program.lower(), self.default_proxy_pool)
        if pool_str:
            return [p.strip() for p in pool_str.split(",") if p.strip()]
        return None
    
    def get_program_proxy_auth(self, program: str) -> Optional[Dict[str, str]]:
        """Get proxy authentication for specific program"""
        auth = {
            "united": (self.united_proxy_user, self.united_proxy_pass),
            "united_mileageplus": (self.united_proxy_user, self.united_proxy_pass),
            "aeroplan": (self.aeroplan_proxy_user, self.aeroplan_proxy_pass),
        }
        user, passwd = auth.get(program.lower(), (None, None))
        if user and passwd:
            return {"username": user, "password": passwd}
        return None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Export settings instance
settings = get_settings()
