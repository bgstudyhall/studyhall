#!/usr/bin/env python3
"""
Google Classroom Setup Helper
This script helps you configure Google Classroom integration by:
1. Opening a browser for you to log in
2. Capturing your login cookies
3. Extracting the classroom ID from the URL
4. Saving everything to configuration files
"""

import os
import json
import pickle
import time

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except ImportError:
    print("❌ Error: selenium not installed")
    print("Install it with: pip install selenium")
    exit(1)

COOKIES_FILE = 'google_cookies.pkl'
CONFIG_FILE = 'classroom_config.json'

def setup_classroom():
    """Interactive setup to configure the classroom."""
    print("\n" + "="*70)
    print("  GOOGLE CLASSROOM SETUP")
    print("="*70)
    print("\nThis will open a Chrome browser where you can:")
    print("  1. Sign in to your Google account")
    print("  2. Navigate to Google Classroom")
    print("  3. Open the specific classroom you want to display")
    print("\nThe script will automatically capture your login and classroom ID.")
    print("="*70 + "\n")

    input("Press Enter to open the browser...")

    # Set up Chrome browser (non-headless so you can see it)
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    print("\n🌐 Opening Chrome browser...")
    driver = webdriver.Chrome(options=options)
    driver.get('https://classroom.google.com')

    print("\n" + "="*70)
    print("  INSTRUCTIONS:")
    print("="*70)
    print("1. Sign in with your Google account in the browser window")
    print("2. Navigate to Google Classroom")
    print("3. Click on the classroom you want to display announcements from")
    print("4. Make sure you're on the 'Stream' tab (where announcements appear)")
    print("5. Come back here and press Enter when ready")
    print("="*70 + "\n")

    input("Press Enter when you're on the correct classroom page...")

    # Get current URL to extract classroom ID
    current_url = driver.current_url
    print(f"\n📍 Current URL: {current_url}")

    classroom_id = None
    if '/c/' in current_url:
        # Extract classroom ID from URL
        classroom_id = current_url.split('/c/')[1].split('/')[0]
        print(f"✅ Classroom ID detected: {classroom_id}")
    else:
        print("\n⚠️  Could not automatically detect classroom ID from URL")
        print("The URL should look like: https://classroom.google.com/u/0/c/CLASSROOM_ID")
        classroom_id = input("\nPlease enter the classroom ID manually: ").strip()

    if not classroom_id:
        print("❌ No classroom ID provided. Setup cancelled.")
        driver.quit()
        return

    # Save cookies
    print("\n💾 Saving login cookies...")
    cookies = driver.get_cookies()
    with open(COOKIES_FILE, 'wb') as f:
        pickle.dump(cookies, f)
    print(f"✅ Cookies saved to: {COOKIES_FILE}")

    # Save classroom ID
    print("💾 Saving classroom configuration...")
    config = {'classroom_id': classroom_id}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"✅ Configuration saved to: {CONFIG_FILE}")

    # Close browser
    driver.quit()

    print("\n" + "="*70)
    print("  ✅ SETUP COMPLETE!")
    print("="*70)
    print(f"\nClassroom ID: {classroom_id}")
    print(f"Cookies saved: {COOKIES_FILE}")
    print(f"Config saved: {CONFIG_FILE}")
    print("\nYou can now:")
    print("  1. Restart your Flask app")
    print("  2. Visit /classroom in your browser")
    print("  3. See announcements automatically scraped every 10 minutes")
    print("\nNote: Cookies typically expire after ~30 days, then you'll need to re-run this setup.")
    print("="*70 + "\n")

if __name__ == '__main__':
    try:
        setup_classroom()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user.")
    except Exception as e:
        print(f"\n\n❌ Error during setup: {e}")
        print("\nPlease make sure Chrome is installed and try again.")
