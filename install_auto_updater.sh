#!/bin/bash

# Installation script for Google Classroom Auto-Updater
# This sets up the auto-updater to run automatically on macOS

echo "======================================================================"
echo "  INSTALLING GOOGLE CLASSROOM AUTO-UPDATER"
echo "======================================================================"
echo ""

# Get the absolute path to the studyhall directory
STUDYHALL_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_FILE="$HOME/Library/LaunchAgents/com.studyhall.classroom.plist"
LOG_DIR="$HOME/Library/Logs/studyhall"

echo "📁 StudyHall directory: $STUDYHALL_DIR"
echo "📄 LaunchAgent plist: $PLIST_FILE"
echo "📋 Logs directory: $LOG_DIR"
echo ""

# Create logs directory
mkdir -p "$LOG_DIR"

# Create the LaunchAgent plist
echo "📝 Creating LaunchAgent configuration..."
cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.studyhall.classroom</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>$STUDYHALL_DIR/classroom_auto_updater.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$STUDYHALL_DIR</string>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/classroom_updater.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/classroom_updater_error.log</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>300</integer>
</dict>
</plist>
EOF

echo "✅ LaunchAgent plist created"
echo ""

# Make the Python script executable
chmod +x "$STUDYHALL_DIR/classroom_auto_updater.py"
echo "✅ Made updater script executable"
echo ""

# Load the LaunchAgent
echo "🚀 Loading LaunchAgent..."
launchctl unload "$PLIST_FILE" 2>/dev/null  # Unload if already loaded
launchctl load "$PLIST_FILE"

if [ $? -eq 0 ]; then
    echo "✅ LaunchAgent loaded successfully!"
else
    echo "⚠️  Warning: LaunchAgent load returned an error"
    echo "   This is often normal on first run"
fi

echo ""
echo "======================================================================"
echo "  ✅ INSTALLATION COMPLETE!"
echo "======================================================================"
echo ""
echo "The auto-updater is now running and will:"
echo "  • Check for new announcements every 5 minutes"
echo "  • Automatically commit and push changes"
echo "  • Automatically deploy to Fly.io"
echo "  • Restart automatically if it crashes"
echo "  • Start automatically when you log in"
echo ""
echo "📋 View logs:"
echo "   tail -f $LOG_DIR/classroom_updater.log"
echo ""
echo "🛑 To stop the auto-updater:"
echo "   launchctl unload $PLIST_FILE"
echo ""
echo "🔄 To restart the auto-updater:"
echo "   launchctl unload $PLIST_FILE && launchctl load $PLIST_FILE"
echo ""
echo "❌ To uninstall:"
echo "   launchctl unload $PLIST_FILE"
echo "   rm $PLIST_FILE"
echo ""
echo "======================================================================"
