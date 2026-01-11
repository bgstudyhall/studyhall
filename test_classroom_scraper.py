#!/usr/bin/env python3
"""
Test script to manually trigger Google Classroom scraping
This helps debug issues without running the full Flask app
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("="*70)
print("  TESTING GOOGLE CLASSROOM SCRAPER")
print("="*70)

# Check if files exist
print("\n1. Checking configuration files...")
if os.path.exists('classroom_config.json'):
    print("   ✅ classroom_config.json exists")
else:
    print("   ❌ classroom_config.json NOT found")
    print("   Run: python3 setup_classroom.py")
    sys.exit(1)

if os.path.exists('google_cookies.pkl'):
    print("   ✅ google_cookies.pkl exists")
else:
    print("   ❌ google_cookies.pkl NOT found")
    print("   Run: python3 setup_classroom.py")
    sys.exit(1)

# Try to import the necessary modules
print("\n2. Checking dependencies...")
try:
    from selenium import webdriver
    print("   ✅ Selenium installed")
except ImportError:
    print("   ❌ Selenium NOT installed")
    print("   Install with: pip install selenium")
    sys.exit(1)

try:
    import pickle
    import json
    from datetime import datetime
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    import time
    print("   ✅ All dependencies available")
except ImportError as e:
    print(f"   ❌ Missing dependency: {e}")
    sys.exit(1)

# Load configuration
print("\n3. Loading configuration...")
with open('classroom_config.json', 'r') as f:
    config = json.load(f)
    classroom_id = config.get('classroom_id')
    print(f"   ✅ Classroom ID: {classroom_id}")

# Set up driver function (copied from flask_app.py)
def get_classroom_driver(load_cookies=False, headless=True):
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
print("   Opening Chrome in headless mode...")

driver = None
try:
    driver = get_classroom_driver(load_cookies=True, headless=False)  # Non-headless for debugging
    print("   ✅ Chrome browser opened")

    print(f"   🔄 Navigating to classroom: {classroom_id}")
    driver.get(f'https://classroom.google.com/u/0/c/{classroom_id}')

    print("   ⏳ Waiting for page to load...")
    time.sleep(5)

    # Check current URL
    current_url = driver.current_url
    print(f"   📍 Current URL: {current_url}")

    # Check if we're logged in
    if 'accounts.google.com' in current_url or 'signin' in current_url.lower():
        print("\n   ❌ NOT LOGGED IN - Cookies may have expired!")
        print("   Solution: Run setup_classroom.py again to refresh cookies")
        driver.quit()
        sys.exit(1)

    # Scroll to load content
    print("   🔄 Scrolling to load announcements...")
    driver.execute_script("window.scrollTo(0, 1000);")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 2000);")
    time.sleep(2)

    # Try to get classroom name
    try:
        name_elem = driver.find_element(By.CSS_SELECTOR, '.YVvGBb.z3vRcc, .fqWr5c')
        classroom_name = name_elem.text.strip()
        print(f"   ✅ Classroom name: {classroom_name}")
    except Exception as e:
        print(f"   ⚠️  Could not get classroom name: {e}")
        classroom_name = "Unknown"

    # Find announcements
    print("   🔍 Looking for announcements...")
    announcement_elements = driver.find_elements(By.CSS_SELECTOR, '[data-stream-item-id]')
    print(f"   📝 Found {len(announcement_elements)} announcement elements")

    if len(announcement_elements) == 0:
        print("\n   ⚠️  No announcements found!")
        print("   Possible reasons:")
        print("   - The classroom has no announcements yet")
        print("   - Google changed their HTML structure")
        print("   - You're not on the 'Stream' tab")
        print("\n   Saving screenshot for debugging...")
        driver.save_screenshot('classroom_debug.png')
        print("   📸 Screenshot saved: classroom_debug.png")
    else:
        print("\n   ✅ Found announcements! Parsing them...")
        announcements = []

        for i, elem in enumerate(announcement_elements):  # Process all announcements
            try:
                full_text = elem.text.strip()
                if full_text and len(full_text) >= 20:
                    # Just show preview
                    preview = full_text[:100].replace('\n', ' ')
                    print(f"   [{i+1}] {preview}...")
                    announcements.append({'text': full_text})
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
            with open('announcements_cache.json', 'w') as f:
                json.dump(cache, f, indent=2)
            print("   💾 Saved to announcements_cache.json")
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
