# Seats Aero Clone - Award Flight Search

A web application that scrapes airline loyalty program websites to find award seat availability, consolidating data into a searchable interface with granular filtering capabilities.

## 🎯 Project Overview

This MVP focuses on the **scraping layer** - collecting award flight availability from multiple loyalty programs and presenting it in a unified search interface.

### Tech Stack
- **Backend**: Python + FastAPI
- **Scraping**: Selenium + undetected-chromedriver + BeautifulSoup
- **Storage**: In-memory (MVP) → PostgreSQL (future)
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Anti-Detection**: Proxy rotation, user agent rotation, request delays

## 📁 Project Structure

```
seatsaero/
├── backend/
│   ├── api/                    # FastAPI application
│   │   ├── main.py            # App entry point
│   │   └── routes/            # API endpoints
│   │       ├── search.py      # Flight search
│   │       ├── programs.py    # Loyalty programs
│   │       └── health.py      # Health checks
│   │
│   ├── scraper/               # Core scraping layer
│   │   ├── base.py            # Abstract base scraper
│   │   ├── browser.py         # Selenium/Chrome manager
│   │   ├── proxy.py           # Proxy rotation
│   │   ├── useragent.py       # User agent rotation
│   │   ├── programs/          # Loyalty program scrapers
│   │   │   ├── united.py      # United MileagePlus
│   │   │   └── aeroplan.py    # Air Canada Aeroplan
│   │   └── parsers/
│   │       └── normalizer.py  # Data normalization
│   │
│   ├── storage/
│   │   └── memory.py          # In-memory store (MVP)
│   │
│   ├── config/
│   │   └── settings.py        # Configuration
│   │
│   ├── requirements.txt       # Python dependencies
│   └── run.py                 # Entry point
│
├── frontend/
│   ├── index.html             # Main page
│   ├── css/styles.css         # Styling
│   └── js/
│       ├── app.js             # Main app logic
│       ├── api.js             # API client
│       ├── filters.js         # Filtering logic
│       └── table.js           # Results table
│
├── docs/
│   └── MVP_REQUIREMENTS.md    # Detailed requirements
│
├── .env.example               # Environment variables template
└── README.md
```

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Google Chrome browser
- ChromeDriver (auto-installed by undetected-chromedriver)

### Installation

1. **Clone and setup:**
```bash
cd seatsaero

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
cd backend
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
# Copy example config
cp .env.example .env

# Edit .env as needed (defaults work for local development)
```

3. **Run the backend:**
```bash
cd backend
python run.py
```

The API will start at `http://localhost:8000`

4. **Open the frontend:**
```bash
# Simply open in browser
open frontend/index.html
# Or serve with Python
cd frontend && python -m http.server 3000
```

## 🔌 API Endpoints

### Search Flights
```http
POST /api/search
Content-Type: application/json

{
  "origin": "JFK",
  "destination": "LHR",
  "departure_date": "2024-03-15",
  "cabin_class": "business",
  "passengers": 1
}
```

### Get Cached Availability
```http
GET /api/availability?origin=JFK&destination=LHR&date=2024-03-15&cabin=business
```

### List Programs
```http
GET /api/programs
```

### Trigger Scrape
```http
POST /api/scrape
Content-Type: application/json

{
  "origin": "JFK",
  "destination": "LHR",
  "departure_date": "2024-03-15"
}
```

### Health Check
```http
GET /health
GET /stats
```

## 🎯 Supported Loyalty Programs

| Program | Status | Notes |
|---------|--------|-------|
| United MileagePlus | ✅ Implemented | Star Alliance awards |
| Air Canada Aeroplan | ✅ Implemented | Star Alliance awards |
| American AAdvantage | 📋 Planned | OneWorld awards |
| Delta SkyMiles | 📋 Planned | SkyTeam awards |

## 🔧 Configuration

Key environment variables (`.env`):

```env
# Scraping delays (seconds)
SCRAPE_DELAY_MIN=2
SCRAPE_DELAY_MAX=10

# Browser settings
HEADLESS_MODE=true
BROWSER_TIMEOUT=30

# Proxy (optional)
PROXY_ENABLED=false

# API
API_PORT=8000
```

## 🛡️ Anti-Detection Features

1. **User Agent Rotation**: Pool of 50+ real browser user agents
2. **Proxy Support**: HTTP/HTTPS/SOCKS5 proxy rotation
3. **Request Delays**: Random delays between requests (2-10s)
4. **Browser Fingerprinting**: undetected-chromedriver for Selenium
5. **Session Management**: Cookie persistence where needed

## 📊 Data Model

```python
FlightAvailability:
  - id: str                    # Unique identifier
  - source_program: str        # e.g., "united_mileageplus"
  - origin: str                # IATA code (e.g., "JFK")
  - destination: str           # IATA code (e.g., "LHR")
  - airline: str               # Operating airline
  - flight_number: str         # e.g., "UA100"
  - departure_date: date
  - departure_time: str
  - arrival_time: str
  - duration_minutes: int
  - cabin_class: str           # economy/premium_economy/business/first
  - points_required: int
  - taxes_fees: float
  - seats_available: int
  - stops: int
  - connection_airports: list
  - scraped_at: datetime
```

## 🗺️ Roadmap

### Phase 1 (MVP) ✅
- [x] Core scraping architecture
- [x] United MileagePlus scraper
- [x] Aeroplan scraper
- [x] In-memory storage
- [x] FastAPI backend
- [x] Simple frontend with filters

### Phase 2 (Enhancement)
- [ ] Add more loyalty programs (AA, Delta, Emirates)
- [ ] PostgreSQL persistence
- [ ] Redis caching
- [ ] Price alerts
- [ ] Email notifications

### Phase 3 (Scale)
- [ ] Docker containerization
- [ ] AWS deployment
- [ ] Scheduled scraping jobs
- [ ] Rate limiting per user
- [ ] User accounts

## ⚠️ Disclaimer

This project is for educational purposes. Web scraping may violate terms of service of target websites. Use responsibly and respect rate limits.

## 📝 License

MIT License
