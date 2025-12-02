import asyncio
from scraper.playwright_browser import AsyncPlaywrightStealthBrowser

async def test():
    async with AsyncPlaywrightStealthBrowser() as browser:
        page = await browser.new_page()
        
        url = 'https://www.google.com/travel/flights?q=Flights%20to%20JFK%20from%20SFO%20on%202025-12-15&curr=USD&hl=en'
        
        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(5)
        
        # Get text content
        text = await page.evaluate('document.body.innerText')
        
        # Save the full text for analysis
        with open('/tmp/google_flights_text.txt', 'w') as f:
            f.write(text)
        print("Saved text to /tmp/google_flights_text.txt")
        
        # Look for flight-like patterns
        lines = text.split('\n')
        print(f"Total lines: {len(lines)}")
        
        for i, line in enumerate(lines):
            if '$' in line and ('AM' in line or 'PM' in line):
                print(f'\nLine {i}: {line[:150]}')
                if i < len(lines) - 3:
                    print(f'  Next: {lines[i+1][:100]}')
                    print(f'  Next: {lines[i+2][:100]}')

asyncio.run(test())
