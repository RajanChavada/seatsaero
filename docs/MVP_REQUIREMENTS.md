# Seats Aero Clone - MVP Requirements Document

## Project Overview
A web application that scrapes airline loyalty program websites to find award seat availability, consolidating data into a searchable interface with granular filtering capabilities.

---

## Phase 1: Scraping Layer MVP (CURRENT FOCUS)

### 1.1 Target Loyalty Programs (Priority Order)

| Priority | Program | Airline | Difficulty | Notes |
|----------|---------|---------|------------|-------|
| P1 | United MileagePlus | United Airlines | Medium | Good starting point, well-documented |
| P1 | Air Canada Aeroplan | Air Canada | Medium | Popular for Star Alliance |
| P2 | American AAdvantage | American Airlines | Medium | OneWorld Alliance |
| P2 | Delta SkyMiles | Delta | Hard | Heavy bot protection |
| P3 | Emirates Skywards | Emirates | Medium | Premium routes |
| P3 | Qantas Frequent Flyer | Qantas | Medium | Good for Pacific routes |
| P4 | British Airways Avios | BA | Medium | Europe coverage |
| P4 | Singapore KrisFlyer | Singapore | Medium | Asia coverage |

### 1.2 Data Model - Flight Availability

```python
class FlightAvailability:
    # Identifiers
    id: str                          # Unique identifier
    source_program: str              # e.g., "united_mileageplus"
    
    # Route Information
    origin: str                      # IATA code (e.g., "JFK")
    destination: str                 # IATA code (e.g., "LHR")
    
    # Flight Details
    airline: str                     # Operating airline
    flight_number: str               # e.g., "UA100"
    departure_date: date             # Flight date
    departure_time: time             # Departure time
    arrival_time: time               # Arrival time
    duration_minutes: int            # Total flight duration
    
    # Award Details
    cabin_class: str                 # economy, premium_economy, business, first
    points_required: int             # Miles/points needed
    taxes_fees: float                # Cash portion (USD)
    seats_available: int             # Number of award seats (if known)
    
    # Routing
    stops: int                       # 0 = direct
    connection_airports: list[str]  # List of connection IATA codes
    
    # Metadata
    scraped_at: datetime             # When data was collected
    expires_at: datetime             # When to consider data stale
    raw_data: dict                   # Original scraped data for debugging
```

### 1.3 Scraping Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SCRAPING LAYER                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Proxy     │    │ User Agent  │    │  Browser    │         │
│  │  Rotator    │    │  Rotator    │    │  Manager    │         │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘         │
│         │                  │                  │                 │
│         └──────────────────┼──────────────────┘                 │
│                            │                                    │
│                   ┌────────▼────────┐                           │
│                   │  Base Scraper   │                           │
│                   │    (Abstract)   │                           │
│                   └────────┬────────┘                           │
│                            │                                    │
│         ┌──────────────────┼──────────────────┐                 │
│         │                  │                  │                 │
│  ┌──────▼──────┐   ┌──────▼──────┐   ┌──────▼──────┐          │
│  │   United    │   │  Aeroplan   │   │  Emirates   │  ...      │
│  │   Scraper   │   │  Scraper    │   │  Scraper    │          │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘          │
│         │                  │                  │                 │
│         └──────────────────┼──────────────────┘                 │
│                            │                                    │
│                   ┌────────▼────────┐                           │
│                   │  Flight Parser  │                           │
│                   │  (Normalizer)   │                           │
│                   └────────┬────────┘                           │
│                            │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
                   ┌─────────────────┐
                   │  Data Storage   │
                   │  (In-Memory MVP)│
                   │  (DB Future)    │
                   └─────────────────┘
```

### 1.4 Anti-Detection Strategy

#### User Agent Rotation
- Maintain pool of 50+ real browser user agents
- Rotate per request or per session
- Match user agent to browser fingerprint

#### Proxy Rotation
- Support for HTTP/HTTPS/SOCKS5 proxies
- Free proxy sources for MVP:
  - Free proxy lists (less reliable)
  - Residential proxy rotation
- Configurable rotation strategy:
  - Per request
  - Per domain
  - On error/block

#### Request Patterns
- Random delays between requests (2-10 seconds)
- Mimic human browsing patterns
- Session persistence where needed
- Cookie handling

#### Browser Fingerprinting Evasion
- Selenium with undetected-chromedriver
- Randomized viewport sizes
- WebGL/Canvas fingerprint randomization
- Timezone matching with proxy location

### 1.5 Scraper Interface Contract

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import date

class BaseScraper(ABC):
    """Abstract base class for all loyalty program scrapers"""
    
    @property
    @abstractmethod
    def program_name(self) -> str:
        """Return the loyalty program identifier"""
        pass
    
    @property
    @abstractmethod
    def supported_airlines(self) -> List[str]:
        """Return list of airlines searchable through this program"""
        pass
    
    @abstractmethod
    async def search_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: Optional[str] = None,
        passengers: int = 1
    ) -> List[FlightAvailability]:
        """
        Search for award availability on a specific route/date.
        Returns normalized FlightAvailability objects.
        """
        pass
    
    @abstractmethod
    async def search_date_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        cabin_class: Optional[str] = None
    ) -> List[FlightAvailability]:
        """
        Search availability across a date range.
        """
        pass
    
    async def health_check(self) -> bool:
        """Verify scraper can connect and authenticate"""
        pass
```

