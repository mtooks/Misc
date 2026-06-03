import asyncio, re, pandas as pd
from playwright.async_api import async_playwright
from datetime import datetime

BASE = ("https://www.golfv2.com/schedule?"
        "_mt=%2Fschedule%2Fdaily%2F48541%3FactiveDate%3D{}")  # 48541 = Tribeca location ID

async def scrape_day(play, date_str: str) -> pd.DataFrame:
    url = BASE.format(date_str)
    browser = await play.chromium.launch(
        headless=False,
        args=['--disable-blink-features=AutomationControlled']
    )
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    )
    page = await context.new_page()
    
    
    print(f"Navigating to: {url}")
    await page.goto(url)
    
    # Take screenshot before cookie handling

    await page.screenshot(path=f'before_cookie_{date_str}.png')
    
    # Wait for iframe with increased timeout
    print("Waiting for iframe to load...")
    await page.wait_for_selector('iframe[name*="zoid"]', timeout=60000)
    
    # Save the page HTML for debugging
    # html_content = await page.content()
    # with open(f'page_1sec_{date_str}.html', 'w', encoding='utf-8') as f:
    #     f.write(html_content)
        
    # Get the booking iframe
    target_frame = None
    for frame in page.frames:
        if "zoid" in frame.name and "mariana" in frame.url.lower():
            target_frame = frame
            break
    
    # if not target_frame:
    #     raise Exception("Could not find booking iframe")
        
    # Wait longer for frame content to load
    await page.wait_for_timeout(8000)


    # Save the frame HTML for debugging
    frame_html_content = await target_frame.content()  
    #save html content to file
    with open(f'frame_1sec_{date_str}.html', 'w', encoding='utf-8') as f:
        f.write(frame_html_content) 

    # Get date and location info
    # try:
    # Extract slot data using more specific class selectors
    time_elems = await target_frame.query_selector_all('p[class*="BoldLabel"]')
    location_elems = await target_frame.query_selector_all('p[class*="LineItem"]')
    status_elems = await target_frame.query_selector_all('p[class*="BoldLabel"][class*="StyledNoWrapLabel"]')

    # Print raw data for debugging
    for time, loc, status in zip(time_elems, location_elems, status_elems):
        time_text = await time.text_content()
        loc_text = await loc.text_content() 
        status_text = await status.text_content()
        print(f"Found slot: {time_text} at {loc_text} - {status_text}")
    # date_elem = await target_frame.wait_for_selector('div[data-testid="date-display"], div[class*="DateDisplay"]', timeout=5000)
    # location_elem = await target_frame.wait_for_selector('div[data-testid="location-info"], div[class*="LocationInfo"]', timeout=5000)
    # bay_info_elem = await target_frame.wait_for_selector('div[data-testid="bay-info"], div[class*="BayInfo"]', timeout=5000)

    # displayed_date = await date_elem.text_content() if date_elem else "Date not found"
    # location = await location_elem.text_content() if location_elem else "Location not found"
    # bay_info = await bay_info_elem.text_content() if bay_info_elem else "Bay info not found"

    # print(f"\nDate displayed: {displayed_date}")
    # print(f"Location: {location}")
    # print(f"Bay information: {bay_info}\n")
    # # except Exception as e:
    # # print(f"Error getting page info: {e}")

    # # ...rest of existing code for finding time slots...
    
    # Handle cookie consent if present
    try:
        cookie_button = await target_frame.wait_for_selector(
            'button[data-test-button="accept-all-cookies"], [aria-label*="cookie"], [class*="cookie-consent"] button',
            timeout=5000,
            state='visible'
        )
        if cookie_button:
            await cookie_button.click()
            print('Cookie pressed')
            await page.wait_for_timeout(5000)
    except Exception as e:
        print(f"No cookie popup found: {e}")
    
    # Take debug screenshot
    await page.screenshot(path=f'debug_screenshot_{date_str}.png')
    
    # Try to find time slots using more specific selectors
    slots = await target_frame.query_selector_all('div[data-testid*="time-slot"], div[class*="TimeSlot"], div[class*="time-slot"]')
    
    if not slots:
        print("No time slots found, taking full page screenshot for debugging")
        await page.screenshot(path=f'debug_full_{date_str}.png')
        return pd.DataFrame()
        
    bookings = []
    for slot in slots:
        try:
            time_elem = await slot.query_selector('p[class*="time"], span[class*="time"]')
            status_elem = await slot.query_selector('p[class*="status"], span[class*="status"]')
            
            if time_elem and status_elem:
                time_text = await time_elem.text_content()
                status_text = await status_elem.text_content()
                
                # Parse time and get booking count
                time = datetime.strptime(time_text.strip(), '%I:%M %p').time()
                booked = bookings_from_label(status_text)
                
                bookings.append({
                    'date': date_str,
                    'time': time,
                    'status': status_text.strip(),
                    'booked_bays': booked
                })
        except Exception as e:
            print(f"Error parsing slot: {e}")
            
    return pd.DataFrame(bookings)
        
    # except Exception as e:
    #     print(f"Error scraping page: {e}")
    #     await page.screenshot(path=f'debug_error_{date_str}.png')
    #     return pd.DataFrame()
        
    # finally:
    await browser.close()

def bookings_from_label(text: str) -> int:
    text = text.lower()
    if "waitlist" in text:
        return 4  # all bays taken
    
    m = re.search(r'(\d+)\s*/\s*(\d+)\s*open', text, re.I)
    if not m:
        if "(1/2 open)" in text.lower():
            return 2  # private event took 2 bays
        return 0  # safety fallback
        
    open_cnt, total = map(int, m.groups())
    
    if total == 4:  # e.g. "3/4 Open"
        return 4 - open_cnt
    elif total == 2:  # e.g. "(1/2 Open)" → 2 bays booked privately
        return 2
    return 0

async def main():
    async with async_playwright() as play:
        # Scrape next 7 days
        days = [(pd.Timestamp.now() + pd.Timedelta(days=i)).strftime("%Y-%m-%d") 
                for i in range(7)]
                
        #Testing: uncomment below
        days = days[0:1]
        print(f"Scraping days: {', '.join(days)}\n")
        frames = []
        for day in days:
            print(f"\nScraping {day}...")
            df = await scrape_day(play, day)
            frames.append(df)
            
    if frames:
        df = pd.concat(frames, ignore_index=True)
        
        # Calculate daily utilization
        summary = (df.groupby("date")["booked_bays"]
                    .agg(['sum', 'count'])
                    .eval('utilization = sum / (count * 4)')
                    .round(3))
                    
        print("\nDaily Bay Utilization:")
        print(summary[['utilization']])

if __name__ == "__main__":
    asyncio.run(main())
