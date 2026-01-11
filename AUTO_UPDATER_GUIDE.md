# Google Classroom Auto-Updater Guide

## What It Does

The auto-updater runs in the background on your MacBook and automatically:
- ✅ Checks Google Classroom every 5 minutes for new announcements
- ✅ Scrapes and cleans announcement text + links
- ✅ Commits changes to git when new announcements are found
- ✅ Pushes to GitHub automatically
- ✅ Deploys to Fly.io automatically
- ✅ Runs even when you're at school (as long as your MacBook is on)
- ✅ Restarts automatically if it crashes
- ✅ Starts automatically when you log in

## Installation

### One-Time Setup

1. **Make sure prerequisites are installed:**
   ```bash
   # Check Python
   python3 --version

   # Check Selenium
   python3 -c "import selenium; print('Selenium OK')"

   # Check Git
   git --version

   # Check Fly CLI
   fly version
   ```

2. **Run the installer:**
   ```bash
   cd /Users/elias/Desktop/studyhall
   ./install_auto_updater.sh
   ```

3. **Done!** The auto-updater is now running in the background.

---

## Usage

### View Live Logs

See what the auto-updater is doing in real-time:

```bash
tail -f ~/Library/Logs/studyhall/classroom_updater.log
```

You'll see output like:
```
[2026-01-10 14:30:00] --- Check #1 ---
[2026-01-10 14:30:00] 🔄 Running scraper...
[2026-01-10 14:30:15] ✅ Scraper completed successfully
[2026-01-10 14:30:15] 📬 New announcements detected!
[2026-01-10 14:30:15]    Total announcements: 5
[2026-01-10 14:30:15] 📝 Committing changes...
[2026-01-10 14:30:16] ✅ Changes committed
[2026-01-10 14:30:16] 📤 Pushing to GitHub...
[2026-01-10 14:30:18] ✅ Pushed to GitHub
[2026-01-10 14:30:18] 🚀 Deploying to Fly.io...
[2026-01-10 14:32:45] ✅ Deployed successfully!
[2026-01-10 14:32:45] 😴 Sleeping for 5 minutes...
```

### Check Status

```bash
# Check if it's running
launchctl list | grep studyhall

# You should see:
# -    0    com.studyhall.classroom
```

### Stop Auto-Updater

```bash
launchctl unload ~/Library/LaunchAgents/com.studyhall.classroom.plist
```

### Start Auto-Updater

```bash
launchctl load ~/Library/LaunchAgents/com.studyhall.classroom.plist
```

### Restart Auto-Updater

```bash
launchctl unload ~/Library/LaunchAgents/com.studyhall.classroom.plist
launchctl load ~/Library/LaunchAgents/com.studyhall.classroom.plist
```

---

## How It Works

### The Update Cycle (Every 5 Minutes)

1. **Scrape**: Opens Chrome headlessly, logs into Google Classroom, scrapes announcements
2. **Compare**: Checks if announcements changed since last check
3. **Commit**: If changed, commits to git with timestamp
4. **Push**: Pushes to GitHub
5. **Deploy**: Runs `fly deploy` to update production
6. **Sleep**: Waits 5 minutes, then repeats

### Smart Features

- **Only deploys when there are changes** - Doesn't waste resources
- **Crash recovery** - Automatically restarts if it fails
- **Persistent** - Keeps running even if you close Terminal
- **Boot startup** - Starts when you log into your Mac
- **Detailed logging** - See exactly what's happening

---

## Troubleshooting

### "It's not running"

Check if it's loaded:
```bash
launchctl list | grep studyhall
```

If nothing shows up, load it:
```bash
launchctl load ~/Library/LaunchAgents/com.studyhall.classroom.plist
```

### "No new announcements even though there should be"

1. Check the logs:
   ```bash
   tail -50 ~/Library/Logs/studyhall/classroom_updater.log
   ```

2. Look for errors:
   ```bash
   tail -50 ~/Library/Logs/studyhall/classroom_updater_error.log
   ```

3. Check if cookies expired:
   ```bash
   python3 test_classroom_scraper.py
   ```

   If you see "NOT LOGGED IN", run:
   ```bash
   python3 setup_classroom.py
   ```

### "Deploy is failing"

Check if you're logged into Fly:
```bash
fly auth login
```

### "MacBook needs to sleep"

The auto-updater will stop when your Mac sleeps. To keep it running:

**Option 1: Prevent sleep while plugged in**
- System Settings → Energy Saver → Prevent automatic sleeping when display is off

**Option 2: Use `caffeinate`** (keeps Mac awake)
```bash
caffeinate -s &
```

**Option 3: Run on a server** (better for 24/7)
- Move the scraper to a cloud VM
- Or use GitHub Actions (see CLASSROOM_WORKFLOW.md)

---

## Configuration

### Change Check Interval

Edit `classroom_auto_updater.py` line 12:

```python
CHECK_INTERVAL = 300  # 5 minutes in seconds
```

Change to:
- `180` = 3 minutes
- `600` = 10 minutes
- `60` = 1 minute (not recommended - might get rate limited)

Then restart:
```bash
launchctl unload ~/Library/LaunchAgents/com.studyhall.classroom.plist
launchctl load ~/Library/LaunchAgents/com.studyhall.classroom.plist
```

---

## Uninstallation

```bash
# Stop the service
launchctl unload ~/Library/LaunchAgents/com.studyhall.classroom.plist

# Remove the plist
rm ~/Library/LaunchAgents/com.studyhall.classroom.plist

# Remove logs (optional)
rm -rf ~/Library/Logs/studyhall
```

---

## At School Workflow

### Before You Leave Home:

1. Make sure MacBook is plugged in
2. Prevent sleep: System Settings → Energy Saver → Never sleep when plugged in
3. Check auto-updater is running:
   ```bash
   launchctl list | grep studyhall
   ```

### While at School:

- Your MacBook automatically checks for new announcements every 5 minutes
- New announcements are automatically deployed to production
- Students see updates within 5-10 minutes
- You don't need to do anything!

### Check Status Remotely:

View the logs from your iPhone/iPad using SSH:
```bash
ssh elias@YOUR_MACBOOK_IP
tail -f ~/Library/Logs/studyhall/classroom_updater.log
```

---

## Files Created

- `~/Library/LaunchAgents/com.studyhall.classroom.plist` - Auto-start configuration
- `~/Library/Logs/studyhall/classroom_updater.log` - Main log file
- `~/Library/Logs/studyhall/classroom_updater_error.log` - Error log
- `.classroom_updater.lock` - Lock file (prevents multiple instances)

---

## Security

- **Cookies are private** - Never committed to git (in .gitignore)
- **Config is private** - Never committed to git (in .gitignore)
- **Only announcements are public** - The cache file is safe to commit
- **Runs locally** - No cloud service has access to your Google account

---

## Tips

1. **Test it first** - Run manually to see it work:
   ```bash
   python3 classroom_auto_updater.py
   ```
   Press Ctrl+C to stop

2. **Monitor initially** - Watch logs for first few cycles to make sure it works

3. **Keep MacBook on** - The updater only runs when your Mac is awake and on

4. **Battery life** - Running constantly uses battery. Best to keep plugged in.

---

## Support

If you have issues:

1. Check logs: `tail -50 ~/Library/Logs/studyhall/classroom_updater.log`
2. Check errors: `tail -50 ~/Library/Logs/studyhall/classroom_updater_error.log`
3. Test manually: `python3 test_classroom_scraper.py`
4. Restart service: `launchctl unload ... && launchctl load ...`
