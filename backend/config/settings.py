"""
Seats Aero Clone - Configuration Settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Scraper Settings
    scrape_delay_min: int = Field(default=2, description="Minimum delay between requests (seconds)")
    scrape_delay_max: int = Field(default=10, description="Maximum delay between requests (seconds)")
    concurrent_scrapers: int = Field(default=3, description="Number of concurrent scraper workers")
    headless_mode: bool = Field(default=True, description="Run browser in headless mode")
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    
    # Proxy Configuration
    proxy_enabled: bool = Field(default=False, description="Enable proxy rotation")
    proxy_list_url: Optional[str] = Field(default=None, description="URL to fetch proxy list")
    proxy_rotation_strategy: str = Field(default="per_request", description="Proxy rotation strategy")
    
    # Browser Settings
    chrome_driver_path: Optional[str] = Field(default=None, description="Path to ChromeDriver")
    browser_timeout: int = Field(default=30, description="Browser operation timeout")
    
    # API Settings
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    cors_origins: str = Field(default="http://localhost:3000", description="Allowed CORS origins")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Optional[str] = Field(default="logs/app.log", description="Log file path")
    
    # Data Settings
    data_expiry_hours: int = Field(default=6, description="Hours before data is considered stale")
    max_results_per_search: int = Field(default=500, description="Maximum results per search")
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
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
