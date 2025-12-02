"""Loyalty Program Scrapers"""
from .united import UnitedMileagePlusScraper
from .aeroplan import AeroplanScraper
from .demo import DemoScraper
from .jetblue import JetBlueTrueBlueScraper
from .lufthansa import LufthansaMilesMoreScraper
from .virgin_atlantic import VirginAtlanticFlyingClubScraper
from .google_flights import GoogleFlightsScraper

__all__ = [
    "UnitedMileagePlusScraper",
    "AeroplanScraper",
    "DemoScraper",
    "JetBlueTrueBlueScraper",
    "LufthansaMilesMoreScraper",
    "VirginAtlanticFlyingClubScraper",
    "GoogleFlightsScraper",
]

# Registry of all available scrapers
# Maps program_name -> Scraper Class
# 
# Target routes coverage:
#   - USA/Mexico/Caribbean: JetBlue, United
#   - Canada: Aeroplan
#   - Europe: Lufthansa (Germany hub), Virgin Atlantic (UK)
#   - India: Aeroplan (via Star Alliance)
#   - Transatlantic: Virgin Atlantic, Lufthansa
#
SCRAPER_REGISTRY = {
    # === Always Available ===
    "demo": DemoScraper,  # Demo mode for testing
    
    # === Cash Fares Aggregator ===
    "google_flights": GoogleFlightsScraper,  # Multi-airline cash prices (works great!)
    
    # === Priority 1: Lighter Detection ===
    "jetblue_trueblue": JetBlueTrueBlueScraper,  # USA, Mexico, Caribbean - lighter bot detection
    
    # === Priority 2: Star Alliance (Europe, Canada, India) ===
    "lufthansa_milesmore": LufthansaMilesMoreScraper,  # Europe hub (FRA, MUC)
    "aeroplan": AeroplanScraper,  # Canada + India routes
    
    # === Priority 3: Transatlantic ===
    "virgin_atlantic": VirginAtlanticFlyingClubScraper,  # UK-USA routes
    
    # === Heavy Bot Detection (needs proxies) ===
    "united_mileageplus": UnitedMileagePlusScraper,  # USA hub - heavy detection
}

# Human-readable program names for UI
PROGRAM_DISPLAY_NAMES = {
    "demo": "Demo Mode",
    "google_flights": "Google Flights (Cash Prices)",
    "jetblue_trueblue": "JetBlue TrueBlue",
    "lufthansa_milesmore": "Lufthansa Miles & More",
    "aeroplan": "Air Canada Aeroplan",
    "virgin_atlantic": "Virgin Atlantic Flying Club",
    "united_mileageplus": "United MileagePlus",
}

# Suggested routes for each program
PROGRAM_ROUTES = {
    "google_flights": [
        ("SFO", "JFK", "USA Transcontinental"),
        ("LAX", "LHR", "USA - Europe"),
        ("NYC", "MIA", "USA Domestic"),
    ],
    "jetblue_trueblue": [
        ("JFK", "MIA", "USA East Coast"),
        ("JFK", "CUN", "Mexico - Cancun"),
        ("BOS", "LAX", "USA Transcontinental"),
    ],
    "lufthansa_milesmore": [
        ("FRA", "JFK", "Germany - USA"),
        ("MUC", "DEL", "Germany - India"),
        ("FRA", "YYZ", "Germany - Canada"),
    ],
    "aeroplan": [
        ("YYZ", "YYC", "Canada Domestic"),
        ("YYZ", "DEL", "Canada - India"),
        ("YYZ", "FRA", "Canada - Europe"),
    ],
    "virgin_atlantic": [
        ("LHR", "JFK", "UK - USA"),
        ("LHR", "LAX", "UK - West Coast"),
        ("MAN", "ATL", "Manchester - Atlanta"),
    ],
    "united_mileageplus": [
        ("EWR", "MEX", "USA - Mexico City"),
        ("ORD", "FRA", "USA - Europe"),
        ("SFO", "NRT", "USA - Japan"),
    ],
}


def get_scraper(program_name: str):
    """Get scraper class by program name"""
    if program_name not in SCRAPER_REGISTRY:
        raise ValueError(f"Unknown program: {program_name}. Available: {list(SCRAPER_REGISTRY.keys())}")
    return SCRAPER_REGISTRY[program_name]


def get_all_scrapers():
    """Get all available scraper classes"""
    return list(SCRAPER_REGISTRY.values())


def get_enabled_scrapers():
    """Get scrapers that are ready to use (excluding demo)"""
    return {k: v for k, v in SCRAPER_REGISTRY.items() if k != "demo"}


def get_programs_for_route(origin: str, destination: str) -> list:
    """
    Suggest best programs for a given route.
    
    This helps the search API try the most relevant scrapers first.
    """
    suggestions = []
    
    # Country/region detection based on airport codes
    us_airports = {'JFK', 'LAX', 'ORD', 'SFO', 'MIA', 'BOS', 'EWR', 'ATL', 'DFW', 'SEA', 'DEN'}
    canada_airports = {'YYZ', 'YYC', 'YVR', 'YUL', 'YOW'}
    uk_airports = {'LHR', 'LGW', 'MAN', 'EDI', 'BHX'}
    germany_airports = {'FRA', 'MUC', 'DUS', 'BER', 'HAM'}
    india_airports = {'DEL', 'BOM', 'BLR', 'MAA', 'HYD', 'CCU'}
    mexico_airports = {'MEX', 'CUN', 'GDL', 'SJD'}
    
    origin_upper = origin.upper()
    dest_upper = destination.upper()
    
    # JetBlue - USA domestic and Caribbean
    if origin_upper in us_airports or dest_upper in us_airports:
        if origin_upper in us_airports and dest_upper in us_airports:
            suggestions.append("jetblue_trueblue")
        if dest_upper in mexico_airports or origin_upper in mexico_airports:
            suggestions.append("jetblue_trueblue")
    
    # Aeroplan - Canada routes and India
    if origin_upper in canada_airports or dest_upper in canada_airports:
        suggestions.append("aeroplan")
    if dest_upper in india_airports or origin_upper in india_airports:
        suggestions.append("aeroplan")
    
    # Lufthansa - Europe, especially Germany
    if origin_upper in germany_airports or dest_upper in germany_airports:
        suggestions.append("lufthansa_milesmore")
    
    # Virgin Atlantic - UK routes
    if origin_upper in uk_airports or dest_upper in uk_airports:
        suggestions.append("virgin_atlantic")
    
    # United - always a fallback for USA
    if origin_upper in us_airports or dest_upper in us_airports:
        suggestions.append("united_mileageplus")
    
    # Always include demo as fallback
    suggestions.append("demo")
    
    # Remove duplicates while preserving order
    seen = set()
    return [x for x in suggestions if not (x in seen or seen.add(x))]
