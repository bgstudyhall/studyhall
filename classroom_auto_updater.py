#!/usr/bin/env python3
"""
Automatic Google Classroom Updater
Runs continuously in the background, checking for new announcements every 5 minutes
Auto-commits and deploys when changes are detected
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
import hashlib

# Configuration
CHECK_INTERVAL = 300  # 5 minutes in seconds
CACHE_FILE = 'announcements_cache.json'
LOCK_FILE = '.classroom_updater.lock'

def log(message):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()

def get_file_hash(filepath):
    """Get MD5 hash of file contents"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def run_scraper():
    """Run the classroom scraper"""
    log("🔄 Running scraper...")
    try:
        # Run the test scraper
        result = subprocess.run(
            ['python3', 'test_classroom_scraper.py'],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            log("✅ Scraper completed successfully")
            return True
        else:
            log(f"⚠️  Scraper failed with code {result.returncode}")
            if result.stderr:
                log(f"   Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        log("⏱️  Scraper timed out after 60 seconds")
        return False
    except Exception as e:
        log(f"❌ Scraper error: {e}")
        return False

def commit_and_deploy():
    """Commit changes and deploy to Fly.io"""
    try:
        log("📝 Committing changes...")

        # Add the cache file
        subprocess.run(['git', 'add', CACHE_FILE], check=True)

        # Check if there are changes to commit
        result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            capture_output=True
        )

        if result.returncode == 0:
            log("   No changes to commit")
            return True

        # Commit with timestamp
        commit_msg = f"Auto-update classroom announcements - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            check=True,
            capture_output=True
        )
        log("✅ Changes committed")

        # Push to GitHub
        log("📤 Pushing to GitHub...")
        subprocess.run(['git', 'push', 'origin', 'master'], check=True, capture_output=True)
        log("✅ Pushed to GitHub")

        # Deploy to Fly.io
        log("🚀 Deploying to Fly.io...")
        result = subprocess.run(
            ['fly', 'deploy'],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            log("✅ Deployed successfully!")
            return True
        else:
            log(f"⚠️  Deploy failed: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        log("⏱️  Deploy timed out")
        return False
    except Exception as e:
        log(f"❌ Commit/deploy error: {e}")
        return False

def check_for_updates():
    """Main update cycle"""
    # Get hash before scraping
    hash_before = get_file_hash(CACHE_FILE)

    # Run scraper
    if not run_scraper():
        return False

    # Get hash after scraping
    hash_after = get_file_hash(CACHE_FILE)

    # Check if file changed
    if hash_before == hash_after:
        log("📭 No new announcements")
        return True

    log("📬 New announcements detected!")

    # Show what changed
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cache = json.load(f)
                count = len(cache.get('announcements', []))
                log(f"   Total announcements: {count}")
        except:
            pass

    # Commit and deploy
    return commit_and_deploy()

def create_lock():
    """Create lock file to prevent multiple instances"""
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, 'r') as f:
            pid = f.read().strip()
        log(f"⚠️  Lock file exists (PID: {pid})")
        log("   Another instance may be running")
        log("   If not, delete .classroom_updater.lock and try again")
        return False

    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True

def remove_lock():
    """Remove lock file"""
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def main():
    """Main daemon loop"""
    log("="*70)
    log("  GOOGLE CLASSROOM AUTO-UPDATER")
    log("="*70)
    log(f"Check interval: {CHECK_INTERVAL} seconds ({CHECK_INTERVAL//60} minutes)")
    log(f"Cache file: {CACHE_FILE}")
    log("")

    # Create lock file
    if not create_lock():
        sys.exit(1)

    try:
        log("🚀 Starting auto-updater daemon...")
        log("   Press Ctrl+C to stop")
        log("")

        iteration = 0
        while True:
            iteration += 1
            log(f"--- Check #{iteration} ---")

            try:
                check_for_updates()
            except Exception as e:
                log(f"❌ Error in update cycle: {e}")

            log(f"😴 Sleeping for {CHECK_INTERVAL//60} minutes...")
            log("")
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        log("")
        log("⏹️  Stopping auto-updater...")
    finally:
        remove_lock()
        log("👋 Auto-updater stopped")
        log("="*70)

if __name__ == '__main__':
    # Change to script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Run main loop
    main()
