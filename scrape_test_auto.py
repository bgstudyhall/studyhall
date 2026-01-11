#!/usr/bin/env python3
"""Auto scraper for Test classroom - no manual confirmation needed"""

import os
import sys
import json
from datetime import datetime
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import pickle

classroom_id = 'ODM4ODA4ODcyMTIw'

def get_driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    return driver

print("🔄 Scraping Test classroom...")
driver = get_driver()

try:
    # Load cookies
    driver.get('https://classroom.google.com')
    with open('google_cookies.pkl', 'rb') as f:
        cookies = pickle.load(f)
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except:
                pass
    driver.refresh()
    time.sleep(2)

    # Navigate to classroom
    driver.get(f'https://classroom.google.com/u/0/c/{classroom_id}')
    time.sleep(3)

    # Scroll to load all
    for i in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)

    # Get announcements
    announcement_elements = driver.find_elements(By.CSS_SELECTOR, '[data-stream-item-id]')
    print(f"✅ Found {len(announcement_elements)} announcement elements")

    announcements = []
    for elem in announcement_elements:
        try:
            full_text = elem.text.strip()
            if not full_text or len(full_text) < 20:
                continue

            announcement_id = elem.get_attribute('data-stream-item-id')
            announcement_url = f'https://classroom.google.com/c/{classroom_id}/p/{announcement_id}/details'

            # Get content
            try:
                content_elem = elem.find_element(By.CSS_SELECTOR, '.pco8Kc')
                announcement_text = content_elem.text.strip()
            except:
                announcement_text = full_text

            # Clean text
            for removal in ['Add comment', 'more_vert', 'Created', 'Edited']:
                announcement_text = announcement_text.replace(removal, '')

            lines = announcement_text.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line and len(line) > 3:
                    if len(line) > 15 or not any(month in line for month in ['Jan', 'Feb', 'Mar']):
                        cleaned_lines.append(line)

            announcement_text = '\n\n'.join(cleaned_lines).strip()

            if announcement_text and len(announcement_text) > 4:
                announcements.append({
                    'id': str(len(announcements)),
                    'text': announcement_text,
                    'clean_text': announcement_text,
                    'date': 'Recently',
                    'materials': [],
                    'classroom_url': announcement_url,
                    'links': []
                })
                print(f"   [{len(announcements)}] {announcement_text[:50]}...")
        except Exception as e:
            continue

    # Save
    cache = {
        'announcements': announcements,
        'last_updated': datetime.now().isoformat(),
        'classroom_name': 'Test'
    }
    with open('test_announcements_cache.json', 'w') as f:
        json.dump(cache, f, indent=2)

    print(f"\n✅ Saved {len(announcements)} announcements to cache")
    driver.quit()

except Exception as e:
    print(f"❌ Error: {e}")
    driver.quit()
    sys.exit(1)
