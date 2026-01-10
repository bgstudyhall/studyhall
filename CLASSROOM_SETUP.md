# Google Classroom Integration Setup Guide

## Overview

The Google Classroom integration allows your StudyHall app to automatically scrape and display announcements from a Google Classroom without requiring users to log in.

## Prerequisites

1. **Selenium** - Install locally (not needed in production):
   ```bash
   pip install selenium
   ```

2. **Google Chrome** - Must be installed on your computer

3. **ChromeDriver** - Usually installed automatically with selenium, but if not:
   ```bash
   # macOS
   brew install chromedriver

   # Or download from: https://chromedriver.chromium.org/
   ```

## Quick Setup (Recommended)

### Option 1: Automated Setup Script

Run the interactive setup script:

```bash
python3 setup_classroom.py
```

This will:
1. Open a Chrome browser
2. Let you log in to Google Classroom
3. Automatically capture your login cookies
4. Extract the classroom ID from the URL
5. Save everything to the correct files

**That's it!** Restart your Flask app and visit `/classroom`

---

## Manual Setup (Advanced)

If you prefer to set things up manually:

### Step 1: Find Your Classroom ID

1. Go to https://classroom.google.com
2. Click on the classroom you want to display
3. Look at the URL in your browser:
   ```
   https://classroom.google.com/u/0/c/NjEyMzQ1Njc4OTAx
                                        ^^^^^^^^^^^^^^^^
                                        This is your classroom ID
   ```
4. Copy the classroom ID (the long string after `/c/`)

### Step 2: Create Configuration File

Create a file named `classroom_config.json` in your project root:

```json
{
  "classroom_id": "YOUR_CLASSROOM_ID_HERE"
}
```

Replace `YOUR_CLASSROOM_ID_HERE` with the ID you copied.

### Step 3: Generate Cookies File

This is the tricky part - you need to export your Google login cookies:

**Method 1: Using Browser Extension**
1. Install a cookie export extension (e.g., "EditThisCookie" for Chrome)
2. Go to classroom.google.com
3. Export cookies as JSON
4. Convert to Python pickle format (requires custom script)

**Method 2: Using Selenium (Easier)**
Just run the automated setup script:
```bash
python3 setup_classroom.py
```

### Step 4: Verify Setup

Check that these files exist:
- ✅ `classroom_config.json` - Contains your classroom ID
- ✅ `google_cookies.pkl` - Contains your login session

### Step 5: Restart Your App

```bash
python3 flask_app.py
```

You should see:
```
============================================================
Google Classroom Integration
============================================================
✅ Classroom ID loaded: YOUR_ID
🔄 Performing initial classroom scrape...
✅ Background classroom scraper started (updates every 10 minutes)
============================================================
```

---

## Testing

1. Visit `http://localhost:8080/classroom` in your browser
2. You should see announcements from your Google Classroom
3. Click the "Refresh" button to manually trigger a new scrape

---

## How It Works

1. **Background Scraper**: Every 10 minutes, the app uses Selenium to:
   - Log in to Google Classroom using your saved cookies
   - Navigate to your classroom page
   - Scrape all announcements from the stream
   - Save them to `announcements_cache.json`

2. **Fast Display**: When users visit `/classroom`:
   - They see cached announcements instantly (no login required)
   - Data is read from `announcements_cache.json`
   - Page auto-refreshes every 5 minutes

3. **Manual Refresh**: Users can click the refresh button to trigger an immediate scrape

---

## Production Deployment

**Important**: The Google Classroom feature is **disabled in production** (Fly.io) because:
- Selenium requires Chrome/ChromeDriver (not available in production containers)
- Web scraping is resource-intensive
- Google may detect and block automated access

### Recommended Approach for Production

**Option 1: Localhost Only**
- Run the scraper on your local computer
- Use the `/classroom` page locally only
- Don't expose it to production users

**Option 2: Separate Scraper Service**
- Set up a separate server/computer that runs the scraper
- Use the Google Classroom API instead (more reliable)
- Push data to your production database via API

**Option 3: Use Google Classroom API** (Best for Production)
Instead of web scraping, use the official API:
1. Enable Google Classroom API in Google Cloud Console
2. Set up OAuth2 credentials
3. Replace Selenium scraper with API calls
4. Much more reliable and Google-approved

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'selenium'"
Install selenium:
```bash
pip install selenium
```

### "selenium.common.exceptions.WebDriverException"
Install ChromeDriver:
```bash
brew install chromedriver  # macOS
```

### "No announcements yet"
1. Check that `classroom_config.json` exists with correct classroom ID
2. Check that `google_cookies.pkl` exists
3. Check the console logs for scraping errors
4. Try running the setup script again (cookies may have expired)

### Cookies Expired
Google sessions typically last ~30 days. When they expire:
1. Run `python3 setup_classroom.py` again
2. This will refresh your cookies

### Wrong Classroom
If you're seeing the wrong classroom's announcements:
1. Delete `classroom_config.json`
2. Delete `google_cookies.pkl`
3. Run `python3 setup_classroom.py` again
4. Make sure to navigate to the CORRECT classroom before pressing Enter

---

## Files Created

- `classroom_config.json` - Classroom ID configuration
- `google_cookies.pkl` - Your Google login session (keep private!)
- `announcements_cache.json` - Cached announcements (auto-generated)
- `static/classroom.css` - Styling for classroom page
- `templates/classroom.html` - Classroom announcements page

---

## Security Notes

⚠️ **Important Security Considerations:**

1. **Keep `google_cookies.pkl` private**
   - Contains your Google login session
   - Add to `.gitignore` (already added)
   - Never commit to git
   - Never share publicly

2. **Cookies expire**
   - Google sessions typically last ~30 days
   - You'll need to re-run setup when they expire

3. **Read-only access**
   - The scraper can only READ announcements
   - Cannot post, delete, or modify anything
   - Only accesses the one classroom you configure

4. **Terms of Service**
   - Web scraping may violate Google's ToS
   - Use responsibly and only for your own classrooms
   - Consider using the official API for production

---

## Uninstalling

To remove the Google Classroom feature:

1. Delete the files:
   ```bash
   rm classroom_config.json
   rm google_cookies.pkl
   rm announcements_cache.json
   rm setup_classroom.py
   ```

2. The app will automatically disable the feature if these files don't exist

---

## Support

If you run into issues:
1. Check the console logs when running `flask_app.py`
2. Make sure Chrome and ChromeDriver are installed
3. Try running the setup script again
4. Check that your Google account has access to the classroom

---

## Credits

Built with:
- **Selenium** - Browser automation
- **Flask** - Web framework
- **Google Classroom** - Educational platform