---

## Phase 2: API Layer (Minimal for MVP)

### 2.1 Endpoints

```
POST /api/search
    - origin: str (required)
    - destination: str (required)  
    - departure_date: date (required)
    - return_date: date (optional)
    - cabin_class: str (optional)
    - programs: list[str] (optional, default=all)

GET /api/availability
    - Query cached/scraped results
    - Supports filtering and pagination

GET /api/programs
    - List available loyalty programs
    - Status of each scraper

POST /api/scrape/trigger
    - Manually trigger a scrape job
    - For testing purposes
```

### 2.2 In-Memory Storage (MVP)

```python
# Simple in-memory store for MVP
class FlightStore:
    def __init__(self):
        self._flights: Dict[str, FlightAvailability] = {}
        self._index_by_route: Dict[str, List[str]] = {}
    
    def add(self, flight: FlightAvailability): ...
    def search(self, origin, dest, date, filters): ...
    def get_all(self): ...
    def clear_expired(self): ...
```

---

## Phase 3: Frontend (Simple Table UI)

### 3.1 Features
- Search form (origin, destination, date range, cabin class)
- Results table with sortable columns
- Filters sidebar:
  - Cabin class
  - Max points
  - Airlines
  - Direct flights only
  - Programs
- Sort options:
  - Points (low to high)
  - Duration
  - Departure time

### 3.2 Tech Stack
- Pure HTML/CSS/JavaScript (no framework)
- Fetch API for backend calls
- CSS Grid/Flexbox for layout
- DataTables.js or similar for table functionality

---

## Technical Requirements

### Dependencies (requirements.txt)

```
# Web Scraping
selenium>=4.15.0
undetected-chromedriver>=3.5.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
httpx>=0.25.0
fake-useragent>=1.4.0

# Async & Concurrency
asyncio
aiohttp>=3.9.0

# API Framework
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.5.0

# Utilities
python-dotenv>=1.0.0
loguru>=0.7.0
tenacity>=8.2.0  # Retry logic

# Development
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

### Environment Variables

```env
# Scraper Settings
SCRAPE_DELAY_MIN=2
SCRAPE_DELAY_MAX=10
CONCURRENT_SCRAPERS=3
HEADLESS_MODE=true

# Proxy Configuration
PROXY_ENABLED=false
PROXY_LIST_URL=
PROXY_ROTATION_STRATEGY=per_request

# Browser Settings
CHROME_DRIVER_PATH=
BROWSER_TIMEOUT=30

# API Settings
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000

# Logging
LOG_LEVEL=INFO
```

---

## MVP Success Criteria

1. ✅ Successfully scrape at least 2 loyalty programs
2. ✅ Normalize data into consistent format
3. ✅ Avoid detection/blocking for 100+ requests
4. ✅ API returns search results within 30 seconds
5. ✅ Frontend displays results with basic filtering
6. ✅ Run locally without external dependencies (no DB/Redis)

---

## Future Roadmap (Post-MVP)

### Database Layer
- PostgreSQL for persistent storage
- Indexing strategy for fast queries
- Historical data retention

### Caching Layer
- Redis for hot routes
- Cache invalidation strategy

### Infrastructure
- Docker containerization
- AWS deployment (EC2/ECS)
- Scheduled scraping jobs

### Advanced Features
- Price alerts
- Email notifications
- User accounts
- More loyalty programs

---

## File Structure (MVP Focus)

```
seatsaero/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── search.py        # Search endpoints
│   │   │   └── health.py        # Health check
│   │   └── schemas/
│   │       ├── __init__.py
│   │       └── flight.py        # Pydantic models
│   │
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── base.py              # Abstract base scraper
│   │   ├── browser.py           # Browser/Selenium manager
│   │   ├── proxy.py             # Proxy rotation
│   │   ├── useragent.py         # User agent rotation
│   │   ├── programs/
│   │   │   ├── __init__.py
│   │   │   ├── united.py        # United MileagePlus
│   │   │   └── aeroplan.py      # Air Canada Aeroplan
│   │   └── parsers/
│   │       ├── __init__.py
│   │       └── normalizer.py    # Data normalization
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   └── memory.py            # In-memory store (MVP)
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Configuration
│   │
│   ├── requirements.txt
│   └── run.py                   # Entry point
│
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── app.js
│       ├── api.js
│       └── filters.js
│
├── docs/
│   └── MVP_REQUIREMENTS.md      # This document
│
├── .env.example
├── .gitignore
├── docker-compose.yml           # For future use
└── README.md
```

---

## Next Steps

1. **Scaffold project structure** ✓
2. **Implement base scraper components**
3. **Build United MileagePlus scraper** (first target)
4. **Create minimal FastAPI endpoints**
5. **Build simple frontend table**
6. **Test end-to-end flow**
7. **Add second scraper (Aeroplan)**
8. **Iterate and improve anti-detection**
