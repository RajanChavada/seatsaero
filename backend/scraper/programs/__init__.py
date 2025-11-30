"""Loyalty Program Scrapers"""
from .united import UnitedMileagePlusScraper
from .aeroplan import AeroplanScraper
from .demo import DemoScraper

__all__ = [
    "UnitedMileagePlusScraper",
    "AeroplanScraper",
    "DemoScraper",
]

# Registry of all available scrapers
# Demo scraper is first for testing - real scrapers can be added
SCRAPER_REGISTRY = {
    "demo": DemoScraper,  # Demo mode for testing
    # "united_mileageplus": UnitedMileagePlusScraper,  # Disabled - needs selector fixes
    # "aeroplan": AeroplanScraper,  # Disabled - needs selector fixes
}


def get_scraper(program_name: str):
    """Get scraper class by program name"""
    if program_name not in SCRAPER_REGISTRY:
        raise ValueError(f"Unknown program: {program_name}. Available: {list(SCRAPER_REGISTRY.keys())}")
    return SCRAPER_REGISTRY[program_name]


def get_all_scrapers():
    """Get all available scraper classes"""
    return list(SCRAPER_REGISTRY.values())
