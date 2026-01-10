#!/usr/bin/env python3
"""
Quick diagnostic to check Google Classroom setup status
"""

import os
import json

print("="*70)
print("  GOOGLE CLASSROOM SETUP STATUS")
print("="*70)

# Check config file
print("\n1. Configuration File:")
if os.path.exists('classroom_config.json'):
    with open('classroom_config.json', 'r') as f:
        config = json.load(f)
        print(f"   ✅ classroom_config.json exists")
        print(f"   Classroom ID: {config.get('classroom_id')}")
else:
    print("   ❌ classroom_config.json NOT found")

# Check cookies file
print("\n2. Cookies File:")
if os.path.exists('google_cookies.pkl'):
    size = os.path.getsize('google_cookies.pkl')
    print(f"   ✅ google_cookies.pkl exists ({size} bytes)")
else:
    print("   ❌ google_cookies.pkl NOT found")

# Check announcements cache
print("\n3. Announcements Cache:")
if os.path.exists('announcements_cache.json'):
    with open('announcements_cache.json', 'r') as f:
        cache = json.load(f)
        count = len(cache.get('announcements', []))
        last_updated = cache.get('last_updated', 'Never')
        print(f"   ✅ announcements_cache.json exists")
        print(f"   Announcements: {count}")
        print(f"   Last Updated: {last_updated}")

        # Show preview of announcements
        if count > 0:
            print("\n   Preview of announcements:")
            for i, ann in enumerate(cache.get('announcements', [])[:3]):
                text = ann.get('text', '')
                preview = text[:80].replace('\n', ' ')
                print(f"   [{i+1}] {preview}...")
else:
    print("   ❌ announcements_cache.json NOT found")
    print("   Run: python3 test_classroom_scraper.py")

# Check Selenium
print("\n4. Selenium Status:")
try:
    import selenium
    print(f"   ✅ Selenium installed")
except ImportError:
    print(f"   ❌ Selenium NOT installed")
    print("   Install with: pip install selenium")

print("\n" + "="*70)
print("  WHAT TO DO NEXT")
print("="*70)

if os.path.exists('announcements_cache.json'):
    print("\n✅ Announcements are ready!")
    print("\nTo see them:")
    print("  1. Start your Flask app: python3 flask_app.py")
    print("  2. Visit: http://localhost:8080/classroom")
    print("\nThe announcements should appear immediately!")
else:
    print("\n⚠️  No announcements cached yet")
    print("\nTo set up:")
    print("  1. Run: python3 test_classroom_scraper.py")
    print("  2. Then start app: python3 flask_app.py")
    print("  3. Visit: http://localhost:8080/classroom")

print("\n" + "="*70 + "\n")
