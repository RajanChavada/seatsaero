# Target Routes Strategy for MVP

## Overview
Based on Seats.aero's supported programs and your target destinations, here's the strategic plan.

## ✅ Implemented Scrapers

| Program | File | Status | Target Routes |
|---------|------|--------|---------------|
| **JetBlue TrueBlue** | `jetblue.py` | ✅ Code Complete | USA, Mexico, Caribbean |
| **Lufthansa Miles & More** | `lufthansa.py` | ✅ Code Complete | Europe (Germany hub) |
| **Virgin Atlantic Flying Club** | `virgin_atlantic.py` | ✅ Code Complete | UK, Transatlantic |
| **Air Canada Aeroplan** | `aeroplan.py` | ✅ Code Complete | Canada, India |
| **United MileagePlus** | `united.py` | ✅ Code Complete | USA (heavy bot detection) |
| **Demo Mode** | `demo.py` | ✅ Working | Fallback for testing |

## Smart Route Selection

The API automatically selects the best programs based on route:

```
YYZ → DEL (Canada to India):    [aeroplan, demo]
JFK → CUN (USA to Mexico):      [jetblue, united, demo]
LHR → JFK (UK to USA):          [virgin_atlantic, united, demo]
FRA → YYZ (Germany to Canada):  [aeroplan, lufthansa, demo]
```

## Target Destinations & Best Programs

### 1. **Europe** 🇪🇺
| Destination | Best Programs | Notes |
|------------|---------------|-------|
| Germany (FRA, MUC) | **Lufthansa Miles & More**, Air Canada Aeroplan | LH is home carrier |
| UK (LHR, LGW) | **Virgin Atlantic Flying Club**, BA Avios | VS has great sweet spots |
| France (CDG) | Air Canada Aeroplan, Lufthansa | Star Alliance connections |

### 2. **India** 🇮🇳
| Destination | Best Programs | Notes |
|------------|---------------|-------|
| Delhi (DEL), Mumbai (BOM) | **Air Canada Aeroplan**, Singapore KrisFlyer, Turkish Miles&Smiles | AC has direct YYZ-DEL |
| Bangalore (BLR) | Singapore KrisFlyer | SQ connection via SIN |

### 3. **Mexico** 🇲🇽
| Destination | Best Programs | Notes |
|------------|---------------|-------|
| Mexico City (MEX) | **United MileagePlus**, Aeroplan | UA hub city |
| Cancun (CUN) | United, JetBlue TrueBlue | Popular leisure route |

### 4. **Spain** 🇪🇸
| Destination | Best Programs | Notes |
|------------|---------------|-------|
| Madrid (MAD) | **Iberia Avios**, Air Canada Aeroplan | IB is home carrier |
| Barcelona (BCN) | Lufthansa, Virgin Atlantic | Good availability |

### 5. **Canada** 🇨🇦
| Destination | Best Programs | Notes |
|------------|---------------|-------|
| Calgary (YYC), Toronto (YYZ) | **Air Canada Aeroplan** | AC is home carrier |
| Vancouver (YVR) | Aeroplan, United | West coast hub |

### 6. **USA** 🇺🇸
| Destination | Best Programs | Notes |
|------------|---------------|-------|
| New York (JFK, EWR) | **United MileagePlus**, JetBlue | UA hub |
| Los Angeles (LAX) | United, Aeroplan | Major hub |
| Miami (MIA) | **JetBlue TrueBlue** | Focus city |

---

## MVP Priority Scrapers (Phase 1)

Based on ease of implementation and route coverage:

### Priority 1 - Core Programs (Build First)
| Program | Routes Covered | Difficulty | Notes |
|---------|---------------|------------|-------|
| **Air Canada Aeroplan** | Canada, Europe, India | Medium | Star Alliance, good API docs |
| **United MileagePlus** | USA, Mexico | Hard | Heavy bot detection (already built) |
| **Lufthansa Miles & More** | Europe | Medium | Star Alliance partner |

### Priority 2 - Secondary Programs
| Program | Routes Covered | Difficulty | Notes |
|---------|---------------|------------|-------|
| **JetBlue TrueBlue** | USA, Mexico, Caribbean | Easy | Simple website |
| **Virgin Atlantic** | UK, USA | Medium | Good availability |
| **Singapore KrisFlyer** | Asia, India | Hard | Complex site |

### Priority 3 - Future
| Program | Routes Covered |
|---------|---------------|
| Turkish Miles&Smiles | Global via IST |
| Qantas Frequent Flyer | Australia, Asia |
| Gol Smiles | South America |

---

## Sample Routes for Testing

### MVP Test Routes
```
Toronto (YYZ) → Frankfurt (FRA) - Aeroplan, Lufthansa
Toronto (YYZ) → Calgary (YYC) - Aeroplan  
Toronto (YYZ) → Delhi (DEL) - Aeroplan
New York (EWR) → Mexico City (MEX) - United
New York (JFK) → London (LHR) - Virgin Atlantic
New York (JFK) → Madrid (MAD) - Iberia Avios
Los Angeles (LAX) → Cancun (CUN) - United, JetBlue
```

---

## Technical Approach by Program

### Air Canada Aeroplan
- **URL**: aircanada.com/aeroplan
- **Method**: Browser scraping (no public API)
- **Anti-bot**: Moderate - Akamai
- **Strategy**: Use Canadian proxies, mimic logged-out flow

### Lufthansa Miles & More
- **URL**: lufthansa.com/milesandmore  
- **Method**: API exists (needs session) + Browser fallback
- **Anti-bot**: Moderate
- **Strategy**: Get session via browser, then use API

### JetBlue TrueBlue
- **URL**: jetblue.com/trueblue
- **Method**: Browser scraping
- **Anti-bot**: Light - easier to scrape
- **Strategy**: Direct browser, minimal stealth needed

### Virgin Atlantic Flying Club
- **URL**: virginatlantic.com
- **Method**: Browser scraping
- **Anti-bot**: Moderate - Cloudflare
- **Strategy**: Use undetected-chromedriver

### Singapore KrisFlyer
- **URL**: singaporeair.com/krisflyer
- **Method**: Browser scraping
- **Anti-bot**: Heavy - Imperva
- **Strategy**: May need residential proxies

---

## Implementation Order

1. **Day 1**: Lufthansa Miles & More (Europe focus)
2. **Day 2**: JetBlue TrueBlue (Easiest, good for confidence)
3. **Day 3**: Improve Aeroplan (Canada + India routes)
4. **Day 4**: Virgin Atlantic (UK routes)
5. **Day 5**: Testing & Integration

## Success Metrics
- [ ] At least 3 programs returning real data
- [ ] Cover routes to: Europe, Canada, Mexico, USA
- [ ] Response time < 30 seconds per search
- [ ] Success rate > 50% without CAPTCHA
