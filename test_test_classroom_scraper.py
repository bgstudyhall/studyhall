#!/usr/bin/env python3
"""
Test script to manually scrape the Test classroom
"""

import os
import sys
import json
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("="*70)
print("  TESTING TEST CLASSROOM SCRAPER")
print("="*70)

# Check if files exist
print("\n1. Checking configuration files...")
if os.path.exists('google_cookies.pkl'):
    print("   ✅ google_cookies.pkl exists")
else:
    print("   ❌ google_cookies.pkl NOT found")
    sys.exit(1)

# Try to import the necessary modules
print("\n2. Checking dependencies...")
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    import pickle
    import time
    print("   ✅ All dependencies available")
except ImportError as e:
    print(f"   ❌ Missing dependency: {e}")
    sys.exit(1)

# Configuration
classroom_id = 'ODM4ODA4ODcyMTIw'
print(f"\n3. Test Classroom ID: {classroom_id}")

# Set up driver function
def get_classroom_driver(load_cookies=False, headless=False):
    """Create and configure Chrome driver for Google Classroom."""
    options = Options()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=options)

    if load_cookies and os.path.exists('google_cookies.pkl'):
        driver.get('https://classroom.google.com')
        with open('google_cookies.pkl', 'rb') as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except:
                    pass
        driver.refresh()

    return driver

# Test scraping
print("\n4. Testing scraper (this may take 10-15 seconds)...")
print("   Opening Chrome...")

driver = None
try:
    driver = get_classroom_driver(load_cookies=True, headless=False)
    print("   ✅ Chrome browser opened")

    print(f"   🔄 Navigating to test classroom: {classroom_id}")
    driver.get(f'https://classroom.google.com/u/0/c/{classroom_id}')

    print("   ⏳ Waiting for page to load...")
    time.sleep(5)

    # MANUAL CONFIRMATION - Wait for user to switch accounts if needed
    print("\n" + "="*70)
    print("   ⚠️  BROWSER IS OPEN - Check if you're logged in with correct account")
    print("   If you need to switch accounts, do it now in the browser window")
    print("="*70)
    input("   👉 Press ENTER when ready to continue scraping... ")
    print("\n   ✅ Continuing with scraping...")

    # Scroll to load content - scroll multiple times to ensure all announcements load
    print("   🔄 Scrolling to load all announcements...")
    for i in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

    # Scroll back to top
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(2)

    # Scroll down again to make sure everything is loaded
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    # Try to get classroom name
    try:
        name_elem = driver.find_element(By.CSS_SELECTOR, '.YVvGBb.z3vRcc, .fqWr5c')
        classroom_name = name_elem.text.strip()
        print(f"   ✅ Classroom name: {classroom_name}")
    except Exception as e:
        classroom_name = "Test"
        print(f"   ⚠️  Could not get classroom name, using default: Test")

    # Find announcements
    print("   🔍 Looking for announcements...")
    announcement_elements = driver.find_elements(By.CSS_SELECTOR, '[data-stream-item-id]')
    print(f"   📝 Found {len(announcement_elements)} announcement elements")

    if len(announcement_elements) == 0:
        print("\n   ⚠️  No announcements found!")
    else:
        print("\n   ✅ Found announcements! Parsing them...")
        announcements = []

        for i, elem in enumerate(announcement_elements):
            try:
                full_text = elem.text.strip()
                print(f"\n   [DEBUG {i+1}] Full text length: {len(full_text)}")
                print(f"   [DEBUG {i+1}] First 100 chars: {full_text[:100]}")

                if not full_text or len(full_text) < 20:
                    print(f"   [DEBUG {i+1}] SKIPPED - Text too short (len={len(full_text)})")
                    continue

                # Extract announcement ID and URL
                announcement_id = elem.get_attribute('data-stream-item-id')
                announcement_url = f'https://classroom.google.com/c/{classroom_id}/p/{announcement_id}/details' if announcement_id else None

                lines = full_text.split('\n')

                # Find date
                date_text = ""
                for line in lines[:10]:
                    if any(month in line for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                        date_text = line.strip()
                        break

                # Extract links from the announcement
                links = []
                try:
                    link_elements = elem.find_elements(By.CSS_SELECTOR, 'a[href]')
                    for link_elem in link_elements:
                        href = link_elem.get_attribute('href')
                        if href and ('http' in href) and ('classroom.google.com' not in href):
                            link_text = link_elem.text.strip() or href
                            links.append({'url': href, 'title': link_text})
                except:
                    pass

                # Get announcement content
                announcement_text = ""
                try:
                    content_elem = elem.find_element(By.CSS_SELECTOR, '.pco8Kc')
                    announcement_text = content_elem.text.strip()
                except:
                    announcement_text = full_text

                # Clean up the text
                lines_to_remove = [
                    'Add comment', 'class comments', 'More options', 'more_vert',
                    'Created', 'Post by', '(Edited', 'Edited'
                ]
                for removal in lines_to_remove:
                    announcement_text = announcement_text.replace(removal, '')

                # Clean line by line
                text_lines = announcement_text.split('\n')
                cleaned_lines = []
                skip_names = ['Emily Hall', 'Jan 8', 'Yesterday', 'Today', 'Jan 7', 'Jan 9', 'Jan 10', 'Jan 11']

                for line in text_lines:
                    line = line.strip()
                    if line and len(line) > 3 and line not in skip_names:
                        if len(line) > 15 or not any(month in line for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']):
                            cleaned_lines.append(line)

                announcement_text = '\n\n'.join(cleaned_lines).strip()

                print(f"   [DEBUG {i+1}] Cleaned text: '{announcement_text}' (len={len(announcement_text)})")

                # Build materials list
                materials = []
                for link in links:
                    materials.append({
                        'type': 'link',
                        'url': link['url'],
                        'title': link['title'] if len(link['title']) < 100 else 'View Link'
                    })

                if announcement_text and len(announcement_text) > 4:
                    preview = announcement_text[:100].replace('\n', ' ')
                    print(f"   [{i+1}] {preview}... ({len(materials)} links)")
                    announcements.append({
                        'id': str(len(announcements)),
                        'text': announcement_text,
                        'clean_text': announcement_text,
                        'date': date_text or 'Recently',
                        'materials': materials,
                        'classroom_url': announcement_url,
                        'links': [{'url': m['url'], 'text': m['title']} for m in materials]
                    })

            except Exception as e:
                print(f"   ⚠️  Error parsing announcement {i+1}: {e}")

        if announcements:
            print(f"\n   ✅ Successfully parsed {len(announcements)} announcements!")

            # Save to cache
            cache = {
                'announcements': announcements,
                'last_updated': datetime.now().isoformat(),
                'classroom_name': classroom_name
            }
            with open('test_announcements_cache.json', 'w') as f:
                json.dump(cache, f, indent=2)
            print("   💾 Saved to test_announcements_cache.json")
        else:
            print("\n   ⚠️  Could not parse any announcements")

    driver.quit()
    print("\n" + "="*70)
    print("  TEST COMPLETE!")
    print("="*70)

except KeyboardInterrupt:
    print("\n\n   ❌ Test cancelled by user")
    if driver:
        driver.quit()
except Exception as e:
    print(f"\n   ❌ Error during test: {e}")
    import traceback
    traceback.print_exc()
    if driver:
        driver.quit()
    sys.exit(1)
