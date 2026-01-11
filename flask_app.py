from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, send_from_directory, make_response, Response
from functools import wraps
import io
import json
import os
from datetime import datetime, timedelta
import pytz
import random
import time
import threading
import requests
import re
from flask import g
import instaloader
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
from email.mime.text import MIMEText
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask_compress import Compress
from flask_socketio import SocketIO, emit, join_room, leave_room
import sys

# Optional Google Classroom dependencies (only needed if using classroom feature)
try:
    import pickle
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("⚠️  Selenium not available - Google Classroom feature will be disabled")

# Force stdout/stderr to flush immediately for logging
sys.stdout = io.TextIOWrapper(open(sys.stdout.fileno(), 'wb', 0), write_through=True)
sys.stderr = io.TextIOWrapper(open(sys.stderr.fileno(), 'wb', 0), write_through=True)

# ===============================================================
# Flask App Configuration
# ===============================================================
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

# Enable Gzip/Brotli compression with optimized settings
app.config['COMPRESS_ALGORITHM'] = ['br', 'gzip', 'deflate']  # Brotli first, then gzip
app.config['COMPRESS_BR_LEVEL'] = 4  # Balanced compression (1-11, 4 is good for speed)
app.config['COMPRESS_LEVEL'] = 6  # Gzip level (1-9, 6 is balanced)
app.config['COMPRESS_MIN_SIZE'] = 500  # Only compress files larger than 500 bytes
app.config['COMPRESS_MIMETYPES'] = [
    'text/html', 'text/css', 'text/javascript', 'application/javascript',
    'application/json', 'text/xml', 'application/xml', 'image/svg+xml'
]
Compress(app)

# Enable WebSockets (now compatible with Fly.io!)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Add caching headers for static files and CDN optimization
@app.after_request
def add_cache_headers(response):
    # Cache static files for a long time (1 year for immutable resources)
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        response.headers['Vary'] = 'Accept-Encoding'
    # Cache game content for 1 hour (can be updated)
    elif request.path.startswith('/play/'):
        response.headers['Cache-Control'] = 'public, max-age=3600'
        response.headers['Vary'] = 'Accept-Encoding'
    # Don't cache dynamic API responses
    elif request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

# Rank system hierarchy
RANKS = [
    {'id': 'bronze', 'name': 'Bronze', 'price': 20, 'color': '#CD7F32'},
    {'id': 'silver', 'name': 'Silver', 'price': 80, 'color': '#C0C0C0'},
    {'id': 'vip', 'name': 'VIP', 'price': 150, 'color': '#FFD700'},
    {'id': 'platinum', 'name': 'Platinum', 'price': 300, 'color': '#E5E4E2'},
    {'id': 'elite', 'name': 'Elite', 'price': 500, 'color': '#9966CC'},
    {'id': 'grandmaster', 'name': 'Grandmaster', 'price': 2000, 'color': '#FF4500'},
    {'id': 'minister', 'name': 'Minister', 'price': 10000, 'color': '#FF0000'}
]

STAFF_ROLES = {
    'admin': {
        'name': 'Administrator',
        'color': '#ff0000',
        'icon': '',
        'level': 100,
        'weekly_pay': 0  # Admin doesn't get paid
    },
    'president': {
        'name': 'President',
        'color': '#9b59b6',
        'icon': '️',
        'level': 90,
        'weekly_pay': 100
    },
    'economy_director': {
        'name': 'Economy Director',
        'color': '#f1c40f',
        'icon': '',
        'level': 80,
        'weekly_pay': 50
    },
    'pr_director': {
        'name': 'Director of Public Relations',
        'color': '#3498db',
        'icon': '',
        'level': 80,
        'weekly_pay': 50
    },
    'master_moderator': {
        'name': 'Master Moderator',
        'color': '#e74c3c',
        'icon': '🛡️',
        'level': 80,
        'weekly_pay': 50
    },
    'ambassador': {
        'name': 'Ambassador',
        'color': '#2ecc71',
        'icon': '',
        'level': 50,
        'weekly_pay': 0  # Base ambassadors don't get paid
    },
    'user': {
        'name': 'User',
        'color': '#95a5a6',
        'icon': '',
        'level': 0,
        'weekly_pay': 0
    }
}

# Group Rank System
GROUP_RANKS = {
    0: {'name': 'No Rank', 'cost': 0, 'interest': 0, 'member_cap': 4, 'display': ''},
    1: {'name': 'Rank I', 'cost': 50, 'interest': 5, 'member_cap': 5, 'display': 'I'},
    2: {'name': 'Rank II', 'cost': 500, 'interest': 10, 'member_cap': 6, 'display': 'II'},
    3: {'name': 'Rank III', 'cost': 1000, 'interest': 15, 'member_cap': 7, 'display': 'III'},
    4: {'name': 'Rank IV', 'cost': 2500, 'interest': 20, 'member_cap': 8, 'display': 'IV'},
    5: {'name': 'Rank V', 'cost': 8000, 'interest': 25, 'member_cap': 9, 'display': 'V'}
}

# Birthday data - easily editable
# Format: month: {day: [(name, on_studyhall), ...]}
BIRTHDAYS = {
    12: {  # December
        8: [('Abigail Gregory', False)],
        9: [('Lucia Hall', False), ('Micah Casey', True)],
        10: [('Ethan Germond', True), ('Bryce Palmer', False), ('Akai Sherman', False)],
        11: [],
        12: [('Madison Stanton', False)],
        13: [('Harpo Hardt', True), ('Izayah Freeman', False), ('Daisy Crisell', False)],
        15: [('Peter Blance', False)],
        16: [('Kaylee Dharry', False), ('Kelly Hubbard', False), ('Caydee Monroe', False)],
        17: [('Elijah Aponte', True), ('Matthew Wombacker', True)],
        18: [('Liam Pohli', False), ('Tabitha Doyle', False)],
        19: [('Madison Smith', False), ('Lelaenia Baldwin', False), ('Beckett Longwell', True)],
        20: [('Adrian Ramirez', True), ('Brayden Wehrli', True), ('Ethan Morris', True)],

        # Added entries
        21: [('Colin Dailey', False), ('Anthony Brasiel', True)],
        22: [('Victoria Cannistra', False), ('Weston Thomas', False)],
        23: [('Carleigh Henchy', False)],
        24: [('Emely Lopez', False), ('Robert Tumilowicz', False)],
        25: [],
        26: [],
        27: [('Janaya Walker', False)],
        28: [('Olivia Bolster', False), ('Parker Buttice', False), ('Colden McFee', False)],
        29: [('Declan Noxon', False)],
        30: [],
        31: []
    }
}

# ===============================================================
# Google Classroom Configuration
# ===============================================================
CLASSROOM_COOKIES_FILE = 'google_cookies.pkl'
CLASSROOM_ANNOUNCEMENTS_FILE = 'announcements_cache.json'
CLASSROOM_CONFIG_FILE = 'classroom_config.json'
CLASSROOM_ID = None  # Will be set after first login

# Global cache for Google Classroom announcements
classroom_announcements_cache = {
    'announcements': [],
    'last_updated': None,
    'classroom_name': 'Loading...'
}

# Permission definitions
PERMISSIONS = {
    'create_users': ['admin', 'president', 'ambassador', 'master_moderator', 'pr_director'],
    'ban_users': ['admin', 'president', 'master_moderator'],
    'change_passwords': ['admin', 'president', 'master_moderator'],
    'edit_tokens': ['admin'],
    'view_token_stats': ['admin', 'president', 'economy_director'],
    'manage_lottery': ['admin', 'president', 'economy_director'],
    'create_promo_codes': ['admin', 'president', 'economy_director'],
    'view_casino_stats': ['admin', 'president', 'economy_director'],
    'manage_announcements': ['admin', 'president', 'pr_director'],
    'manage_feedback': ['admin', 'president', 'pr_director'],
    'delete_lounge_messages': ['admin', 'president', 'master_moderator'],
    'view_reported_messages': ['admin', 'president', 'master_moderator'],
    'manage_games': ['admin'],
    'maintenance_mode': ['admin', 'president'],
    'view_action_logs': ['admin', 'president'],
    'assign_roles': ['admin', 'president'],
    'approve_paychecks': ['admin', 'president'],
    'view_paycheck_status': ['admin', 'president', 'economy_director', 'pr_director', 'master_moderator'],
    'manage_groups': ['admin', 'president'],
}

# ===============================================================
# Jinja2 Filters
# ===============================================================
@app.template_filter('format_time')
def format_time_filter(timestamp):
    """Format timestamp to 12-hour format with AM/PM"""
    try:
        if 'AM' in timestamp or 'PM' in timestamp:
            parts = timestamp.split(' ')
            if len(parts) >= 2:
                time_part = parts[1]
                time_components = time_part.split(':')
                if len(time_components) == 3:
                    time_part = f"{time_components[0]}:{time_components[1]}"
                return f"{time_part} {parts[2]}"
        if len(timestamp) > 16:
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M')
        else:
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M')
        return dt.strftime('%I:%M %p')
    except Exception:
        return timestamp

# ===============================================================
# File paths for JSON storage
# ===============================================================
# Use environment variable if set (for fly.io persistent volume), otherwise use local ./data
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
GAMES_FILE = os.path.join(DATA_DIR, 'games.json')
ANNOUNCEMENTS_FILE = os.path.join(DATA_DIR, 'announcements.json')
FEEDBACK_FILE = os.path.join(DATA_DIR, 'feedback.json')
WEBSITE_REQUESTS_FILE = os.path.join(DATA_DIR, 'website_requests.json')
MESSAGES_FILE = os.path.join(DATA_DIR, 'messages.json')
READ_RECEIPTS_FILE = os.path.join(DATA_DIR, 'read_receipts1.json')
SNAP_VIEWS_FILE = os.path.join(DATA_DIR, 'snap_views.json')
USER_ACTIVITY_FILE = os.path.join(DATA_DIR, 'user_activity.json')
LOUNGE_FILE = os.path.join(DATA_DIR, 'lounge.json')
RANKS_FILE = os.path.join(DATA_DIR, 'ranks.json')
PURCHASES_FILE = os.path.join(DATA_DIR, 'purchases.json')
CODES_FILE = os.path.join(DATA_DIR, 'codes.json')
REDEEMED_CODES_FILE = os.path.join(DATA_DIR, 'redeemed_codes.json')
RANK_PASS_FILE = os.path.join(DATA_DIR, 'rank_pass.json')
PLAYS_FILE = os.path.join(DATA_DIR, 'game_plays.json')
LOUNGE_REACTIONS_FILE = os.path.join(DATA_DIR, 'lounge_reactions.json')
LOUNGE_READ_RECEIPTS_FILE = os.path.join(DATA_DIR, 'lounge_read_receipts1.json')
LOUNGE_TYPING_FILE = os.path.join(DATA_DIR, 'lounge_typing.json')
LOUNGE_MESSAGE_READS_FILE = os.path.join(DATA_DIR, 'lounge_message_reads.json')
MAINTENANCE_FILE = os.path.join(DATA_DIR, 'maintenance.json')
TOWER_WINS_FILE = os.path.join(DATA_DIR, 'tower_wins.json')
PROFILES_FILE = os.path.join(DATA_DIR, 'profiles.json')
LOGIN_NOTIFICATIONS_FILE = os.path.join(DATA_DIR, 'login_notifications.json')
LOTTERY_FILE = os.path.join(DATA_DIR, 'lottery.json')
LOTTERY_TICKETS_FILE = os.path.join(DATA_DIR, 'lottery_tickets.json')
COINFLIP_WINS_FILE = 'coinflip_wins.json'
RPS_GAMES_FILE = os.path.join(DATA_DIR, 'rps_games.json')
RPS_HISTORY_FILE = os.path.join(DATA_DIR, 'rps_history.json')
SITE_ACCESS_FILE = os.path.join(DATA_DIR, 'site_access.json')
GROUPS_FILE = os.path.join(DATA_DIR, 'groups.json')
GROUP_MESSAGES_FILE = os.path.join(DATA_DIR, 'group_messages.json')
GROUP_REACTIONS_FILE = os.path.join(DATA_DIR, 'group_reactions.json')
GROUP_READ_RECEIPTS_FILE = os.path.join(DATA_DIR, 'group_read_receipts.json')
ACTION_LOGS_FILE = os.path.join(DATA_DIR, 'action_logs.json')
TOKEN_TRANSACTIONS_FILE = os.path.join(DATA_DIR, 'token_transactions.json')
REPORTED_MESSAGES_FILE = os.path.join(DATA_DIR, 'reported_messages.json')
PAYCHECKS_FILE = os.path.join(DATA_DIR, 'paychecks.json')
CASINO_STATS_FILE = os.path.join(DATA_DIR, 'casino_stats.json')
LOTTERY_HISTORY_FILE = os.path.join(DATA_DIR, 'lottery_history.json')
GMAIL_TOKENS_FILE = os.path.join(DATA_DIR, 'gmail_tokens.json')
GMAIL_CREDENTIALS_FILE = os.path.join(DATA_DIR, 'client_secret.json')
IDLE_DICE_ACHIEVEMENTS_FILE = os.path.join(DATA_DIR, 'idle_dice_achievements.json')
IDLE_DICE_CLAIMS_FILE = os.path.join(DATA_DIR, 'idle_dice_claims.json')

tower_games = {}


# Create data directory if it doesn't exist
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ===============================================================
# JSON persistence helpers
# ===============================================================
def load_json(filepath, default_data):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default_data
    return default_data

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ===============================================================
# Core helpers and time utilities
# ===============================================================
def get_ny_time():
    ny_tz = pytz.timezone('America/New_York')
    return datetime.now(ny_tz)

# Helper function to create consistent chat keys
def get_chat_key(user1, user2):
    return '-'.join(sorted([user1, user2]))

def load_coinflip_wins():
    if os.path.exists(COINFLIP_WINS_FILE):
        with open(COINFLIP_WINS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_coinflip_wins(wins):
    with open(COINFLIP_WINS_FILE, 'w') as f:
        json.dump(wins, f, indent=4)

def has_permission(username, permission):
    """Check if user has a specific permission"""
    if username not in users:
        return False
    user_role = users[username].get('role', 'user')
    return user_role in PERMISSIONS.get(permission, [])

def get_user_role_info(username):
    """Get role information for a user"""
    if username not in users:
        return STAFF_ROLES['user']
    user_role = users[username].get('role', 'user')
    return STAFF_ROLES.get(user_role, STAFF_ROLES['user'])

def log_action(actor, action_type, target=None, details=None, reason=None):
    """Log an action performed by staff"""
    log_entry = {
        'id': len(action_logs) + 1,
        'actor': actor,
        'actor_role': users.get(actor, {}).get('role', 'unknown'),
        'action_type': action_type,
        'target': target,
        'details': details,
        'reason': reason,
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    }
    action_logs.insert(0, log_entry)
    # Keep only last 1000 logs
    if len(action_logs) > 1000:
        action_logs.pop()
    save_json(ACTION_LOGS_FILE, action_logs)
    return log_entry

def log_transaction(transaction_type, amount, user, source, details=None):
    """Log a token transaction"""
    # Calculate new total tokens in circulation
    total_tokens = sum(u.get('tokens', 0) for u in users.values())

    transaction = {
        'id': len(token_transactions) + 1,
        'type': transaction_type,  # 'creation', 'destruction', 'transfer'
        'amount': amount,
        'user': user,
        'source': source,  # e.g., 'daily_reward', 'lottery_win', 'game_purchase', 'gift', 'code_redeem'
        'details': details,
        'total_circulation': total_tokens,
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    }
    token_transactions.insert(0, transaction)
    # Keep only last 5000 transactions
    if len(token_transactions) > 5000:
        token_transactions.pop()
    save_json(TOKEN_TRANSACTIONS_FILE, token_transactions)
    return transaction

def log_casino_game(game_type, username, bet_amount, won, profit_loss, details=None):
    """Log a casino game result"""
    entry = {
        'username': username,
        'bet_amount': bet_amount,
        'won': won,
        'profit_loss': profit_loss,
        'details': details,
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    }

    if game_type not in casino_stats:
        casino_stats[game_type] = []

    casino_stats[game_type].insert(0, entry)
    # Keep only last 1000 per game type
    if len(casino_stats[game_type]) > 1000:
        casino_stats[game_type].pop()

    save_json(CASINO_STATS_FILE, casino_stats)
    return entry

def get_token_statistics():
    """Calculate comprehensive token statistics"""
    total_tokens = sum(u.get('tokens', 0) for u in users.values())

    # Calculate tokens by source (last 30 days)
    thirty_days_ago = (get_ny_time() - timedelta(days=30)).strftime('%Y-%m-%d')

    created_by_source = {}
    destroyed_by_source = {}

    for tx in token_transactions:
        if tx['timestamp'] < thirty_days_ago:
            continue

        if tx['type'] == 'creation':
            source = tx['source']
            created_by_source[source] = created_by_source.get(source, 0) + tx['amount']
        elif tx['type'] == 'destruction':
            source = tx['source']
            destroyed_by_source[source] = destroyed_by_source.get(source, 0) + tx['amount']

    # Daily totals for graph (last 14 days)
    daily_totals = {}
    for tx in token_transactions:
        date = tx['timestamp'].split(' ')[0]
        if date not in daily_totals:
            daily_totals[date] = tx.get('total_circulation', 0)

    return {
        'total_circulation': total_tokens,
        'created_by_source': created_by_source,
        'destroyed_by_source': destroyed_by_source,
        'daily_totals': daily_totals,
        'total_transactions': len(token_transactions)
    }

def get_casino_statistics():
    """Calculate casino profit/loss statistics"""
    stats = {
        'coinflip': {'total_games': 0, 'house_profit': 0, 'player_wins': 0, 'player_losses': 0},
        'tower': {'total_games': 0, 'house_profit': 0, 'player_wins': 0, 'player_losses': 0},
        'blackjack': {'total_games': 0, 'house_profit': 0, 'player_wins': 0, 'player_losses': 0},
        'rps': {'total_games': 0, 'total_pot': 0}
    }

    # Coinflip stats
    for game in casino_stats.get('coinflip', []):
        stats['coinflip']['total_games'] += 1
        if game['won']:
            stats['coinflip']['player_wins'] += game['profit_loss']
            stats['coinflip']['house_profit'] -= game['profit_loss']
        else:
            stats['coinflip']['player_losses'] += abs(game['profit_loss'])
            stats['coinflip']['house_profit'] += abs(game['profit_loss'])

    # Tower stats
    for game in casino_stats.get('tower', []):
        stats['tower']['total_games'] += 1
        if game['won']:
            stats['tower']['player_wins'] += game['profit_loss']
            stats['tower']['house_profit'] -= game['profit_loss']
        else:
            stats['tower']['player_losses'] += abs(game['profit_loss'])
            stats['tower']['house_profit'] += abs(game['profit_loss'])

    # Blackjack stats
    for game in casino_stats.get('blackjack', []):
        stats['blackjack']['total_games'] += 1
        if game['won']:
            stats['blackjack']['player_wins'] += game['profit_loss']
            stats['blackjack']['house_profit'] -= game['profit_loss']
        else:
            stats['blackjack']['player_losses'] += abs(game['profit_loss'])
            stats['blackjack']['house_profit'] += abs(game['profit_loss'])

    # RPS is player vs player, no house profit
    for game in casino_stats.get('rps', []):
        stats['rps']['total_games'] += 1
        stats['rps']['total_pot'] += game.get('bet_amount', 0) * 2

    return stats

# ===============================================================
# Default in-memory data structures
# ===============================================================
default_users = {
    'admin': {
        'password': 'admin123',
        'role': 'admin',
        'banned': False,
        'ban_reason': ''
    }
}

default_games = {}

# Load data from JSON files
users = load_json(USERS_FILE, default_users)
games = load_json(GAMES_FILE, default_games)
announcements = load_json(ANNOUNCEMENTS_FILE, [])
feedback = load_json(FEEDBACK_FILE, [])
website_requests = load_json(WEBSITE_REQUESTS_FILE, [])
messages = load_json(MESSAGES_FILE, {})
read_receipts = load_json(READ_RECEIPTS_FILE, {})
# Snap views tracking: {chat_key: {message_index: {'opened_by': [users], 'replayed_by': [users]}}}
snap_views = load_json(SNAP_VIEWS_FILE, {})
user_activity = load_json(USER_ACTIVITY_FILE, {})
lounge_messages = load_json(LOUNGE_FILE, [])

# MIGRATION: Fix old message format (normalize 'from' field and remove legacy fields)
messages_migrated = False
for msg in lounge_messages:
    # Fix old system messages that used 'username' instead of 'from'
    if 'username' in msg and 'from' not in msg:
        msg['from'] = msg['username'].lower()  # "System" -> "system"
        del msg['username']
        messages_migrated = True
    # Remove legacy 'is_system' field (no longer needed)
    if 'is_system' in msg:
        del msg['is_system']
        messages_migrated = True

if messages_migrated:
    print(f"[MIGRATION] Migrated old lounge messages to new format")
    save_json(LOUNGE_FILE, lounge_messages)

lounge_reactions = load_json(LOUNGE_REACTIONS_FILE, {})
lounge_read_receipts = load_json(LOUNGE_READ_RECEIPTS_FILE, {})
lounge_typing = load_json(LOUNGE_TYPING_FILE, {})

LOUNGE_BADGE_ROLES = {'admin', 'ambassador', 'master_moderator'}

def get_lounge_staff_tag(username):
    """Return staff tag slug for lounge badges, or None if not eligible."""
    role = users.get(username, {}).get('role')
    return role if role in LOUNGE_BADGE_ROLES else None

# Debug logging for lounge messages on startup
print(f"[STARTUP DEBUG] ========================================")
print(f"[STARTUP DEBUG] DATA_DIR: {DATA_DIR}")
print(f"[STARTUP DEBUG] LOUNGE_FILE: {LOUNGE_FILE}")
print(f"[STARTUP DEBUG] Lounge messages loaded: {len(lounge_messages)}")
if os.path.exists(LOUNGE_FILE):
    file_size = os.path.getsize(LOUNGE_FILE)
    print(f"[STARTUP DEBUG] Lounge file exists, size: {file_size} bytes")
else:
    print(f"[STARTUP DEBUG] WARNING: Lounge file does NOT exist!")
print(f"[STARTUP DEBUG] ========================================")

lounge_message_reads = load_json(LOUNGE_MESSAGE_READS_FILE, {})
login_notifications = load_json(LOGIN_NOTIFICATIONS_FILE, {})
gmail_tokens = load_json(GMAIL_TOKENS_FILE, {})
maintenance_mode = load_json(MAINTENANCE_FILE, {
    'enabled': False,
    'title': "What's Coming",
    'notes': []
})
tower_recent_wins = load_json(TOWER_WINS_FILE, [])
profiles = load_json(PROFILES_FILE, {})

rps_games = load_json(RPS_GAMES_FILE, {})
rps_history = load_json(RPS_HISTORY_FILE, [])

# Load Idle Dice achievement data
idle_dice_achievements = load_json(IDLE_DICE_ACHIEVEMENTS_FILE, {
    # Basic Achievements
    'firstSteps': {'name': 'First Steps', 'description': 'Start your journey', 'tokens': 1, 'category': 'Basic', 'check': 'a_value_firstSteps>=1'},
    'points1m': {'name': 'Millionaire', 'description': 'Reach 1M points', 'tokens': 10, 'category': 'Basic', 'check': 'a_value_points1m>=1000000'},
    'points1b': {'name': 'Billionaire', 'description': 'Reach 1B points', 'tokens': 20, 'category': 'Basic', 'check': 'a_value_points1b>=1000000000'},
    'points1t': {'name': 'Trillionaire', 'description': 'Reach 1T points', 'tokens': 40, 'category': 'Basic', 'check': 'a_value_points1t>=1000000000000'},
    'points1qa': {'name': 'Quadrillionaire', 'description': 'Reach 1Qa points', 'tokens': 80, 'category': 'Basic', 'check': 'a_value_points1qa>=1000000000000000'},
    'points1qi': {'name': 'Quintillionaire', 'description': 'Reach 1Qi points', 'tokens': 150, 'category': 'Basic', 'check': 'a_value_points1qi>=1000000000000000000'},
    'roll20': {'name': 'Roll 20', 'description': 'Roll the dice 20 times', 'tokens': 5, 'category': 'Basic', 'check': 'a_value_roll20>=20'},
    'roll1k': {'name': 'Roll 1000', 'description': 'Roll the dice 1000 times', 'tokens': 35, 'category': 'Basic', 'check': 'a_value_roll1k>=1000'},
    'prestige2': {'name': 'Prestige 2', 'description': 'Prestige 2 times', 'tokens': 10, 'category': 'Basic', 'check': 'a_value_prestige2>=2'},
    'prestige10': {'name': 'Prestige 10', 'description': 'Prestige 10 times', 'tokens': 25, 'category': 'Basic', 'check': 'a_value_prestige10>=10'},
    'prestige100': {'name': 'Prestige 100', 'description': 'Prestige 100 times', 'tokens': 50, 'category': 'Basic', 'check': 'a_value_prestige100>=100'},
    'prestige1k': {'name': 'Prestige 1000', 'description': 'Prestige 1000 times', 'tokens': 100, 'category': 'Basic', 'check': 'a_value_prestige1k>=1000'},
    'lazy': {'name': 'Lazy', 'description': 'Be lazy', 'tokens': 5, 'category': 'Basic', 'check': 'a_value_lazy>=1'},
    'playtime1': {'name': 'Playtime 1h', 'description': 'Play for 1 hour', 'tokens': 5, 'category': 'Basic', 'check': 'a_value_playtime1>=1'},
    'playtime24': {'name': 'Playtime 24h', 'description': 'Play for 24 hours', 'tokens': 15, 'category': 'Basic', 'check': 'a_value_playtime24>=1'},
    'playtime168': {'name': 'Playtime 168h', 'description': 'Play for 168 hours (1 week)', 'tokens': 30, 'category': 'Basic', 'check': 'a_value_playtime168>=1'},

    # Advanced Achievements (Card-based - correct IDs from game)
    'cards5': {'name': 'Full Hand', 'description': 'Draw 5 cards in one run', 'tokens': 6, 'category': 'Advanced', 'check': 'a_value_cards5>=5'},
    'cards10': {'name': 'Double or Nothing', 'description': 'Draw 10 cards in one run', 'tokens': 10, 'category': 'Advanced', 'check': 'a_value_cards10>=10'},
    'cards15': {'name': 'Three Hands Full', 'description': 'Draw 15 cards in one run', 'tokens': 15, 'category': 'Advanced', 'check': 'a_value_cards15>=15'},
    'cards20': {'name': 'Draw 20', 'description': 'Draw 20 cards in one run', 'tokens': 20, 'category': 'Advanced', 'check': 'a_value_cards20>=20'},
    'cards26': {'name': 'Half Deck', 'description': 'Draw 26 cards in one run', 'tokens': 25, 'category': 'Advanced', 'check': 'a_value_cards26>=26'},
    'cards32': {'name': 'Wrong Type of Deck', 'description': 'Draw 32 cards in one run', 'tokens': 30, 'category': 'Advanced', 'check': 'a_value_cards32>=32'},
    'cards45': {'name': 'Almost Done', 'description': 'Draw 45 cards in one run', 'tokens': 35, 'category': 'Advanced', 'check': 'a_value_cards45>=45'},
    'cards52': {'name': 'Full Deck', 'description': 'Draw 52 cards in one run', 'tokens': 50, 'category': 'Advanced', 'check': 'a_value_cards52>=52'},
    'cards4_2': {'name': 'Strategic Mastermind', 'description': 'Draw 4 2s in one run', 'tokens': 20, 'category': 'Advanced', 'check': 'a_value_cards4_2>=4'},
    'cards4_3': {'name': 'Equality', 'description': 'Draw 4 3s in one run', 'tokens': 25, 'category': 'Advanced', 'check': 'a_value_cards4_3>=4'},
    'cards4_4': {'name': 'Into Heaven', 'description': 'Draw 4 4s in one run', 'tokens': 30, 'category': 'Advanced', 'check': 'a_value_cards4_4>=4'},
    'cards4_5': {'name': 'Combo Master', 'description': 'Draw 4 5s in one run', 'tokens': 35, 'category': 'Advanced', 'check': 'a_value_cards4_5>=4'},
    'cards4_6': {'name': '5th Dice', 'description': 'Draw 4 6s in one run', 'tokens': 40, 'category': 'Advanced', 'check': 'a_value_cards4_6>=4'},
    'cards4_7': {'name': '4th Dice', 'description': 'Draw 4 7s in one run', 'tokens': 35, 'category': 'Advanced', 'check': 'a_value_cards4_7>=4'},
    'cards4_8': {'name': '3rd Dice', 'description': 'Draw 4 8s in one run', 'tokens': 30, 'category': 'Advanced', 'check': 'a_value_cards4_8>=4'},
    'cards4_9': {'name': '2nd Dice', 'description': 'Draw 4 9s in one run', 'tokens': 25, 'category': 'Advanced', 'check': 'a_value_cards4_9>=4'},
    'cards4_10': {'name': '1st Dice', 'description': 'Draw 4 10s in one run', 'tokens': 20, 'category': 'Advanced', 'check': 'a_value_cards4_10>=4'},
    'cards4_J': {'name': 'Faster!!', 'description': 'Draw 4 Jacks in one run', 'tokens': 25, 'category': 'Advanced', 'check': 'a_value_cards4_J>=4'},
    'cards4_Q': {'name': 'Multiply the Multipliers', 'description': 'Draw 4 Queens in one run', 'tokens': 40, 'category': 'Advanced', 'check': 'a_value_cards4_Q>=4'},
    'cards4_K': {'name': 'Patience', 'description': 'Draw 4 Kings in one run', 'tokens': 50, 'category': 'Advanced', 'check': 'a_value_cards4_K>=4'},
    'cards4_A': {'name': 'No Patience', 'description': 'Draw 4 Aces in one run', 'tokens': 50, 'category': 'Advanced', 'check': 'a_value_cards4_A>=4'},

    # Expert Achievements (Roulette-based)
    'autoroll100': {'name': 'Autoroll 100', 'description': 'Reach autoroll milestone 100', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_autoroll100>=100'},
    'spin5': {'name': 'Spin 5', 'description': 'Spin the roulette 5 times in total', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_spin5>=5'},
    'spin100': {'name': 'Spin 100', 'description': 'Spin the roulette 100 times in total', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_spin100>=100'},
    'spinRun5': {'name': 'Spinner', 'description': 'Spin the roulette 5 times in one run', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_spinrun5>=5'},
    'spinRun15': {'name': 'Expert Spinner', 'description': 'Spin the roulette 15 times in one run', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_spinrun15>=15'},
    'spinRun100': {'name': 'Fidget Spinner', 'description': 'Spin the roulette 100 times in one run', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_spinrun100>=100'},
    'spin10noLevel': {'name': 'Unlucky', 'description': 'Spin the roulette 10 times on level 0 without leveling up', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_spin10noLevel>=10'},
    'roulette3': {'name': 'Roulette 3', 'description': 'Reach roulette level 3', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette3>=3'},
    'roulette5': {'name': 'Roulette 5', 'description': 'Reach roulette level 5', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette5>=5'},
    'roulette7': {'name': 'Roulette 7', 'description': 'Reach roulette level 7', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette7>=7'},
    'roulette8': {'name': 'Roulette 8', 'description': 'Reach roulette level 8', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette8>=8'},
    'roulette9': {'name': 'Roulette 9', 'description': 'Reach roulette level 9', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette9>=9'},
    'roulette10': {'name': 'Roulette 10', 'description': 'Reach roulette level 10', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette10>=10'},
    'roulette11': {'name': 'Roulette 11', 'description': 'Reach roulette level 11', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette11>=11'},
    'roulette20': {'name': 'Roulette 20', 'description': 'Reach roulette level 20', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette20>=20'},
    'roulette25': {'name': 'Roulette 25', 'description': 'Reach roulette level 25', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette25>=25'},
    'roulette34': {'name': 'Roulette Max', 'description': 'Reach roulette level 34', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_roulette34>=34'},
    'pair1000': {'name': 'Pair Master', 'description': 'Roll 1000 pairs', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_pair1000>=1000'},
    'triplet1000': {'name': 'Triplet Master', 'description': 'Roll 1000 triplets', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_triplet1000>=1000'},
    'twopair1000': {'name': 'Two Pair Master', 'description': 'Roll 1000 two pairs', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_twopair1000>=1000'},
    'four1000': {'name': 'Four Master', 'description': 'Roll 1000 fours', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_four1000>=1000'},
    'fullhouse1000': {'name': 'Full House Master', 'description': 'Roll 1000 full houses', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_fullhouse1000>=1000'},
    'five1000': {'name': 'Five Master', 'description': 'Roll 1000 fives', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_five1000>=1000'},
    'straight1000': {'name': 'Straight Master', 'description': 'Roll 1000 straights', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_straight1000>=1000'},
    'straight1k': {'name': 'Straight Master (Legacy)', 'description': 'Roll 1000 straights', 'tokens': 10, 'category': 'Expert', 'check': 'a_value_straight1k>=1000'},

    # Legendary Achievements (Golden cards and special milestones)
    'gold_2': {'name': 'God of strategy', 'description': 'Have 4 golden 2s', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_gold_2>=4'},
    'gold_3': {'name': 'Equality (Gold)', 'description': 'Have 4 golden 3s', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_gold_3>=4'},
    'gold_4': {'name': 'Into the universe', 'description': 'Have 4 golden 4s', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_gold_4>=4'},
    'gold_5': {'name': 'Combining galaxies', 'description': 'Have 4 golden 5s', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_gold_5>=4'},
    'gold_A': {'name': 'Spinning Ace', 'description': 'Have 4 golden As', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_gold_A>=4'},
    'golden52': {'name': 'Golden deck', 'description': 'Have 52 golden cards', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_golden52>=52'},
    'noPrestige': {'name': 'No prestige needed', 'description': 'Convert a deck without prestiging', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_noPrestige>=1'},
    'focus10': {'name': 'Meditation', 'description': 'Have a focus charge of 10', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_focus10>=10'},
    'lucke100': {'name': 'Goose', 'description': 'Have 1e100 luck', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_lucke100>=1e100'},
    'noRoll': {'name': 'Too slow', 'description': 'Do not roll the dice for 1 minute', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_noRoll>=1'},

    # Godlike Achievements (Casinos and prestige milestones)
    'roulette35': {'name': 'Roulette Prestige', 'description': 'Reach roulette level 35', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_roulette35>=35'},
    'casino1': {'name': 'Investment Beginner', 'description': 'Have 1 casino', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino1>=1'},
    'casino2': {'name': 'Roulette Investor', 'description': 'Have 2 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino2>=2'},
    'casino3': {'name': 'Investor', 'description': 'Have 3 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino3>=3'},
    'casino4': {'name': 'Investing into speed', 'description': 'Have 4 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino4>=4'},
    'casino5': {'name': 'Chip Factory', 'description': 'Have 5 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino5>=5'},
    'casino6': {'name': 'Swiss Bank Account', 'description': 'Have 6 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino6>=6'},
    'casino7': {'name': 'Lucky Number', 'description': 'Have 7 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino7>=7'},
    'casino8': {'name': 'Chip Mass Production', 'description': 'Have 8 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino8>=8'},
    'casino9': {'name': 'Corruption', 'description': 'Have 9 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino9>=9'},
    'casino10': {'name': 'Employees', 'description': 'Have 10 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino10>=10'},
    'casino11': {'name': 'Can buy anything', 'description': 'Have 11 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino11>=11'},
    'casino12': {'name': 'Getting Lazy', 'description': 'Have 12 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino12>=12'},
    'casino13': {'name': 'Unlucky Number', 'description': 'Have 13 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino13>=13'},
    'casino14': {'name': 'Particle Accelerator', 'description': 'Have 14 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino14>=14'},
    'casino15': {'name': 'Greed', 'description': 'Have 15 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino15>=15'},
    'casino16': {'name': 'Hexadecagonal Chips', 'description': 'Have 16 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino16>=16'},
    'casino17': {'name': 'Happiness', 'description': 'Have 17 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino17>=17'},
    'casino18': {'name': 'No flavor for this one', 'description': 'Have 18 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino18>=18'},
    'casino19': {'name': 'Accelerator Farm', 'description': 'Have 19 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino19>=19'},
    'casino20': {'name': 'Slaves', 'description': 'Have 20 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino20>=20'},
    'casino21': {'name': 'Blackjack', 'description': 'Have 21 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino21>=21'},
    'casino22': {'name': 'Interesting', 'description': 'Have 22 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino22>=22'},
    'casino23': {'name': 'Sun Harvesting', 'description': 'Have 23 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino23>=23'},
    'casino24': {'name': 'Gluttony', 'description': 'Have 24 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino24>=24'},
    'casino25': {'name': 'Mega Chips', 'description': 'Have 25 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino25>=25'},
    'casino26': {'name': 'Fulfillment', 'description': 'Have 26 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino26>=26'},
    'casino27': {'name': 'Upgrade Machines', 'description': 'Have 27 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino27>=27'},
    'casino28': {'name': 'Very Interesting', 'description': 'Have 28 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino28>=28'},
    'casino29': {'name': 'Speed of light', 'description': 'Have 29 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino29>=29'},
    'casino30': {'name': 'Lust', 'description': 'Have 30 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino30>=30'},
    'casino33': {'name': 'God of Luck', 'description': 'Have 33 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino33>=33'},
    'casino35': {'name': 'Giga Chips', 'description': 'Have 35 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino35>=35'},
    'casino40': {'name': 'Gladstone Gander', 'description': 'Have 40 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino40>=40'},
    'casino45': {'name': 'Upgrade Slaves', 'description': 'Have 45 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino45>=45'},
    'casino50': {'name': 'Need more Names', 'description': 'Have 50 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino50>=50'},
    'casino55': {'name': 'Hypnotizing', 'description': 'Have 55 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino55>=55'},
    'casino60': {'name': 'Pride', 'description': 'Have 60 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino60>=60'},
    'casino65': {'name': 'What will you do with all these Chips?', 'description': 'Have 65 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino65>=65'},
    'casino70': {'name': 'Nothing bad will ever happen to you', 'description': 'Have 70 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino70>=70'},
    'casino75': {'name': 'Upgrade Drones', 'description': 'Have 75 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino75>=75'},
    'casino80': {'name': 'Seriously', 'description': 'Have 80 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino80>=80'},
    'casino85': {'name': 'Can your Computer even handle this speed', 'description': 'Have 85 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino85>=85'},
    'casino90': {'name': 'Envy', 'description': 'Have 90 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino90>=90'},
    'casino95': {'name': 'Stop', 'description': 'Have 95 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino95>=95'},
    'casino100': {'name': 'No need to play anymore', 'description': 'Have 100 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino100>=100'},
    'casino200': {'name': 'Fine, go double as far as it was ever intended', 'description': 'Have 200 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino200>=200'},
})
idle_dice_claims = load_json(IDLE_DICE_CLAIMS_FILE, {})

def _rebuild_idle_dice_achievements(data):
    """Restrict Idle Dice achievements to the desired subset and adjust token values."""
    allowed_basic = {
        'firstSteps': {'name': 'First Steps', 'description': 'Start your journey', 'tokens': 10, 'category': 'Basic', 'check': 'a_value_firstSteps>=1'},
        'roll20': {'name': 'Roll 20', 'description': 'Roll the dice 20 times', 'tokens': 10, 'category': 'Basic', 'check': 'a_value_roll20>=20'},
        'playtime1': {'name': 'Playtime 1h', 'description': 'Play for 1 hour', 'tokens': 20, 'category': 'Basic', 'check': 'a_value_playtime1>=1'},
        'points1m': {'name': 'Millionaire', 'description': 'Reach 1M points', 'tokens': 50, 'category': 'Basic', 'check': 'a_value_points1m>=1000000'},
        'prestige2': {'name': 'Prestige 2', 'description': 'Prestige 2 times', 'tokens': 25, 'category': 'Basic', 'check': 'a_value_prestige2>=2'},
        'points1b': {'name': 'Billionaire', 'description': 'Reach 1B points', 'tokens': 100, 'category': 'Basic', 'check': 'a_value_points1b>=1000000000'},
        'roll1k': {'name': 'Roll 1000', 'description': 'Roll the dice 1000 times', 'tokens': 100, 'category': 'Basic', 'check': 'a_value_roll1k>=1000'},
        'points1t': {'name': 'Trillionaire', 'description': 'Reach 1T points', 'tokens': 125, 'category': 'Basic', 'check': 'a_value_points1t>=1000000000000'},
        'points1qa': {'name': 'Quadrillionaire', 'description': 'Reach 1Qa points', 'tokens': 150, 'category': 'Basic', 'check': 'a_value_points1qa>=1000000000000000'},
        'points1qi': {'name': 'Quintillionaire', 'description': 'Reach 1Qi points', 'tokens': 180, 'category': 'Basic', 'check': 'a_value_points1qi>=1000000000000000000'}
    }

    allowed_advanced = {
        'cards5': {'name': 'Full Hand', 'description': 'Draw 5 cards in one run', 'tokens': 50, 'category': 'Advanced', 'check': 'a_value_cards5>=5'},
        'cards4_A': {'name': 'No Patience', 'description': 'Draw 4 Aces in one run', 'tokens': 50, 'category': 'Advanced', 'check': 'a_value_cards4_A>=4'},
        'cards4_K': {'name': 'Patience', 'description': 'Draw 4 Kings in one run', 'tokens': 50, 'category': 'Advanced', 'check': 'a_value_cards4_K>=4'}
    }

    allowed_expert = {
        'spinRun15': {'name': 'Expert Spinner', 'description': 'Spin the roulette 15 times in one run', 'tokens': 20, 'category': 'Expert', 'check': 'a_value_spinrun15>=15'},
        'roulette10': {'name': 'Roulette 10', 'description': 'Reach roulette level 10', 'tokens': 35, 'category': 'Expert', 'check': 'a_value_roulette10>=10'},
        'straight1000': {'name': 'Straight Master', 'description': 'Roll 1000 straights', 'tokens': 40, 'category': 'Expert', 'check': 'a_value_straight1000>=1000'}
    }

    allowed_legendary = {
        'gold_2': {'name': 'God of strategy', 'description': 'Have 4 golden 2s', 'tokens': 35, 'category': 'Legendary', 'check': 'a_value_gold_2>=4'},
        'gold_A': {'name': 'Spinning Ace', 'description': 'Have 4 golden As', 'tokens': 20, 'category': 'Legendary', 'check': 'a_value_gold_A>=4'},
        'golden52': {'name': 'Golden deck', 'description': 'Have 52 golden cards', 'tokens': 50, 'category': 'Legendary', 'check': 'a_value_golden52>=52'},
        'focus10': {'name': 'Meditation', 'description': 'Have a focus charge of 10', 'tokens': 10, 'category': 'Legendary', 'check': 'a_value_focus10>=10'},
        'lucke100': {'name': 'Goose', 'description': 'Have 1e100 luck', 'tokens': 35, 'category': 'Legendary', 'check': 'a_value_lucke100>=1e100'}
    }

    allowed_godlike = {
        'casino10': {'name': 'Employees', 'description': 'Have 10 casinos', 'tokens': 30, 'category': 'Godlike', 'check': 'a_value_casino10>=10'},
        'casino25': {'name': 'Mega Chips', 'description': 'Have 25 casinos', 'tokens': 25, 'category': 'Godlike', 'check': 'a_value_casino25>=25'},
        'casino50': {'name': 'Need more Names', 'description': 'Have 50 casinos', 'tokens': 10, 'category': 'Godlike', 'check': 'a_value_casino50>=50'},
        'casino100': {'name': 'No need to play anymore', 'description': 'Have 100 casinos', 'tokens': 100, 'category': 'Godlike', 'check': 'a_value_casino100>=100'}
    }

    rebuilt = {}
    rebuilt.update(allowed_basic)
    rebuilt.update(allowed_advanced)
    rebuilt.update(allowed_expert)
    rebuilt.update(allowed_legendary)
    rebuilt.update(allowed_godlike)

    return rebuilt

idle_dice_achievements = _rebuild_idle_dice_achievements(idle_dice_achievements)

user_ranks = load_json(RANKS_FILE, {})
purchases = load_json(PURCHASES_FILE, {})
codes = load_json(CODES_FILE, {})
redeemed_codes = load_json(REDEEMED_CODES_FILE, {})
rank_pass_state = load_json(RANK_PASS_FILE, {})
plays = load_json(PLAYS_FILE, {})

lottery_state = load_json(LOTTERY_FILE, {
    'active': False,
    'prize_pool': 0,  # Now set by admin, not accumulated
    'ticket_price': 0,
    'end_time': None,
    'created_at': None,
    'winner': None,
    'winner_tickets': None,
    'total_tickets': None,
    'won_at': None,
    'won_amount': None
})

lottery_tickets = load_json(LOTTERY_TICKETS_FILE, {})
site_access = load_json(SITE_ACCESS_FILE, {})

# Groups data
groups = load_json(GROUPS_FILE, {})

group_messages = load_json(GROUP_MESSAGES_FILE, {})
group_reactions = load_json(GROUP_REACTIONS_FILE, {})
group_read_receipts = load_json(GROUP_READ_RECEIPTS_FILE, {})

action_logs = load_json(ACTION_LOGS_FILE, [])
token_transactions = load_json(TOKEN_TRANSACTIONS_FILE, [])
reported_messages = load_json(REPORTED_MESSAGES_FILE, [])
paychecks = load_json(PAYCHECKS_FILE, {
    'pending': [],
    'history': []
})
casino_stats = load_json(CASINO_STATS_FILE, {
    'coinflip': [],
    'tower': [],
    'rps': []
})
lottery_history = load_json(LOTTERY_HISTORY_FILE, [])

# Performance optimization: Cache for expensive API calls
user_list_cache = {}
user_list_cache_time = 0

# ===============================================================
# One-time data migration / normalization
# ===============================================================
# Migrate existing data
for game_id in games:
    if 'available' not in games[game_id]:
        games[game_id]['available'] = True
    if 'price' not in games[game_id]:
        games[game_id]['price'] = 0
    if 'free_for_all' not in games[game_id]:
        games[game_id]['free_for_all'] = True
    if 'is_own_game' not in games[game_id]:
        games[game_id]['is_own_game'] = False
    if 'is_roblox_game' not in games[game_id]:
        games[game_id]['is_roblox_game'] = False
    if 'is_pokemon_game' not in games[game_id]:  # ✅ ADD THIS
        games[game_id]['is_pokemon_game'] = False  # ✅ ADD THIS
    if 'is_minecraft_game' not in games[game_id]:
        games[game_id]['is_minecraft_game'] = False
    if 'background_image' not in games[game_id]:
        games[game_id]['background_image'] = None

for username in users:
    if 'tokens' not in users[username]:
        users[username]['tokens'] = 0
    if 'rank' not in users[username]:
        users[username]['rank'] = None
    # NEW: Add password_changed flag
    if 'password_changed' not in users[username]:
        users[username]['password_changed'] = False

save_json(USERS_FILE, users)
save_json(GAMES_FILE, games)

# Initialize groups with rank and bank if they don't have them
for group_id in groups:
    if 'rank' not in groups[group_id]:
        groups[group_id]['rank'] = 0
    if 'bank' not in groups[group_id]:
        groups[group_id]['bank'] = 0
save_json(GROUPS_FILE, groups)

# In-memory typing status for chat
typing_status = {}

@app.before_request
def track_user_activity():
    if 'username' in session:
        username = session['username']
        user_activity[username] = get_ny_time().timestamp()

def periodic_save():
    while True:
        time.sleep(60)  # Save every 60 seconds
        save_json(USER_ACTIVITY_FILE, user_activity)

# Start the background thread when your app starts
save_thread = threading.Thread(target=periodic_save, daemon=True)
save_thread.start()

# Periodic RPS timeout check
def periodic_rps_check():
    while True:
        time.sleep(60)  # Check every minute
        check_rps_timeouts()

rps_check_thread = threading.Thread(target=periodic_rps_check, daemon=True)
rps_check_thread.start()

# ===============================================================
# Group Interest Scheduler
# ===============================================================
def apply_group_interest():
    """Apply interest to all group banks based on their rank - runs every Monday at 0 AM"""
    try:
        for group_id, group_data in groups.items():
            rank = group_data.get('rank', 0)
            bank = group_data.get('bank', 0)

            if rank > 0 and bank > 0:
                interest_rate = GROUP_RANKS[rank]['interest']
                interest_amount = int(bank * (interest_rate / 100))
                new_balance = bank + interest_amount

                groups[group_id]['bank'] = new_balance

                # Add system message to group chat
                if group_id not in group_messages:
                    group_messages[group_id] = []

                group_messages[group_id].append({
                    'from': 'system',
                    'text': f'Weekly interest applied. Bank received {interest_amount} tokens ({interest_rate}% interest). New balance: {new_balance} tokens',
                    'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
                })

        save_json(GROUPS_FILE, groups)
        save_json(GROUP_MESSAGES_FILE, group_messages)
        print(f"Group interest applied at {get_ny_time()}")
    except Exception as e:
        print(f"Error applying group interest: {e}")

# Initialize scheduler
scheduler = BackgroundScheduler(timezone='America/New_York')
# Run every Monday at 0:00 AM
scheduler.add_job(
    func=apply_group_interest,
    trigger=CronTrigger(day_of_week='mon', hour=0, minute=0),
    id='group_interest',
    name='Apply group interest',
    replace_existing=True
)
scheduler.start()

# ===============================================================
# Access control decorators
# ===============================================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        if users[session['username']]['banned']:
            return redirect(url_for('banned'))
        return f(*args, **kwargs)
    return decorated_function

def panel_access_required(f):
    """Check if user can access admin panel (any staff role)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        user_role = users[session['username']].get('role', 'user')
        staff_roles = ['admin', 'president', 'economy_director', 'pr_director', 'master_moderator', 'ambassador']
        if user_role not in staff_roles:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        if users[session['username']]['role'] != 'admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def password_change_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' in session:
            username = session['username']
            if not users[username].get('password_changed', False):
                return redirect(url_for('force_password_change'))
        return f(*args, **kwargs)
    return decorated_function

def maintenance_check(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if maintenance_mode.get('enabled', False):
            if 'username' not in session:
                return render_template('maintenance.html',
                    maintenance_title=maintenance_mode.get('title'),
                    maintenance_notes=maintenance_mode.get('notes', []))
            user_role = users.get(session['username'], {}).get('role', 'user')
            if user_role != 'admin':  # ONLY admin can access during maintenance
                return render_template('maintenance.html',
                    maintenance_title=maintenance_mode.get('title'),
                    maintenance_notes=maintenance_mode.get('notes', []))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    """Decorator to check if user has one of the allowed roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                return redirect(url_for('login'))
            user_role = users[session['username']].get('role', 'user')
            if user_role not in allowed_roles:
                return jsonify({'error': 'Permission denied'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def permission_required(permission):
    """Decorator to check if user has a specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                return redirect(url_for('login'))
            if not has_permission(session['username'], permission):
                return jsonify({'error': 'Permission denied'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Helper functions
def get_unread_count(username):
    """Count unread messages - messages TO you FROM others that you haven't read"""
    unread = 0
    for chat_key, msgs in messages.items():
        participants = chat_key.split('-')
        if username not in participants:
            continue

        # Get the other person in the chat
        other_user = participants[0] if participants[1] == username else participants[1]
        last_read = read_receipts.get(username, {}).get(chat_key, '')

        for msg in msgs:
            # ✅ TRIPLE CHECK: Must be TO you, FROM other person, AND after last read
            if (msg.get('to') == username and
                msg.get('from') == other_user and
                msg.get('from') != username and
                msg['timestamp'] > last_read):
                unread += 1

    return unread

def get_lounge_unread_count(username):
    """Count unread lounge messages - messages FROM others that you haven't read"""
    if not lounge_messages:
        return 0

    last_read = lounge_read_receipts.get(username, '')

    # If never read lounge, count ALL messages from others
    if not last_read:
        return sum(1 for msg in lounge_messages if msg.get('from') != username)

    # Count messages from others that are newer than last_read
    return sum(1 for msg in lounge_messages
               if msg.get('from') != username and msg['timestamp'] > last_read)

# OAuth 2.0 scopes for Gmail
SCOPES = ['https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.modify']

# Lunch menu data
lunch_menu = {
    '2026-01-05': {
        'food': 'Chicken Patty on a Bun, French Fries, Seasoned Carrots',
        'fact': 'Chicken patties are a popular school lunch because they provide protein in a familiar, easy-to-eat form that helps reduce food waste.',
        'breakfast': 'French Toast Sticks'
    },
    '2026-01-06': {
        'food': 'Nachos with Meat & Cheese, Black Beans, Corn',
        'fact': 'Black beans are rich in fiber and plant protein, which help students stay full and focused longer.',
        'breakfast': 'Cheese Omelet with 1/2 Bagel'
    },
    '2026-01-07': {
        'food': 'Chicken Alfredo over Rotini, Roasted Broccoli, Whole-Grain Dinner Roll',
        'fact': 'Whole-grain pasta provides longer-lasting energy than refined grains, supporting afternoon concentration.',
        'breakfast': 'Confetti Pancakes with 1/2 Bagel'
    },
    '2026-01-08': {
        'food': 'NY Southwest Chili, NY Black Beans, Corn, Onion, Carrots, Cornbread, NY Roasted Corn, NY Apple',
        'fact': 'Chili is a well-balanced meal that combines protein, vegetables, and fiber in one hearty dish.',
        'breakfast': 'Yogurt & Muffin'
    },
    '2026-01-09': {
        'food': 'Assorted Pizza, Romaine Salad with Tomatoes & Cucumbers',
        'fact': 'Serving salad alongside pizza helps balance carbohydrates with fresh vegetables and nutrients.',
        'breakfast': 'Breakfast Sandwich'
    },
    '2026-01-12': {
        'food': 'Cheeseburger on a Bun, Tater Tots, Baked Beans',
        'fact': 'Baked beans provide fiber and iron, which support muscle function and energy levels.',
        'breakfast': 'Breakfast on a Stick'
    },
    '2026-01-13': {
        'food': 'Tacos with Meat & Cheese, Rice, Corn',
        'fact': 'Rice is a key energy source for the brain, helping students stay alert during class.',
        'breakfast': 'Breakfast Pizza'
    },
    '2026-01-14': {
        'food': 'Cheesy Chicken & Rice, Broccoli, Whole-Grain Roll',
        'fact': 'Broccoli is high in vitamin C, which supports immune health during winter months.',
        'breakfast': 'Breakfast Banana Splits'
    },
    '2026-01-15': {
        'food': 'Rotini with Meat Sauce, Carrots, Whole-Grain Roll',
        'fact': 'Tomato-based sauces contain antioxidants that support long-term health.',
        'breakfast': 'Waffles'
    },
    '2026-01-16': {
        'food': 'Three-Cheese or Pepperoni Roll with Dipping Sauce, Romaine Salad with Tomatoes & Cucumbers',
        'fact': 'Cheese is an important source of calcium for growing bones and teeth.',
        'breakfast': 'Breakfast Sandwich'
    },
    '2026-01-17': {
        'food': 'No School - Martin Luther King Jr. Day',
        'fact': 'School is closed in observance of Martin Luther King Jr. Day.',
        'breakfast': 'No school today.'
    },
    '2026-01-20': {
        'food': 'Toasty Grilled Cheese Sandwich, Tomato Soup',
        'fact': 'Tomato soup helps boost vegetable intake and is especially popular in colder weather.',
        'breakfast': 'Cinni Minis'
    },
    '2026-01-21': {
        'food': 'Chicken & Cheese Quesadillas, Mexican Street Corn Salad',
        'fact': 'Corn provides natural carbohydrates that fuel learning and physical activity.',
        'breakfast': 'Coffee Cake'
    },
    '2026-01-22': {
        'food': 'Teriyaki Chicken Stir Fry over Rice with Peppers & Onions, Potstickers',
        'fact': 'Stir-fry meals introduce students to global flavors while delivering vegetables in an appealing way.',
        'breakfast': 'French Toast'
    },
    '2026-01-23': {
        'food': 'Assorted Pizza, Romaine Salad with Tomatoes & Cucumbers',
        'fact': 'Romaine lettuce contains folate, which supports focus and cognitive development.',
        'breakfast': 'Breakfast Sandwich'
    },
    '2026-01-26': {
        'food': 'Chicken Tenders, Potato Wedges, Carrots, Whole-Grain Dinner Roll',
        'fact': 'Whole grains help keep students energized longer than refined breads.',
        'breakfast': 'Apple Frudel'
    },
    '2026-01-27': {
        'food': 'Tater Tot Totchos with Taco Meat, Cheese, Salsa, Sour Cream, Seasoned Black Beans, Corn Muffin',
        'fact': 'Beans and grains together form a more complete protein for growing bodies.',
        'breakfast': 'Scrambled Eggs with 1/2 Bagel'
    },
    '2026-01-28': {
        'food': 'Hot Dog on a Bun, Macaroni Salad, Baked Beans',
        'fact': 'Carbohydrate-rich sides help replenish energy for afternoon learning.',
        'breakfast': 'Pancakes'
    },
    '2026-01-29': {
        'food': 'NY Sliced Pork Loin, Smashed NY Potatoes, NY Green Beans, Warmed NY Apples with Cinnamon & NY Honey Biscuit',
        'fact': 'Locally sourced meals support regional farms and often arrive fresher on students\' plates.',
        'breakfast': 'Yogurt & Muffin'
    },
    '2026-01-30': {
        'food': 'Assorted Pizza, Romaine Salad with Tomatoes & Cucumbers',
        'fact': 'Familiar end-of-week meals can increase participation in school lunch programs.',
        'breakfast': 'Breakfast Sandwich'
    }
}

# ===============================================================
# Google Classroom Helper Functions
# ===============================================================

# Define stub functions when Selenium is not available
if not SELENIUM_AVAILABLE:
    def get_classroom_driver(load_cookies=False, headless=True):
        raise RuntimeError("Selenium not installed - Google Classroom feature unavailable")

    def save_classroom_cookies(driver=None):
        pass

    def save_classroom_announcements_cache():
        with open(CLASSROOM_ANNOUNCEMENTS_FILE, 'w') as f:
            json.dump(classroom_announcements_cache, f)

    def load_classroom_announcements_cache():
        global classroom_announcements_cache
        if os.path.exists(CLASSROOM_ANNOUNCEMENTS_FILE):
            with open(CLASSROOM_ANNOUNCEMENTS_FILE, 'r') as f:
                classroom_announcements_cache = json.load(f)

    def scrape_classroom_announcements():
        print("⚠️  Google Classroom scraping disabled - selenium not installed")
        return

    def background_classroom_scraper():
        pass

else:
    # Selenium is available - define full functionality
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

        if load_cookies and os.path.exists(CLASSROOM_COOKIES_FILE):
            driver.get('https://classroom.google.com')
            with open(CLASSROOM_COOKIES_FILE, 'rb') as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    try:
                        driver.add_cookie(cookie)
                    except:
                        pass
            driver.refresh()

        return driver

    def save_classroom_cookies(driver):
        """Save browser cookies for future sessions."""
        cookies = driver.get_cookies()
        with open(CLASSROOM_COOKIES_FILE, 'wb') as f:
            pickle.dump(cookies, f)

    def save_classroom_announcements_cache():
        """Save announcements to file."""
        with open(CLASSROOM_ANNOUNCEMENTS_FILE, 'w') as f:
            json.dump(classroom_announcements_cache, f)

    def load_classroom_announcements_cache():
        """Load announcements from file."""
        global classroom_announcements_cache
        if os.path.exists(CLASSROOM_ANNOUNCEMENTS_FILE):
            with open(CLASSROOM_ANNOUNCEMENTS_FILE, 'r') as f:
                classroom_announcements_cache = json.load(f)

    def scrape_classroom_announcements():
        """Scrape announcements from Google Classroom."""
        global classroom_announcements_cache, CLASSROOM_ID

        if not CLASSROOM_ID or not os.path.exists(CLASSROOM_COOKIES_FILE):
            print("⚠️  No classroom configured or not logged in yet")
            return

        driver = None
        try:
            print(f"🔄 Scraping Google Classroom announcements... [{datetime.now().strftime('%H:%M:%S')}]")
            driver = get_classroom_driver(load_cookies=True)
            driver.get(f'https://classroom.google.com/u/0/c/{CLASSROOM_ID}')

            time.sleep(3)

            # Scroll down to load announcements
            driver.execute_script("window.scrollTo(0, 1000);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 2000);")
            time.sleep(2)

            # Get classroom name
            try:
                name_elem = driver.find_element(By.CSS_SELECTOR, '.YVvGBb.z3vRcc, .fqWr5c')
                classroom_announcements_cache['classroom_name'] = name_elem.text.strip()
            except:
                pass

            announcements = []

            # Find announcements using the data-stream-item-id attribute
            announcement_elements = driver.find_elements(By.CSS_SELECTOR, '[data-stream-item-id]')
            print(f"   Found {len(announcement_elements)} announcements")

            for elem in announcement_elements:
                try:
                    full_text = elem.text.strip()

                    if not full_text or len(full_text) < 20:
                        continue

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
                        # Get the main content area
                        content_elem = elem.find_element(By.CSS_SELECTOR, '.pco8Kc')
                        announcement_text = content_elem.text.strip()
                    except:
                        # Fallback: use full text
                        announcement_text = full_text

                    # Clean up the text - remove metadata but keep the actual content
                    lines_to_remove = [
                        'Add comment', 'class comments', 'More options', 'more_vert',
                        'Created', 'Post by', '(Edited', 'Edited'
                    ]
                    for removal in lines_to_remove:
                        announcement_text = announcement_text.replace(removal, '')

                    # Clean line by line
                    text_lines = announcement_text.split('\n')
                    cleaned_lines = []
                    skip_names = ['Emily Hall', 'Jan 8', 'Yesterday', 'Today', 'Jan 7', 'Jan 9', 'Jan 10']

                    for line in text_lines:
                        line = line.strip()
                        # Skip empty lines, very short lines, and author names
                        if line and len(line) > 3 and line not in skip_names:
                            # Don't skip if it's the actual content (longer than typical metadata)
                            if len(line) > 15 or not any(month in line for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']):
                                cleaned_lines.append(line)

                    announcement_text = '\n\n'.join(cleaned_lines).strip()

                    # Build materials list from extracted links
                    materials = []
                    for link in links:
                        materials.append({
                            'type': 'link',
                            'url': link['url'],
                            'title': link['title'] if len(link['title']) < 100 else 'View Link'
                        })

                    if announcement_text and len(announcement_text) > 15:
                        announcements.append({
                            'id': str(len(announcements)),
                            'text': announcement_text,
                            'date': date_text or 'Recently',
                            'materials': materials
                        })
                        print(f"   ✅ Added: {announcement_text[:60]}... ({len(materials)} links)")

                except Exception as e:
                    print(f"   ⚠️  Error parsing announcement: {e}")
                    continue

            driver.quit()

            classroom_announcements_cache['announcements'] = announcements
            classroom_announcements_cache['last_updated'] = datetime.now().isoformat()

            save_classroom_announcements_cache()

            print(f"✅ Scraped {len(announcements)} announcements from Google Classroom")

        except Exception as e:
            print(f"❌ Classroom scraping error: {str(e)}")
            if driver:
                driver.quit()

    def background_classroom_scraper():
        """Background thread that periodically scrapes classroom announcements."""
        while True:
            scrape_classroom_announcements()
            # Scrape every 10 minutes
            time.sleep(600)

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        actual_username = None
        for user in users.keys():
            if user.lower() == username.lower():
                actual_username = user
                break
        if actual_username and users[actual_username]['password'] == password:
            if users[actual_username]['banned']:
                session.permanent = True
                session['username'] = actual_username
                return redirect(url_for('banned'))
            # Make session permanent so it persists across browser restarts
            session.permanent = True
            session['username'] = actual_username

            # Check if password change is required
            if not users[actual_username].get('password_changed', False):
                return redirect(url_for('force_password_change'))

            # 🔹 NEW: Send login notification to admins/ambassadors
            login_time = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
            for admin_user in users:
                if users[admin_user]['role'] in ['admin', 'ambassador']:
                    if admin_user not in login_notifications:
                        login_notifications[admin_user] = []
                    login_notifications[admin_user].append({
                        'username': actual_username,
                        'timestamp': login_time
                    })
            save_json(LOGIN_NOTIFICATIONS_FILE, login_notifications)

            if users[actual_username]['role'] in ['admin', 'ambassador']:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/banned')
def banned():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    if username not in users or not users[username]['banned']:
        return redirect(url_for('index'))
    ban_reason = users[username]['ban_reason']
    return render_template('banned.html', reason=ban_reason)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/force_password_change', methods=['GET', 'POST'])
def force_password_change():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']

    # If already changed, redirect to main
    if users[username].get('password_changed', False):
        return redirect(url_for('index'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Validation
        if not new_password or not confirm_password:
            return render_template('change_password.html',
                error="Both fields are required")

        if len(new_password) < 2:
            return render_template('change_password.html',
                error="Password must be at least 2 characters")

        if new_password != confirm_password:
            return render_template('change_password.html',
                error="Passwords do not match")

        if new_password == users[username]['password']:
            return render_template('change_password.html',
                error="New password must be different from old password")

        # Update password
        users[username]['password'] = new_password
        users[username]['password_changed'] = True
        save_json(USERS_FILE, users)

        return render_template('change_password.html',
            success=True)

    return render_template('change_password.html')

@app.route('/')
@maintenance_check
@login_required
@password_change_required
def index():
    username = session['username']
    unread_count = get_unread_count(username)  # Only count private chat messages
    group_unread_count = get_total_group_unread_count(username)  # Track group messages separately
    lounge_unread_count = get_lounge_unread_count(username)
    sorted_games = sorted(games.items(), key=lambda x: (
        not x[1].get('free_for_all', True),
        x[1].get('price', 0),
        x[1]['name'].lower()
    ))
    sorted_games = dict(sorted_games)
    current_rank = users[username].get('rank')
    current_rank_index = -1
    if current_rank:
        for i, rank in enumerate(RANKS):
            if rank['id'] == current_rank:
                current_rank_index = i
                break

    # Get groups data for the Groups tab
    groups_data = []
    for group_id, group_data in groups.items():
        is_member = username == group_data['leader'] or username in group_data.get('members', [])
        unread = get_group_unread_count(username, group_id) if is_member else 0

        # Get last message preview
        last_message = None
        if group_id in group_messages and group_messages[group_id]:
            last_msg = group_messages[group_id][-1]
            if last_msg.get('type') == 'snap':
                preview = '📷 Snap'
            elif last_msg.get('type') == 'voice':
                preview = '🎤 Voice message'
            else:
                preview = last_msg.get('text', '')[:40] + ('...' if len(last_msg.get('text', '')) > 40 else '')
            last_message = {
                'preview': preview,
                'timestamp': last_msg['timestamp'],
                'from': last_msg['from']
            }

        groups_data.append({
            'id': group_id,
            'name': group_data['name'],
            'leader': group_data['leader'],
            'members': group_data.get('members', []),
            'image': group_data.get('image'),
            'is_member': is_member,
            'unread': unread,
            'last_message': last_message,
            'member_count': len(group_data.get('members', [])) + 1,
            'rank': group_data.get('rank', 0),
            'rank_display': GROUP_RANKS[group_data.get('rank', 0)]['display'],
            'bank': group_data.get('bank', 0)
        })

    # Sort by bank amount (highest first)
    groups_data.sort(key=lambda x: x['bank'], reverse=True)

    # Check if user already has a group they lead
    user_has_group = any(g['leader'] == username for g in groups.values())

    # Check if user should see Instagram connection prompt
    show_instagram_prompt = False
    if username in profiles:
        profile = profiles[username]
        # Show prompt if: setup_complete but no instagram_username and hasn't been shown before
        if (profile.get('setup_complete', False) and
            not profile.get('instagram_username') and
            not profile.get('instagram_prompt_shown', False)):
            show_instagram_prompt = True

    return render_template('main.html',
    games=sorted_games,
    announcements=announcements,
    users=users,
    purchases=purchases,
    user_role=users[username]['role'],
    unread_count=unread_count,
    group_unread_count=group_unread_count,
    lounge_unread_count=lounge_unread_count,
    RANKS=RANKS,
    STAFF_ROLES=STAFF_ROLES,
    current_rank_index=current_rank_index,
    session=session,
    profiles=profiles,
    groups=groups_data,
    user_has_group=user_has_group,
    user_tokens=users[username].get('tokens', 0),
    show_instagram_prompt=show_instagram_prompt
)

# In app.py, add this route:
@app.route('/api/reset_cookie', methods=['POST'])
@admin_required
def reset_cookie():
    global cookie_state
    cookie_state = {
        'last_reset': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
        'claimed': False,
        'claimed_by': None,
        'claimed_at': None,
        'fortune': random.choice(FORTUNES)
    }
    save_json(COOKIE_FILE, cookie_state)
    return jsonify({'success': True})

@app.route('/api/chat_notifications')
@login_required
def get_chat_notifications():
    """Get recent unread message notifications"""
    username = session['username']
    notifications = []

    for chat_key, msgs in messages.items():
        participants = chat_key.split('-')
        if username not in participants:
            continue

        other_user = participants[0] if participants[1] == username else participants[1]
        last_read = read_receipts.get(username, {}).get(chat_key, '')

        # Get most recent unread message from other person
        for msg in reversed(msgs):
            if (msg.get('to') == username and
                msg.get('from') == other_user and
                msg['timestamp'] > last_read):
                notifications.append({
                    'from': other_user,
                    'timestamp': msg['timestamp'],
                    'chat_key': chat_key,
                    'type': msg.get('type', 'message') if msg.get('type') == 'rps_invite' else 'message'
                })
                break  # Only get the most recent per chat

    # Sort by timestamp, most recent first
    notifications.sort(key=lambda x: x['timestamp'], reverse=True)

    return jsonify({'notifications': notifications[:5]})  # Limit to 5

@app.route('/api/group_notifications')
@login_required
def get_group_notifications():
    """Get recent unread group message notifications"""
    username = session['username']
    notifications = []

    for group_id, group_data in groups.items():
        # Check if user is a member
        if username != group_data['leader'] and username not in group_data.get('members', []):
            continue

        # Get last read timestamp for this group
        last_read = group_read_receipts.get(username, {}).get(group_id, '')

        # Get most recent unread message from others
        if group_id in group_messages:
            for msg in reversed(group_messages[group_id]):
                if (msg.get('from') != username and
                    msg.get('from') != 'system' and
                    msg['timestamp'] > last_read):
                    notifications.append({
                        'from': msg['from'],
                        'group_id': group_id,
                        'group_name': group_data['name'],
                        'timestamp': msg['timestamp'],
                        'message_type': msg.get('type', 'message')
                    })
                    break  # Only get the most recent per group

    # Sort by timestamp, most recent first
    notifications.sort(key=lambda x: x['timestamp'], reverse=True)

    return jsonify({'notifications': notifications[:5]})  # Limit to 5

@app.route('/api/paycheck_notifications')
@login_required
def get_paycheck_notifications():
    """Get paycheck notifications for the current user"""
    username = session['username']
    user_notifications = login_notifications.get(username, [])

    # Filter for paycheck notifications
    paycheck_notifs = [n for n in user_notifications if n.get('type') == 'paycheck_approved']

    return jsonify({
        'success': True,
        'notifications': paycheck_notifs
    })

@app.route('/api/clear_paycheck_notification/<int:index>', methods=['POST'])
@login_required
def clear_paycheck_notification(index):
    """Clear a specific paycheck notification"""
    username = session['username']

    if username in login_notifications:
        user_notifs = login_notifications[username]
        if 0 <= index < len(user_notifs):
            user_notifs.pop(index)
            save_json(LOGIN_NOTIFICATIONS_FILE, login_notifications)
            return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Notification not found'}), 404

@app.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    feedback_text = request.form.get('feedback')
    if feedback_text:
        feedback.append({
            'username': session['username'],
            'text': feedback_text,
            'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_json(FEEDBACK_FILE, feedback)
    return redirect(url_for('index'))

@app.route('/submit_website_request', methods=['POST'])
@login_required
def submit_website_request():
    request_text = request.form.get('website_request')
    if request_text:
        website_requests.append({
            'username': session['username'],
            'text': request_text,
            'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_json(WEBSITE_REQUESTS_FILE, website_requests)
    return redirect(url_for('proxy'))

@app.route('/casino')
@maintenance_check
@login_required
def casino():
    username = session['username']

    unread_count = get_unread_count(username)  # Only count private chat messages
    group_unread_count = get_total_group_unread_count(username)  # Track group messages separately
    lounge_unread_count = get_lounge_unread_count(username)
    return render_template('casino.html',
        user_tokens=users[username].get('tokens', 0),
        username=username,
        unread_count=unread_count,
        group_unread_count=group_unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role'],
        user_rank=users[username].get('rank'),
        RANKS=RANKS,
        STAFF_ROLES=STAFF_ROLES
    )

# ===============================================================
# Google Classroom Routes
# ===============================================================

@app.route('/classroom')
@maintenance_check
@login_required
def classroom():
    """Display Google Classroom announcements."""
    username = session['username']

    unread_count = get_unread_count(username)
    group_unread_count = get_total_group_unread_count(username)
    lounge_unread_count = get_lounge_unread_count(username)

    return render_template('classroom.html',
        username=username,
        unread_count=unread_count,
        group_unread_count=group_unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role'],
        user_rank=users[username].get('rank'),
        RANKS=RANKS,
        STAFF_ROLES=STAFF_ROLES
    )

@app.route('/api/classroom/status')
@login_required
def get_classroom_status():
    """Get classroom configuration status."""
    return jsonify({
        'configured': CLASSROOM_ID is not None,
        'logged_in': os.path.exists(CLASSROOM_COOKIES_FILE),
        'classroom_id': CLASSROOM_ID,
        'classroom_name': classroom_announcements_cache.get('classroom_name', 'Not configured')
    })

@app.route('/api/classroom/announcements')
@login_required
def get_classroom_announcements():
    """Get cached classroom announcements."""
    return jsonify(classroom_announcements_cache)

@app.route('/api/classroom/refresh', methods=['POST'])
@login_required
def manual_classroom_refresh():
    """Manually trigger a classroom announcements refresh."""
    scrape_classroom_announcements()
    return jsonify({'success': True, 'message': 'Refreshed successfully'})

@app.route('/profile', methods=['GET', 'POST'])
@maintenance_check
@login_required
def profile():
    username = session['username']
    unread_count = get_unread_count(username)  # Only count private chat messages
    group_unread_count = get_total_group_unread_count(username)  # Track group messages separately
    lounge_unread_count = get_lounge_unread_count(username)

    if username not in profiles:
        profiles[username] = {
            'setup_complete': False,
            'instagram_username': None,
            'profile_picture': None,
            'bio': '',
            'instagram_followers': None,
            'instagram_following': None,
            'instagram_full_name': None
        }

    profile_data = profiles[username]

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'purchase_setup':
            user_tokens = users[username].get('tokens', 0)
            if user_tokens < 100:
                return render_template('profile.html',
                    profile=profile_data,
                    user_tokens=user_tokens,
                    username=username,
                    unread_count=unread_count,
                    group_unread_count=group_unread_count,
                    lounge_unread_count=lounge_unread_count,
                    user_role=users[username]['role'],
                    error="Insufficient tokens. You need 100 tokens to set up your profile."
                )

            users[username]['tokens'] -= 100
            profiles[username]['setup_complete'] = True
            save_json(USERS_FILE, users)
            save_json(PROFILES_FILE, profiles)

            return redirect(url_for('profile'))

        elif action == 'update_profile' and profile_data['setup_complete']:
            instagram_username = request.form.get('instagram_username', '').strip()
            bio = request.form.get('bio', '').strip()

            # Update bio
            profiles[username]['bio'] = bio

            # Fetch Instagram data if username provided
            if instagram_username:
                try:
                    # Validate username format
                    if not re.match(r'^[a-zA-Z0-9._]+$', instagram_username):
                        raise ValueError("Invalid Instagram username format")

                    # Use Instaloader
                    L = instaloader.Instaloader(
                        download_pictures=False,
                        save_metadata=False,
                        compress_json=False
                    )

                    profile = instaloader.Profile.from_username(L.context, instagram_username)

                    # Get profile picture URL and download it
                    profile_pic_url = profile.profile_pic_url

                    # Download and convert to base64
                    import base64
                    response = requests.get(profile_pic_url, timeout=15)

                    if response.status_code == 200:
                        image_base64 = base64.b64encode(response.content).decode('utf-8')
                        profile_pic_data_uri = f"data:image/jpeg;base64,{image_base64}"
                    else:
                        profile_pic_data_uri = None

                    # Update profile with Instagram data
                    profiles[username]['instagram_username'] = instagram_username
                    profiles[username]['profile_picture'] = profile_pic_data_uri
                    profiles[username]['instagram_followers'] = profile.followers
                    profiles[username]['instagram_following'] = profile.followees
                    profiles[username]['instagram_full_name'] = profile.full_name

                except instaloader.exceptions.ProfileNotExistsException:
                    profiles[username]['instagram_username'] = instagram_username
                    profiles[username]['profile_picture'] = None
                    profiles[username]['instagram_followers'] = None
                    profiles[username]['instagram_following'] = None
                    profiles[username]['instagram_full_name'] = None
                    save_json(PROFILES_FILE, profiles)

                    return render_template('profile.html',
                        profile=profiles[username],
                        user_tokens=users[username].get('tokens', 0),
                        username=username,
                        unread_count=unread_count,
                        group_unread_count=group_unread_count,
                        lounge_unread_count=lounge_unread_count,
                        user_role=users[username]['role'],
                        error=f"Instagram username '@{instagram_username}' not found."
                    )

                except Exception as e:
                    profiles[username]['instagram_username'] = instagram_username
                    profiles[username]['profile_picture'] = None
                    profiles[username]['instagram_followers'] = None
                    profiles[username]['instagram_following'] = None
                    profiles[username]['instagram_full_name'] = None
                    save_json(PROFILES_FILE, profiles)

                    return render_template('profile.html',
                        profile=profiles[username],
                        user_tokens=users[username].get('tokens', 0),
                        username=username,
                        unread_count=unread_count,
                        group_unread_count=group_unread_count,
                        lounge_unread_count=lounge_unread_count,
                        user_role=users[username]['role'],
                        error=f"Failed to fetch Instagram data. Please try again."
                    )
            else:
                # Clear Instagram data if no username provided
                profiles[username]['instagram_username'] = None
                profiles[username]['profile_picture'] = None
                profiles[username]['instagram_followers'] = None
                profiles[username]['instagram_following'] = None
                profiles[username]['instagram_full_name'] = None

            save_json(PROFILES_FILE, profiles)

            return render_template('profile.html',
                profile=profiles[username],
                user_tokens=users[username].get('tokens', 0),
                username=username,
                unread_count=unread_count,
                group_unread_count=group_unread_count,
                lounge_unread_count=lounge_unread_count,
                user_role=users[username]['role'],
                success="Profile updated successfully!"
            )

    return render_template('profile.html',
        profile=profile_data,
        user_tokens=users[username].get('tokens', 0),
        username=username,
        unread_count=unread_count,
        group_unread_count=group_unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role']
    )

@app.route('/api/update_profile_instagram', methods=['POST'])
@login_required
def update_profile_instagram():
    """Update profile with Instagram data"""
    username = session['username']

    instagram_username = request.form.get('instagram_username', '').strip()
    bio = request.form.get('bio', '').strip()

    try:
        # Update bio
        profiles[username]['bio'] = bio

        if instagram_username:
            # Validate username format
            if not re.match(r'^[a-zA-Z0-9._]+$', instagram_username):
                return jsonify({'success': False, 'error': 'Invalid Instagram username format'})

            # Use Instaloader
            import base64
            L = instaloader.Instaloader(
                download_pictures=False,
                save_metadata=False,
                compress_json=False
            )

            profile = instaloader.Profile.from_username(L.context, instagram_username)

            # Get profile picture URL and download it
            profile_pic_url = profile.profile_pic_url
            response = requests.get(profile_pic_url, timeout=15)

            if response.status_code == 200:
                image_base64 = base64.b64encode(response.content).decode('utf-8')
                profile_pic_data_uri = f"data:image/jpeg;base64,{image_base64}"
            else:
                profile_pic_data_uri = None

            # Update profile with Instagram data
            profiles[username]['instagram_username'] = instagram_username
            profiles[username]['profile_picture'] = profile_pic_data_uri
            profiles[username]['instagram_followers'] = profile.followers
            profiles[username]['instagram_following'] = profile.followees
            profiles[username]['instagram_full_name'] = profile.full_name

        else:
            # Clear Instagram data if no username provided
            profiles[username]['instagram_username'] = None
            profiles[username]['profile_picture'] = None
            profiles[username]['instagram_followers'] = None
            profiles[username]['instagram_following'] = None
            profiles[username]['instagram_full_name'] = None

        save_json(PROFILES_FILE, profiles)
        return jsonify({'success': True})

    except instaloader.exceptions.ProfileNotExistsException:
        profiles[username]['instagram_username'] = instagram_username
        profiles[username]['profile_picture'] = None
        profiles[username]['instagram_followers'] = None
        profiles[username]['instagram_following'] = None
        profiles[username]['instagram_full_name'] = None
        save_json(PROFILES_FILE, profiles)
        return jsonify({'success': False, 'error': f"Instagram username '@{instagram_username}' not found."})

    except Exception as e:
        profiles[username]['instagram_username'] = instagram_username
        profiles[username]['profile_picture'] = None
        profiles[username]['instagram_followers'] = None
        profiles[username]['instagram_following'] = None
        profiles[username]['instagram_full_name'] = None
        save_json(PROFILES_FILE, profiles)
        return jsonify({'success': False, 'error': f"Failed to fetch Instagram data: {str(e)}"})


@app.route('/view_profile/<username>')
@maintenance_check
@login_required
def view_profile(username):
    if username not in users:
        return "User not found", 404

    current_user = session['username']
    unread_count = get_unread_count(current_user)
    group_unread_count = get_total_group_unread_count(current_user)
    unread_count += group_unread_count
    lounge_unread_count = get_lounge_unread_count(current_user)

    # Check if user has a profile set up
    if username not in profiles or not profiles[username].get('setup_complete', False):
        return "This user hasn't set up their profile yet", 404

    profile_data = profiles[username]
    user_rank = users[username].get('rank')
    user_tokens = users[username].get('tokens', 0)

    # Get user's most played games
    user_plays = plays.get(username, {})
    most_played = []
    if user_plays:
        sorted_plays = sorted(user_plays.items(), key=lambda x: x[1], reverse=True)[:5]
        for game_id, play_count in sorted_plays:
            if game_id in games:
                most_played.append({
                    'name': games[game_id]['name'],
                    'plays': play_count
                })

    return render_template('view_profile.html',
        profile=profile_data,
        viewed_username=username,
        user_rank=user_rank,
        user_tokens=user_tokens,
        most_played=most_played,
        RANKS=RANKS,
        unread_count=unread_count,
        group_unread_count=group_unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[current_user]['role']
    )

@app.route('/api/get_profile/<username>')
@login_required
def get_profile_data(username):
    user_rank = users.get(username, {}).get('rank')  # Purchased rank for avatar colors (not staff role)

    if username not in profiles:
        return jsonify({'has_profile': False, 'rank': user_rank})

    profile = profiles[username]
    if not profile.get('setup_complete', False):
        return jsonify({'has_profile': False, 'rank': user_rank})

    return jsonify({
        'has_profile': True,
        'profile_picture': profile.get('profile_picture'),  # Can be None if no Instagram connected
        'rank': user_rank  # Purchased rank for profile colors
    })


@app.route('/api/connect_instagram_prompt', methods=['POST'])
@maintenance_check
@login_required
def connect_instagram_prompt():
    username = session['username']
    action = request.form.get('action')

    # Ensure user has profile setup
    if username not in profiles or not profiles[username].get('setup_complete', False):
        return jsonify({'success': False, 'error': 'Profile not set up'}), 403

    # Handle dismiss action
    if action == 'dismiss':
        profiles[username]['instagram_prompt_shown'] = True
        save_json(PROFILES_FILE, profiles)
        return jsonify({'success': True})

    # Handle connect action
    if action == 'connect':
        instagram_username = request.form.get('instagram_username', '').strip()

        if not instagram_username:
            return jsonify({'success': False, 'error': 'Instagram username is required'})

        # Validate Instagram username format
        if not re.match(r'^[a-zA-Z0-9._]+$', instagram_username):
            return jsonify({'success': False, 'error': 'Invalid Instagram username format'})

        try:
            # Fetch Instagram data using Instaloader
            L = instaloader.Instaloader(
                download_pictures=False,
                save_metadata=False,
                compress_json=False
            )
            profile = instaloader.Profile.from_username(L.context, instagram_username)

            # Get profile picture
            profile_pic_url = profile.profile_pic_url
            response = requests.get(profile_pic_url, timeout=15)
            response.raise_for_status()

            # Convert image to base64
            image_base64 = base64.b64encode(response.content).decode('utf-8')
            profile_pic_data_uri = f"data:image/jpeg;base64,{image_base64}"

            # Update profile with Instagram data
            profiles[username]['instagram_username'] = instagram_username
            profiles[username]['profile_picture'] = profile_pic_data_uri
            profiles[username]['instagram_followers'] = profile.followers
            profiles[username]['instagram_following'] = profile.followees
            profiles[username]['instagram_full_name'] = profile.full_name
            profiles[username]['instagram_prompt_shown'] = True
            save_json(PROFILES_FILE, profiles)

            return jsonify({'success': True})

        except instaloader.exceptions.ProfileNotExistsException:
            profiles[username]['instagram_prompt_shown'] = True
            save_json(PROFILES_FILE, profiles)
            return jsonify({'success': False, 'error': f"Instagram username '@{instagram_username}' not found."})

        except Exception as e:
            profiles[username]['instagram_prompt_shown'] = True
            save_json(PROFILES_FILE, profiles)
            return jsonify({'success': False, 'error': f"Failed to fetch Instagram data: {str(e)}"})

    return jsonify({'success': False, 'error': 'Invalid action'}), 400


@app.route('/api/tower_recent_wins')
@login_required
def tower_recent_wins_api():
    return jsonify({'wins': tower_recent_wins})

@app.route('/api/coinflip', methods=['POST'])
@login_required
def coinflip():
    username = session['username']
    data = request.json
    bet_amount = data.get('amount')
    chosen_side = data.get('side')  # 'heads' or 'tails'

    # Validation
    if not bet_amount or not chosen_side:
        return jsonify({'error': 'Invalid request'}), 400

    try:
        bet_amount = int(bet_amount)
    except ValueError:
        return jsonify({'error': 'Invalid bet amount'}), 400

    if bet_amount < 2:
        return jsonify({'error': 'Minimum bet is 2 tokens'}), 400

    if chosen_side not in ['heads', 'tails']:
        return jsonify({'error': 'Invalid side choice'}), 400

    # Check if user has enough tokens
    user_tokens = users[username].get('tokens', 0)
    if user_tokens < bet_amount:
        return jsonify({'error': 'Insufficient tokens'}), 400

    # Flip the coin (50/50 chance)
    result = random.choice(['heads', 'tails'])
    won = result == chosen_side

    # Update balance
    if won:
        users[username]['tokens'] += bet_amount
        new_balance = users[username]['tokens']

        # Record win in top wins if it's big enough
        wins = load_coinflip_wins()
        new_win = {
            'username': username,
            'profit': bet_amount,
            'date': datetime.now().strftime('%Y-%m-%d')
        }

        # Add to wins list
        wins.append(new_win)

        # Sort by profit (descending) and keep top 3
        wins.sort(key=lambda x: x['profit'], reverse=True)
        wins = wins[:3]

        save_coinflip_wins(wins)
    else:
        users[username]['tokens'] -= bet_amount
        new_balance = users[username]['tokens']

    log_casino_game('coinflip', username, bet_amount, won, bet_amount if won else -bet_amount)
    log_transaction('creation' if won else 'destruction', bet_amount, username, 'casino_coinflip')
    save_json(USERS_FILE, users)

    return jsonify({
        'success': True,
        'result': result,
        'won': won,
        'amount': bet_amount,
        'new_balance': new_balance
    })

# Add this new route to get top wins
@app.route('/api/coinflip_top_wins')
@login_required
def coinflip_top_wins():
    wins = load_coinflip_wins()
    return jsonify({'wins': wins})


@app.route('/chat')
@maintenance_check
@login_required
def chat():
    current_user = session['username']
    user_list = [u for u in users.keys() if u != current_user]
    user_unread = {}
    user_last_message = {}
    for other_user in user_list:
        chat_key = get_chat_key(current_user, other_user)
        if chat_key in messages:
            unread = 0
            last_read = read_receipts.get(current_user, {}).get(chat_key, '')
            for msg in messages[chat_key]:
                # Only count messages TO you FROM the other person
                if (msg.get('to') == current_user and
                    msg.get('from') != current_user and
                    msg['timestamp'] > last_read):
                    unread += 1
            user_unread[other_user] = unread
            if messages[chat_key]:
                last_msg = messages[chat_key][-1]
                if last_msg.get('type') == 'snap':
                    preview = '📷 Snap'
                elif last_msg.get('type') == 'voice':
                    preview = '🎤 Voice message'
                elif last_msg.get('type') == 'token_gift':
                    preview = '🎁 Token gift'
                else:
                    preview = last_msg.get('text', '')[:50] + ('...' if len(last_msg.get('text', '')) > 50 else '')
                user_last_message[other_user] = {
                    'preview': preview,
                    'timestamp': last_msg['timestamp'],
                    'from_me': last_msg['from'] == current_user
                }
        else:
            user_unread[other_user] = 0
            user_last_message[other_user] = None

    # Get groups data for the Groups tab
    groups_data = []
    for group_id, group_data in groups.items():
        is_member = current_user == group_data['leader'] or current_user in group_data.get('members', [])
        unread = get_group_unread_count(current_user, group_id) if is_member else 0

        # Get last message preview
        last_message = None
        if group_id in group_messages and group_messages[group_id]:
            last_msg = group_messages[group_id][-1]
            if last_msg.get('type') == 'snap':
                preview = '📷 Snap'
            elif last_msg.get('type') == 'voice':
                preview = '🎤 Voice message'
            else:
                preview = last_msg.get('text', '')[:40] + ('...' if len(last_msg.get('text', '')) > 40 else '')
            last_message = {
                'preview': preview,
                'timestamp': last_msg['timestamp'],
                'from': last_msg['from']
            }

        groups_data.append({
            'id': group_id,
            'name': group_data['name'],
            'leader': group_data['leader'],
            'members': group_data.get('members', []),
            'image': group_data.get('image'),
            'is_member': is_member,
            'unread': unread,
            'last_message': last_message,
            'member_count': len(group_data.get('members', [])) + 1,
            'rank': group_data.get('rank', 0),
            'rank_display': GROUP_RANKS[group_data.get('rank', 0)]['display'],
            'bank': group_data.get('bank', 0)
        })

    # Sort by bank amount (highest first)
    groups_data.sort(key=lambda x: x['bank'], reverse=True)

    # Check if user already has a group they lead
    user_has_group = any(g['leader'] == current_user for g in groups.values())

    return render_template('chat_list.html',
        users=user_list,
        user_unread=user_unread,
        user_last_message=user_last_message,
        RANKS=RANKS,
        STAFF_ROLES=STAFF_ROLES,
        groups=groups_data,
        user_has_group=user_has_group,
        user_tokens=users[current_user].get('tokens', 0),
        profiles=profiles
    )
@app.route('/chat/<other_user>')
@login_required
def chat_conversation(other_user):
    if other_user not in users:
        return redirect(url_for('chat'))
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)
    if chat_key not in messages:
        messages[chat_key] = []

    # Get last read timestamp for NEW line
    last_read = read_receipts.get(current_user, {}).get(chat_key, '')

    # Get snap views for this chat
    chat_snap_views = snap_views.get(chat_key, {})

    return render_template('chat_conversation.html',
        other_user=other_user,
        messages=messages[chat_key],
        current_user=current_user,
        read_receipts=read_receipts,
        last_read_timestamp=last_read,
        users=users,
        session=session,
        STAFF_ROLES=STAFF_ROLES,
        RANKS=RANKS,
        profiles=profiles,
        snap_views=chat_snap_views
    )

@app.route('/chat/<other_user>/send', methods=['POST'])
@login_required
def send_message(other_user):
    if other_user not in users:
        return jsonify({'error': 'User not found'}), 404

    message_text = request.form.get('message')
    current_user = session['username']

    if message_text:
        chat_key = get_chat_key(current_user, other_user)
        if chat_key not in messages:
            messages[chat_key] = []

        new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

        reply_to_index = request.form.get('reply_to_index')
        reply_to = None
        if reply_to_index is not None and str(reply_to_index).strip() != '':
            try:
                reply_to = {
                    'index': int(reply_to_index),
                    'sender': request.form.get('reply_to_sender', ''),
                    'preview': request.form.get('reply_to_preview', ''),
                    'type': request.form.get('reply_to_type', 'text')
                }
            except ValueError:
                reply_to = None

        messages[chat_key].append({
            'from': current_user,
            'to': other_user,
            'text': message_text,
            'timestamp': new_timestamp,
            'read': False,
            'reply_to': reply_to
        })
        save_json(MESSAGES_FILE, messages)

        # ✅ CRITICAL FIX: Mark as read for BOTH sender and receiver to prevent false unreads
        if current_user not in read_receipts:
            read_receipts[current_user] = {}
        if other_user not in read_receipts:
            read_receipts[other_user] = {}

        # Mark as read for sender (you)
        read_receipts[current_user][chat_key] = new_timestamp

        # DO NOT mark as read for receiver - let them mark it themselves
        # But ensure they have an entry (can be empty or old timestamp)
        if chat_key not in read_receipts[other_user]:
            read_receipts[other_user][chat_key] = ""

        save_json(READ_RECEIPTS_FILE, read_receipts)

        # Emit WebSocket event to notify the other user in real-time
        new_message = {
            'from': current_user,
            'to': other_user,
            'text': message_text,
            'timestamp': new_timestamp,
            'read': False,
            'index': len(messages[chat_key]) - 1,
            'reply_to': reply_to
        }
        socketio.emit('new_chat_message', new_message, room=f'chat_{other_user}')

        return jsonify({'success': True})

@app.route('/chat/<other_user>/messages')
@login_required
def get_messages(other_user):
    if other_user not in users:
        return jsonify({'error': 'User not found'}), 404
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)
    if chat_key not in messages:
        messages[chat_key] = []

    # Performance optimization: Add pagination support
    limit = request.args.get('limit', 100, type=int)  # Default 100 messages
    since = request.args.get('since', '', type=str)  # Timestamp filter

    chat_messages = messages[chat_key]

    # Filter messages newer than 'since' timestamp if provided
    if since:
        chat_messages = [m for m in chat_messages if m.get('timestamp', '') > since]

    # Limit to last N messages
    chat_messages = chat_messages[-limit:]

    # Process snap messages using snap_views to determine state per user
    processed_messages = []
    base_index = len(messages[chat_key]) - len(chat_messages)  # Starting index for these messages

    for i, msg in enumerate(chat_messages):
        msg_copy = msg.copy()
        message_index = base_index + i

        # For snaps: check snap_views to determine opened/replayed state
        if msg.get('type') == 'snap':
            is_sender = msg.get('from') == current_user
            is_recipient = msg.get('to') == current_user

            # Check snap_views for this snap
            snap_data = {}
            if chat_key in snap_views and str(message_index) in snap_views[chat_key]:
                snap_data = snap_views[chat_key][str(message_index)]

            opened_by_list = snap_data.get('opened_by', [])
            replayed_by_list = snap_data.get('replayed_by', [])

            if is_recipient:
                # Recipient never sees it as opened (they're the one who opens it)
                msg_copy['opened'] = False
                msg_copy['replayed_by'] = None
                msg_copy['can_replay'] = False
            elif is_sender:
                # Sender sees if recipient has opened/replayed
                recipient = msg.get('to')
                msg_copy['opened'] = recipient in opened_by_list
                msg_copy['replayed_by'] = recipient if recipient in replayed_by_list else None
                msg_copy['can_replay'] = recipient not in replayed_by_list

        processed_messages.append(msg_copy)

    return jsonify({'messages': processed_messages})

@app.route('/chat/<other_user>/read_status')
@login_required
def get_read_status(other_user):
    if other_user not in users:
        return jsonify({'error': 'User not found'}), 404
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)
    last_read = read_receipts.get(other_user, {}).get(chat_key, '')
    return jsonify({'last_read': last_read})

@app.route('/chat/<other_user>/typing', methods=['POST'])
@login_required
def send_typing(other_user):
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)
    typing_status[chat_key] = {
        'user': current_user,
        'timestamp': datetime.now().timestamp()
    }
    return jsonify({'success': True})

@app.route('/chat/<other_user>/is_typing')
@login_required
def is_typing(other_user):
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)
    if chat_key in typing_status:
        status = typing_status[chat_key]
        if status['user'] == other_user and (datetime.now().timestamp() - status['timestamp']) < 3:
            return jsonify({'is_typing': True})
    return jsonify({'is_typing': False})

@app.route('/chat/<other_user>/mark_read', methods=['POST'])
@login_required
def mark_read(other_user):
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)

    if chat_key not in messages or not messages[chat_key]:
        return jsonify({'success': True})

    # Find the VERY LAST message in the chat (regardless of who sent it)
    last_message = messages[chat_key][-1]
    new_timestamp = last_message['timestamp']

    if current_user not in read_receipts:
        read_receipts[current_user] = {}

    # ✅ CRITICAL: Only update if the new timestamp is NEWER than existing
    existing_timestamp = read_receipts[current_user].get(chat_key, '')

    if new_timestamp > existing_timestamp or not existing_timestamp:
        read_receipts[current_user][chat_key] = new_timestamp
        save_json(READ_RECEIPTS_FILE, read_receipts)

    return jsonify({'success': True})

@app.route('/chat/<other_user>/send_snap', methods=['POST'])
@login_required
def send_snap(other_user):
    if other_user not in users:
        return jsonify({'error': 'User not found'}), 404

    photo_data = request.json.get('photo')
    current_user = session['username']

    if photo_data:
        chat_key = get_chat_key(current_user, other_user)
        if chat_key not in messages:
            messages[chat_key] = []

        new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

        snap_message = {
            'from': current_user,
            'to': other_user,
            'type': 'snap',
            'photo': photo_data,
            'opened': False,
            'timestamp': new_timestamp,
            'read': False
        }
        messages[chat_key].append(snap_message)
        save_json(MESSAGES_FILE, messages)

        # ✅ Mark as read for yourself after sending
        if current_user not in read_receipts:
            read_receipts[current_user] = {}
        read_receipts[current_user][chat_key] = new_timestamp
        save_json(READ_RECEIPTS_FILE, read_receipts)

        # Broadcast new snap to recipient via WebSocket
        message_index = len(messages[chat_key]) - 1
        socketio.emit('new_snap', {
            'message': snap_message,
            'message_index': message_index
        }, room=f'chat_{other_user}')

        return jsonify({'success': True})

@app.route('/chat/<other_user>/send_voice', methods=['POST'])
@login_required
def send_voice(other_user):
    if other_user not in users:
        return jsonify({'error': 'User not found'}), 404

    audio_data = request.json.get('audio')
    duration = request.json.get('duration', 0)
    current_user = session['username']

    if audio_data:
        chat_key = get_chat_key(current_user, other_user)
        if chat_key not in messages:
            messages[chat_key] = []

        new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

        voice_message = {
            'from': current_user,
            'to': other_user,
            'type': 'voice',
            'audio': audio_data,
            'duration': duration,
            'timestamp': new_timestamp,
            'read': False
        }

        messages[chat_key].append(voice_message)
        save_json(MESSAGES_FILE, messages)

        # ✅ Mark as read for yourself after sending
        if current_user not in read_receipts:
            read_receipts[current_user] = {}
        read_receipts[current_user][chat_key] = new_timestamp
        save_json(READ_RECEIPTS_FILE, read_receipts)

        # Broadcast new voice message to recipient via WebSocket
        message_index = len(messages[chat_key]) - 1
        socketio.emit('new_voice', {
            'message': voice_message,
            'message_index': message_index
        }, room=f'chat_{other_user}')

        return jsonify({'success': True})

@app.route('/chat/<other_user>/open_snap/<int:message_index>', methods=['POST'])
@login_required
def open_snap(other_user, message_index):
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)
    if chat_key in messages and message_index < len(messages[chat_key]):
        msg = messages[chat_key][message_index]
        if msg.get('type') == 'snap' and msg.get('to') == current_user:
            # Track who opened this snap in snap_views
            if chat_key not in snap_views:
                snap_views[chat_key] = {}
            if str(message_index) not in snap_views[chat_key]:
                snap_views[chat_key][str(message_index)] = {'opened_by': [], 'replayed_by': []}

            if current_user not in snap_views[chat_key][str(message_index)]['opened_by']:
                snap_views[chat_key][str(message_index)]['opened_by'].append(current_user)

            save_json(SNAP_VIEWS_FILE, snap_views)

            # Emit WebSocket event ONLY to sender to show snap was opened
            snap_sender = msg.get('from')
            socketio.emit('snap_opened', {
                'message_index': message_index,
                'opened_by': current_user,
                'chat_key': chat_key
            }, room=f'chat_{snap_sender}')

            return jsonify({'success': True, 'photo': msg['photo']})
    return jsonify({'error': 'Snap not found'}), 404

@app.route('/chat/<other_user>/replay_snap/<int:message_index>', methods=['POST'])
@login_required
def replay_snap(other_user, message_index):
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)

    if chat_key in messages and message_index < len(messages[chat_key]):
        msg = messages[chat_key][message_index]

        # Validate it's a snap, sent to current user, and not their own snap
        if (msg.get('type') == 'snap' and
            msg.get('to') == current_user and
            msg.get('from') != current_user):

            # Check snap_views to see if already replayed
            if chat_key in snap_views and str(message_index) in snap_views[chat_key]:
                if current_user in snap_views[chat_key][str(message_index)].get('replayed_by', []):
                    return jsonify({'error': 'Snap already replayed'}), 400

            # Track replay in snap_views
            if chat_key not in snap_views:
                snap_views[chat_key] = {}
            if str(message_index) not in snap_views[chat_key]:
                snap_views[chat_key][str(message_index)] = {'opened_by': [], 'replayed_by': []}

            snap_views[chat_key][str(message_index)]['replayed_by'].append(current_user)
            save_json(SNAP_VIEWS_FILE, snap_views)

            # Emit WebSocket event to BOTH users
            snap_sender = msg.get('from')
            socketio.emit('snap_replayed', {
                'message_index': message_index,
                'replayed_by': current_user,
                'chat_key': chat_key
            }, room=f'chat_{snap_sender}')
            socketio.emit('snap_replayed', {
                'message_index': message_index,
                'replayed_by': current_user,
                'chat_key': chat_key
            }, room=f'chat_{current_user}')

            return jsonify({'success': True, 'photo': msg['photo']})

    return jsonify({'error': 'Snap not found'}), 404

@app.route('/chat/<other_user>/save_snap/<int:message_index>', methods=['POST'])
@login_required
def save_snap(other_user, message_index):
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)

    if chat_key in messages and message_index < len(messages[chat_key]):
        msg = messages[chat_key][message_index]

        if msg.get('type') == 'snap':
            # Initialize snap_views structure
            if chat_key not in snap_views:
                snap_views[chat_key] = {}
            if str(message_index) not in snap_views[chat_key]:
                snap_views[chat_key][str(message_index)] = {'opened_by': [], 'replayed_by': [], 'saved_by': []}

            saved_by_list = snap_views[chat_key][str(message_index)].get('saved_by', [])

            # Toggle save/unsave
            if current_user in saved_by_list:
                # Unsave
                saved_by_list.remove(current_user)
                action = 'unsaved'
            else:
                # Save
                saved_by_list.append(current_user)
                action = 'saved'

            snap_views[chat_key][str(message_index)]['saved_by'] = saved_by_list
            save_json(SNAP_VIEWS_FILE, snap_views)

            # Emit WebSocket event to BOTH users
            snap_sender = msg.get('from')
            snap_recipient = msg.get('to')

            socketio.emit('snap_saved', {
                'message_index': message_index,
                'saved_by': current_user,
                'action': action,
                'saved_by_list': saved_by_list,
                'snap_photo': msg['photo']
            }, room=f'chat_{snap_sender}')
            socketio.emit('snap_saved', {
                'message_index': message_index,
                'saved_by': current_user,
                'action': action,
                'saved_by_list': saved_by_list,
                'snap_photo': msg['photo']
            }, room=f'chat_{snap_recipient}')

            return jsonify({
                'success': True,
                'action': action,
                'saved_by_list': saved_by_list
            })

    return jsonify({'error': 'Snap not found'}), 404

@app.route('/chat/<other_user>/send_tokens', methods=['POST'])
@login_required
def send_tokens(other_user):
    if other_user not in users:
        return jsonify({'error': 'User not found'}), 404

    current_user = session['username']
    data = request.json
    amount = data.get('amount')

    if not amount or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    if users[current_user].get('tokens', 0) < amount:
        return jsonify({'error': 'Insufficient balance'}), 400

    users[current_user]['tokens'] -= amount
    users[other_user]['tokens'] = users[other_user].get('tokens', 0) + amount
    save_json(USERS_FILE, users)
    log_transaction('transfer', amount, current_user, 'gift_sent', f'To: {other_user}')
    log_transaction('transfer', amount, other_user, 'gift_received', f'From: {current_user}')

    chat_key = get_chat_key(current_user, other_user)
    if chat_key not in messages:
        messages[chat_key] = []

    new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

    token_gift_message = {
        'from': 'system',
        'to': other_user,
        'type': 'token_gift',
        'text': f'{current_user} sent {amount} tokens to {other_user}!️',
        'timestamp': new_timestamp,
        'read': False
    }
    messages[chat_key].append(token_gift_message)
    save_json(MESSAGES_FILE, messages)

    # Emit WebSocket event to notify both users in real-time
    message_data = token_gift_message.copy()
    message_data['index'] = len(messages[chat_key]) - 1
    socketio.emit('new_chat_message', message_data, room=f'chat_{other_user}')
    socketio.emit('new_chat_message', message_data, room=f'chat_{current_user}')

    return jsonify({'success': True, 'new_balance': users[current_user]['tokens']})

@app.route('/api/user_balance')
@login_required
def get_user_balance():
    username = session['username']
    return jsonify({'balance': users[username].get('tokens', 0)})

@app.route('/api/heartbeat', methods=['POST'])
@login_required
def heartbeat():
    username = session['username']
    user_activity[username] = get_ny_time().timestamp()
    save_json(USER_ACTIVITY_FILE, user_activity)
    return jsonify({'success': True})

@app.route('/api/online_users')
@login_required
def get_online_users():
    current_time = get_ny_time().timestamp()
    online_threshold = 30
    online_users = []
    offline_users = {}
    for username, last_seen in user_activity.items():
        time_diff = current_time - last_seen
        if time_diff < online_threshold:
            online_users.append(username)
        else:
            hours_ago = int(time_diff / 3600)
            if hours_ago < 1:
                minutes_ago = int(time_diff / 60)
                offline_users[username] = f"{minutes_ago}m ago" if minutes_ago > 0 else "Just now"
            elif hours_ago < 24:
                offline_users[username] = f"{hours_ago}h ago"
            else:
                days_ago = int(hours_ago / 24)
                offline_users[username] = f"{days_ago}d ago"
    return jsonify({
        'online_users': online_users,
        'offline_users': offline_users
    })

@app.route('/api/users_with_ranks')
@login_required
def get_users_with_ranks():
    global user_list_cache, user_list_cache_time
    current_user = session['username']
    current_time = get_ny_time().timestamp()

    # Performance optimization: Cache for 5 seconds per user to reduce load
    cache_key = f"{current_user}_cache"
    if (current_time - user_list_cache_time < 5 and
        user_list_cache and
        user_list_cache.get('_cached_for') == current_user):
        return jsonify(user_list_cache)

    online_threshold = 30
    users_by_rank = {}
    pr_director_user = None

    for username in users.keys():
        if username == current_user:
            continue
        user_rank = users[username].get('rank')
        rank_id = user_rank if user_rank else 'no_rank'
        if rank_id not in users_by_rank:
            users_by_rank[rank_id] = []

        is_online = False
        last_seen_text = ''
        if username in user_activity:
            time_diff = current_time - user_activity[username]
            if time_diff < online_threshold:
                is_online = True
            else:
                hours_ago = int(time_diff / 3600)
                if hours_ago < 1:
                    minutes_ago = int(time_diff / 60)
                    last_seen_text = f"{minutes_ago}m ago" if minutes_ago > 0 else "Just now"
                elif hours_ago < 24:
                    last_seen_text = f"{hours_ago}h ago"
                else:
                    days_ago = int(hours_ago / 24)
                    last_seen_text = f"{days_ago}d ago"

        chat_key = get_chat_key(current_user, username)
        unread = 0
        last_message = None
        last_message_timestamp = None

        if chat_key in messages and messages[chat_key]:
            last_read = read_receipts.get(current_user, {}).get(chat_key, '')
            for msg in messages[chat_key]:
                if msg['to'] == current_user and msg['timestamp'] > last_read:
                    unread += 1

            last_msg = messages[chat_key][-1]
            last_message_timestamp = last_msg['timestamp']

            # Determine message type and snap state
            msg_type = last_msg.get('type', 'text')
            snap_opened = False
            text_opened = False
            gift_opened = False

            if msg_type == 'snap':
                preview = '📷 Snap'
                # Check if snap was opened by checking snap_views
                message_index = len(messages[chat_key]) - 1
                if chat_key in snap_views and str(message_index) in snap_views[chat_key]:
                    snap_data = snap_views[chat_key][str(message_index)]
                    # Determine if snap is "opened" from current user's perspective
                    if last_msg['from'] == current_user:
                        # I sent it - check if recipient opened it
                        recipient = last_msg['to']
                        snap_opened = recipient in snap_data.get('opened_by', [])
                    else:
                        # I received it - check if I opened it
                        snap_opened = current_user in snap_data.get('opened_by', [])
            elif msg_type == 'voice':
                preview = '🎤 Voice message'
            elif msg_type == 'token_gift':
                preview = '🎁 Token gift'
                # Check if gift was read (opened)
                if last_msg['from'] == current_user:
                    # I sent it - check if recipient read it
                    recipient = last_msg['to']
                    recipient_last_read = read_receipts.get(recipient, {}).get(chat_key, '')
                    gift_opened = recipient_last_read and last_msg['timestamp'] <= recipient_last_read
                else:
                    # I received it - check if I read it
                    gift_opened = last_read and last_msg['timestamp'] <= last_read
            else:
                preview = last_msg.get('text', '')[:50] + ('...' if len(last_msg.get('text', '')) > 50 else '')
                # Check if text message was read
                if last_msg['from'] == current_user:
                    # I sent it - check if recipient read it
                    recipient = last_msg['to']
                    recipient_last_read = read_receipts.get(recipient, {}).get(chat_key, '')
                    text_opened = recipient_last_read and last_msg['timestamp'] <= recipient_last_read
                else:
                    # I received it - check if I read it
                    text_opened = last_read and last_msg['timestamp'] <= last_read

            last_message = {
                'preview': preview,
                'timestamp': last_msg['timestamp'],
                'from_me': last_msg['from'] == current_user,
                'type': msg_type,
                'snap_opened': snap_opened,
                'text_opened': text_opened,
                'gift_opened': gift_opened
            }

        # Get Instagram full name if profile exists
        instagram_name = None
        profile_picture = None
        if username in profiles and profiles[username].get('setup_complete', False):
            instagram_name = profiles[username].get('instagram_full_name')
            profile_picture = profiles[username].get('profile_picture')

        users_by_rank[rank_id].append({
            'username': username,
            'instagram_name': instagram_name,
            'profile_picture': profile_picture,
            'is_online': is_online,
            'last_seen': last_seen_text,
            'unread': unread,
            'last_message': last_message,
            'last_message_timestamp': last_message_timestamp,
            'has_glow': users[username].get('glow_effect', {}).get('enabled', False)
        })

        if users[username].get('role') == 'pr_director':
            pr_director_user = {**users_by_rank[rank_id][-1], 'rank_id': rank_id}

    # Get current user's profile data for header
    current_user_profile = None
    current_user_rank = None
    if current_user in profiles:
        profile_pic = profiles[current_user].get('profile_picture')
        # Only set profile picture if it's not None/empty
        if profile_pic:
            current_user_profile = profile_pic
    if current_user in users:
        current_user_rank = users[current_user].get('rank')

    # Update cache with user identifier to prevent cross-user cache pollution
    user_list_cache = {
        'users_by_rank': users_by_rank,
        'current_user_data': {
            'profile_picture': current_user_profile,
            'rank': current_user_rank
        },
        'pr_director': pr_director_user,
        '_cached_for': current_user
    }
    user_list_cache_time = current_time

    return jsonify(user_list_cache)

@app.route('/api/chat_list_data')
@login_required
def get_chat_list_data():
    current_user = session['username']
    current_time = get_ny_time().timestamp()
    online_threshold = 30
    user_list = [u for u in users.keys() if u != current_user]
    chat_data = []
    for other_user in user_list:
        chat_key = get_chat_key(current_user, other_user)
        is_online = False
        last_seen_text = ''
        if other_user in user_activity:
            time_diff = current_time - user_activity[other_user]
            if time_diff < online_threshold:
                is_online = True
            else:
                hours_ago = int(time_diff / 3600)
                if hours_ago < 1:
                    minutes_ago = int(time_diff / 60)
                    last_seen_text = f"{minutes_ago}m ago" if minutes_ago > 0 else "Just now"
                elif hours_ago < 24:
                    last_seen_text = f"{hours_ago}h ago"
                else:
                    days_ago = int(hours_ago / 24)
                    last_seen_text = f"{days_ago}d ago"
        unread = 0
        last_message = None
        if chat_key in messages and messages[chat_key]:
            last_read = read_receipts.get(current_user, {}).get(chat_key, '')
            for msg in messages[chat_key]:
                if msg['to'] == current_user and msg['timestamp'] > last_read:
                    unread += 1

            last_msg = messages[chat_key][-1]
            if last_msg.get('type') == 'snap':
                preview = '📷 Snap'
            elif last_msg.get('type') == 'voice':
                preview = '🎤 Voice message'
            elif last_msg.get('type') == 'token_gift':
                preview = '🎁 Token gift'
            else:
                preview = last_msg.get('text', '')[:50] + ('...' if len(last_msg.get('text', '')) > 50 else '')

            last_message = {
                'preview': preview,
                'timestamp': last_msg['timestamp'],
                'from_me': last_msg['from'] == current_user
            }
        chat_data.append({
            'username': other_user,
            'is_online': is_online,
            'last_seen': last_seen_text,
            'unread': unread,
            'last_message': last_message
        })
    return jsonify({'chats': chat_data})

@app.route('/lounge')
@maintenance_check
@login_required
def lounge():
    username = session['username']

    # ✅ MARK AS READ IMMEDIATELY ON PAGE LOAD (server-side)
    if lounge_messages:
        # Get last message from others
        last_msg_from_others = None
        for msg in reversed(lounge_messages):
            if msg.get('from') != username:
                last_msg_from_others = msg
                break

        if last_msg_from_others:
            lounge_read_receipts[username] = last_msg_from_others['timestamp']
            save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

    return render_template('lounge.html',
        messages=lounge_messages,
        current_user=username,
        user_role=users[username]['role'],
        reactions=lounge_reactions,
        STAFF_ROLES=STAFF_ROLES,
        RANKS=RANKS,
        profiles=profiles,
        users=users
    )

@app.route('/lounge/mark_read', methods=['POST'])
@login_required
def mark_lounge_read():
    username = session['username']

    # ✅ Mark ALL messages as read - use the VERY LAST message timestamp
    if lounge_messages:
        # Get the absolute last message (regardless of who sent it)
        last_message = lounge_messages[-1]
        lounge_read_receipts[username] = last_message['timestamp']
        save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

    return jsonify({'success': True})

@app.route('/lounge/send', methods=['POST'])
@login_required
def send_lounge_message():
    message_text = request.form.get('message')
    reply_to_index = request.form.get('reply_to')  # Support for slide-to-reply
    current_user = session['username']

    if message_text:
        # Handle /clear command for admins/master moderators via HTTP endpoint
        if message_text.strip().lower() == '/clear':
            user_role = users[current_user].get('role', 'user')
            if user_role in ['admin', 'master_moderator']:
                lounge_messages.clear()
                lounge_reactions.clear()
                lounge_read_receipts.clear()
                save_json(LOUNGE_FILE, lounge_messages)
                save_json(LOUNGE_REACTIONS_FILE, lounge_reactions)
                save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)
                socketio.emit('lounge_cleared', room='lounge')
                return jsonify({'success': True, 'cleared': True})
            else:
                return jsonify({'error': 'Unauthorized to clear lounge'}), 403

        new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        display_time = get_ny_time().strftime('%I:%M %p')

        message_obj = {
            'from': current_user,
            'message': message_text,
            'timestamp': new_timestamp,
            'display_time': display_time,
            'type': 'text'
        }

        # Add reply reference if present
        if reply_to_index is not None:
            message_obj['reply_to'] = int(reply_to_index)

        print(f"[LOUNGE DEBUG] Before append - Total messages: {len(lounge_messages)}")
        print(f"[LOUNGE DEBUG] LOUNGE_FILE path: {LOUNGE_FILE}")
        print(f"[LOUNGE DEBUG] Message to add: {message_obj}")

        lounge_messages.append(message_obj)

        print(f"[LOUNGE DEBUG] After append - Total messages: {len(lounge_messages)}")
        print(f"[LOUNGE DEBUG] Last 3 messages: {lounge_messages[-3:] if len(lounge_messages) >= 3 else lounge_messages}")

        save_json(LOUNGE_FILE, lounge_messages)

        print(f"[LOUNGE DEBUG] File saved successfully to {LOUNGE_FILE}")

        # Verify file was written
        if os.path.exists(LOUNGE_FILE):
            file_size = os.path.getsize(LOUNGE_FILE)
            print(f"[LOUNGE DEBUG] File exists! Size: {file_size} bytes")
        else:
            print(f"[LOUNGE DEBUG] WARNING: File does not exist after save!")

        # ✅ CRITICAL: Mark lounge as read for yourself after sending
        lounge_read_receipts[current_user] = new_timestamp
        save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

        return jsonify({'success': True})

    return jsonify({'error': 'No message provided'}), 400

@app.route('/lounge/messages')
@login_required
def get_lounge_messages():
    # ✅ DO NOT mark as read when polling - only when user explicitly marks

    limit = request.args.get('limit', default=10, type=int)
    before = request.args.get('before', default=None, type=int)
    limit = max(1, min(limit, 100))  # clamp to sane range
    total_messages = len(lounge_messages)

    end_index = total_messages if before is None else min(before, total_messages)
    start_index = max(0, end_index - limit)
    sliced_messages = lounge_messages[start_index:end_index]

    staff_tags = {}
    messages_payload = []
    for offset, msg in enumerate(sliced_messages):
        global_index = start_index + offset
        message_copy = msg.copy()
        message_copy['index'] = global_index
        message_copy['reactions'] = lounge_reactions.get(str(global_index), {})
        messages_payload.append(message_copy)
        sender = msg.get('from')
        if sender and sender not in staff_tags:
            staff_tags[sender] = get_lounge_staff_tag(sender)

    return jsonify({
        'messages': messages_payload,
        'user_role': users[session['username']]['role'],
        'staff_tags': staff_tags,
        'has_more': start_index > 0,
        'start_index': start_index,
        'total': total_messages
    })

@app.route('/lounge/react/<int:message_index>', methods=['POST'])
@login_required
def react_to_lounge_message(message_index):
    emoji = request.json.get('emoji')
    username = session['username']
    if message_index >= len(lounge_messages):
        return jsonify({'error': 'Message not found'}), 404
    msg_key = str(message_index)
    if msg_key not in lounge_reactions:
        lounge_reactions[msg_key] = {}
    if emoji not in lounge_reactions[msg_key]:
        lounge_reactions[msg_key][emoji] = []
    if username in lounge_reactions[msg_key][emoji]:
        lounge_reactions[msg_key][emoji].remove(username)
        if not lounge_reactions[msg_key][emoji]:
            del lounge_reactions[msg_key][emoji]
    else:
        lounge_reactions[msg_key][emoji].append(username)
    save_json(LOUNGE_REACTIONS_FILE, lounge_reactions)

    return jsonify({'success': True, 'reactions': lounge_reactions.get(msg_key, {})})

def _delete_lounge_message_at_index(message_index):
    """Shared helper to delete a lounge message and keep reaction indexes in sync."""
    global lounge_reactions

    if message_index < 0 or message_index >= len(lounge_messages):
        return None, 'Message not found'

    deleted_message = lounge_messages.pop(message_index)
    save_json(LOUNGE_FILE, lounge_messages)

    new_reactions = {}
    for key, reactions in lounge_reactions.items():
        idx = int(key)
        if idx < message_index:
            new_reactions[key] = reactions
        elif idx > message_index:
            new_reactions[str(idx - 1)] = reactions
    lounge_reactions = new_reactions
    save_json(LOUNGE_REACTIONS_FILE, lounge_reactions)

    return deleted_message, None

@app.route('/lounge/delete/<int:message_index>', methods=['POST'])
@panel_access_required
def delete_lounge_message_panel(message_index):
    username = session['username']
    if not has_permission(username, 'delete_lounge_messages'):
        return jsonify({'error': 'Unauthorized'}), 403

    _, error = _delete_lounge_message_at_index(message_index)
    if error:
        return jsonify({'error': error}), 404

    return jsonify({'success': True})

@app.route('/lounge/send_snap', methods=['POST'])
@login_required
def send_lounge_snap():
    photo_data = request.json.get('photo')
    current_user = session['username']

    if photo_data:
        new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

        snap_message = {
            'from': current_user,
            'type': 'snap',
            'photo': photo_data,
            'opened_by': [],
            'timestamp': new_timestamp
        }

        lounge_messages.append(snap_message)
        save_json(LOUNGE_FILE, lounge_messages)

        # ✅ CRITICAL: Mark lounge as read for yourself after sending snap
        lounge_read_receipts[current_user] = new_timestamp
        save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

        # Broadcast snap via WebSocket if user is in lounge
        if current_user in lounge_users:
            profile = profiles.get(current_user, {})
            profile_picture = profile.get('profile_picture') if profile.get('setup_complete') else None
            staff_tag = get_lounge_staff_tag(current_user)
            broadcast_message = snap_message.copy()
            broadcast_message['index'] = len(lounge_messages) - 1

            socketio.emit('new_lounge_message', {
                'message': broadcast_message,
                'profile_picture': profile_picture,
                'user_rank': staff_tag,
                'staff_tag': staff_tag
            }, room='lounge')

        return jsonify({'success': True})

    return jsonify({'error': 'No photo provided'}), 400

@app.route('/lounge/send_voice', methods=['POST'])
@login_required
def send_lounge_voice():
    audio_data = request.json.get('audio')
    duration = request.json.get('duration', 0)
    current_user = session['username']

    if audio_data:
        new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        display_time = get_ny_time().strftime('%I:%M %p')

        voice_message = {
            'from': current_user,
            'type': 'voice',
            'audio': audio_data,
            'duration': duration,
            'timestamp': new_timestamp,
            'display_time': display_time
        }

        lounge_messages.append(voice_message)
        save_json(LOUNGE_FILE, lounge_messages)

        # Mark lounge as read for yourself after sending voice
        lounge_read_receipts[current_user] = new_timestamp
        save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

        # Broadcast voice message via WebSocket if user is in lounge
        if current_user in lounge_users:
            profile = profiles.get(current_user, {})
            profile_picture = profile.get('profile_picture') if profile.get('setup_complete') else None
            staff_tag = get_lounge_staff_tag(current_user)
            broadcast_message = voice_message.copy()
            broadcast_message['index'] = len(lounge_messages) - 1

            socketio.emit('new_lounge_message', {
                'message': broadcast_message,
                'profile_picture': profile_picture,
                'user_rank': staff_tag,
                'staff_tag': staff_tag
            }, room='lounge')

        return jsonify({'success': True})

    return jsonify({'error': 'No audio provided'}), 400

@app.route('/lounge/open_snap/<int:message_index>', methods=['POST'])
@login_required
def open_lounge_snap(message_index):
    username = session['username']
    if message_index >= len(lounge_messages):
        return jsonify({'error': 'Snap not found'}), 404
    msg = lounge_messages[message_index]
    if msg.get('type') != 'snap':
        return jsonify({'error': 'Not a snap'}), 400
    if username in msg.get('opened_by', []):
        return jsonify({'error': 'Already opened'}), 400
    if 'opened_by' not in msg:
        msg['opened_by'] = []
    msg['opened_by'].append(username)
    save_json(LOUNGE_FILE, lounge_messages)
    return jsonify({
        'success': True,
        'photo': msg['photo'],
        'opened_count': len(msg['opened_by'])
    })

@app.route('/api/clear_login_notifications', methods=['POST'])
@panel_access_required
def clear_login_notifications():
    username = session['username']
    login_notifications[username] = []  # Clear the list instead of deleting the key
    save_json(LOGIN_NOTIFICATIONS_FILE, login_notifications)
    return jsonify({'success': True})

@app.route('/proxy')
@maintenance_check
@login_required
def proxy():
    username = session['username']
    unread_count = get_unread_count(username)  # Only count private chat messages
    group_unread_count = get_total_group_unread_count(username)  # Track group messages separately
    lounge_unread_count = get_lounge_unread_count(username)
    return render_template('proxy.html',
        user_tokens=users[username].get('tokens', 0),
        username=username,
        unread_count=unread_count,
        group_unread_count=group_unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role'],
        site_access=site_access
    )

@app.route('/transfer')
@app.route('/transfer-saves')
@maintenance_check
@login_required
def transfer():
    if request.path == '/transfer-saves':
        return redirect(url_for('transfer'))
    return render_template('transfer_import.html')

@app.route('/proxy_test')
def proxy_test():
    return redirect('https://bg.i-creativelearner.com/*/@/hvtrs8%2F-wuw%2Ctkkvoi.aoo%2Fdopymu')

@app.route('/iframe')
@maintenance_check
@login_required
def iframe_viewer():
    """Simple iframe viewer - paste any URL and view it in an iframe"""
    username = session['username']
    return render_template('iframe.html', username=username)


@app.route('/test')
@maintenance_check
@login_required
def test_iframe():
    test_url = "https://bg.i-creativelearner.com/*/@/hvtrs8%2F-wuw%2Chkgjsregdknvepngt%2Ccmm-tmons-sregd%2Ftgsv%2Faoopcrg%3Fwto_qowrae%3Fbkne%26wto_oefiwm%3Fpcif_qecrah%24uvm%5Dccmrakgl%3D081378161%26wto_aoltgnv%3D32692474415677%3A2%24uvm%5Dtgro%3Diwf-582675585137208lmc%2F1%3B0%24ngtuopk%3Fo%24adf%5Dulisug5%3F2c83506%3B120f1ce%3B9fa73%603df%3Af%3A7787%26osaliif%3D0a%3A17249302d3ag9%3Bdc51b1fd8d855%3A5"
    return render_template('test.html', test_iframe_url=test_url)


@app.route('/bg')
@maintenance_check
@login_required
def bg():
    username = session['username']
    unread_count = get_unread_count(username)  # Only count private chat messages
    group_unread_count = get_total_group_unread_count(username)  # Track group messages separately
    lounge_unread_count = get_lounge_unread_count(username)
    return render_template('bg.html',
        user_tokens=users[username].get('tokens', 0),
        username=username,
        unread_count=unread_count,
        group_unread_count=group_unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role'],
        BIRTHDAYS=BIRTHDAYS
    )


@app.route('/youtube')
@maintenance_check
@login_required
def youtube():
    # YouTube is now free for everyone - no access check needed
    return render_template('youtube.html')

@app.route('/twitch')
@maintenance_check
@login_required
def twitch():
    username = session['username']
    # Check if user has twitch access
    if username not in site_access or 'twitch' not in site_access[username]:
        return render_template('no_access.html',
            site_name='Twitch',
            purchase_url=url_for('proxy')
        )
    return render_template('twitch.html')

@app.route('/freemovies')
@maintenance_check
@login_required
def freemovies():
    username = session['username']
    # Check if user has freemovies access
    if username not in site_access or 'freemovies' not in site_access[username]:
        return render_template('no_access.html',
            site_name='Free Movies',
            purchase_url=url_for('proxy')
        )
    return render_template('freemovies.html')

@app.route('/lounge/clear_history', methods=['POST'])
@login_required
def clear_lounge_history():
    """Admin only: Clear entire lounge history and reset all read receipts"""

    # Check if user is admin
    if users[session['username']]['role'] != 'admin':
        return jsonify({'success': False, 'error': 'Admin only'}), 403

    try:
        global lounge_messages, lounge_reactions, lounge_read_receipts

        # Clear all lounge data
        lounge_messages.clear()
        lounge_reactions.clear()
        lounge_read_receipts.clear()

        # Save empty data
        save_json(LOUNGE_FILE, [])
        save_json(LOUNGE_REACTIONS_FILE, {})
        save_json(LOUNGE_READ_RECEIPTS_FILE, {})

        # Add system message that history was cleared
        timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        lounge_messages.append({
            'from': 'system',
            'message': f'🗑️ Lounge history was cleared by {session["username"]}',
            'timestamp': timestamp,
            'display_time': get_ny_time().strftime('%I:%M %p'),
            'type': 'text'
        })
        save_json(LOUNGE_FILE, lounge_messages)

        return jsonify({'success': True, 'message': 'Lounge history cleared'})

    except Exception as e:
        print(f"Error clearing lounge history: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ===============================================================
@app.route('/api/mark_all_as_read', methods=['POST'])
@login_required
@admin_required
def mark_all_as_read():
    try:
        current_time = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

        # ✅ Mark all private chats as read for ALL users
        for chat_key in messages.keys():
            participants = chat_key.split('-')
            for user in participants:
                if user not in read_receipts:
                    read_receipts[user] = {}
                read_receipts[user][chat_key] = current_time

        # ✅ Mark lounge as read for ALL users
        for username in users.keys():
            lounge_read_receipts[username] = current_time

        save_json(READ_RECEIPTS_FILE, read_receipts)
        save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear_all_read_receipts', methods=['POST'])
@login_required
@admin_required
def clear_all_read_receipts():
    try:
        # Create empty read receipts file
        save_json(READ_RECEIPTS_FILE, {})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/lunch_menu')
@login_required
def get_lunch_menu():
    today = get_ny_time()
    today_str = today.strftime('%Y-%m-%d')
    tomorrow = today + timedelta(days=1)
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')

    # Get today's menu or show default message
    today_menu = lunch_menu.get(today_str, {
        'food': 'Weekend / No Menu Available',
        'fact': 'Enjoy your day off!',
        'breakfast': 'No breakfast menu available'
    })

    # Get tomorrow's menu (can be None if not available)
    tomorrow_menu = lunch_menu.get(tomorrow_str)

    return jsonify({
        'today': today_menu,
        'tomorrow': tomorrow_menu,
        'date': today.strftime('%A, %B %d, %Y')
    })

@app.route('/play/<game_id>')
@login_required
def play_game(game_id):
    if game_id not in games:
        return "Game not found", 404
    if not games[game_id].get('available', True):
        return "This game is currently unavailable for maintenance", 503
    game = games[game_id]
    username = session['username']

    # Check if this is a minecraft game - redirect to download
    if game.get('is_minecraft_game', False):
        return redirect(url_for('download', game_id=game_id))

    # Free games: explicitly marked as free_for_all, have price of 0, or is idle_dice (limited time event)
    is_free = game.get('free_for_all', True) or game.get('price', 0) == 0 or game_id == 'idle_dice'

    if is_free:
        pass
    else:
        if username not in purchases:
            purchases[username] = []
        if game_id not in purchases[username]:
            return "You must purchase this game first", 403
    if username not in plays:
        plays[username] = {}
    if game_id not in plays[username]:
        plays[username][game_id] = 0
    plays[username][game_id] += 1
    save_json(PLAYS_FILE, plays)

    # Inject notification system and presence tracking into game HTML
    notification_html = (
        '<div id="chatNotificationContainer"></div>'
        '<script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>'
        '<script>'
        'const socket = io();'
        'socket.on("connect", () => {'
        '    socket.emit("presence_heartbeat");'
        '});'
        'setInterval(() => {'
        '    socket.emit("presence_heartbeat");'
        '}, 10000);'  # Send heartbeat every 10 seconds
        '</script>'
        '<script src="/static/notifications.js?v=3"></script>'
    )

    game_html = game['html_content']

    # Add stopwatch overlay for Idle Dice (January event indicator)
    if game_id == 'idle_dice' or 'idle-dice' in game_html.lower() or 'idle dice' in game.get('name', '').lower():
        stopwatch_overlay = '''
        <div id="idleDiceStopwatch" style="
            position: fixed;
            top: 15px;
            left: 15px;
            z-index: 9999;
            background: rgba(0, 0, 0, 0.8);
            padding: 8px 12px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
            cursor: pointer;
            transition: all 0.3s ease;
        " onclick="window.open('/idle_dice_rewards', '_blank')" onmouseover="this.style.background='rgba(0, 0, 0, 0.95)'" onmouseout="this.style.background='rgba(0, 0, 0, 0.8)'">
            <img src="https://i.ibb.co/XfB6KsN8/stopwatch.png" alt="Limited Time" style="width: 24px; height: 24px;">
            <span style="color: white; font-family: Arial, sans-serif; font-size: 13px; font-weight: 600;">January Event</span>
        </div>
        '''
        notification_html = stopwatch_overlay + notification_html

    # Inject notifications at the end
    if '</body>' in game_html:
        game_html = game_html.replace('</body>', notification_html + '</body>')
    else:
        game_html = game_html + notification_html

    # Return with proper headers for caching and compression
    response = make_response(game_html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
    return response


@app.route('/purchase_game/<game_id>', methods=['POST'])
@login_required
def purchase_game(game_id):
    if game_id not in games:
        return jsonify({'error': 'Game not found'}), 404
    username = session['username']
    game = games[game_id]
    if username not in purchases:
        purchases[username] = []
    if game_id in purchases[username]:
        return jsonify({'error': 'Already purchased'}), 400
    if game.get('free_for_all', True):
        return jsonify({'error': 'Game is free'}), 400
    price = game.get('price', 0)
    user_tokens = users[username].get('tokens', 0)
    if user_tokens < price:
        return jsonify({'error': 'Insufficient tokens'}), 400
    users[username]['tokens'] -= price
    purchases[username].append(game_id)
    save_json(USERS_FILE, users)
    save_json(PURCHASES_FILE, purchases)
    log_transaction('destruction', price, username, 'game_purchase', f'Game: {game_id}')
    return jsonify({'success': True, 'new_balance': users[username]['tokens']})

@app.route('/api/purchase_access/<site_id>', methods=['POST'])
@login_required
def purchase_access(site_id):
    username = session['username']

    # Define available sites and their prices
    site_prices = {
        'youtube': 0,
        'twitch': 50,
        'freemovies': 100,
        'gmail': 50
    }

    if site_id not in site_prices:
        return jsonify({'error': 'Site not found'}), 404

    # Check if user already has access
    if username in site_access and site_id in site_access.get(username, []):
        return jsonify({'error': 'Already purchased'}), 400

    price = site_prices[site_id]
    user_tokens = users[username].get('tokens', 0)

    if user_tokens < price:
        return jsonify({'error': 'Insufficient tokens'}), 400

    # Deduct tokens and grant access
    users[username]['tokens'] -= price
    if username not in site_access:
        site_access[username] = []
    site_access[username].append(site_id)

    save_json(USERS_FILE, users)
    save_json(SITE_ACCESS_FILE, site_access)

    return jsonify({'success': True, 'new_balance': users[username]['tokens']})

@app.route('/purchase_rank/<rank_id>', methods=['POST'])
@login_required
def purchase_rank(rank_id):
    username = session['username']
    rank_index = None
    rank_data = None
    for i, rank in enumerate(RANKS):
        if rank['id'] == rank_id:
            rank_index = i
            rank_data = rank
            break
    if rank_data is None:
        return jsonify({'error': 'Rank not found'}), 404
    current_rank = users[username].get('rank')
    current_rank_index = -1
    if current_rank:
        for i, rank in enumerate(RANKS):
            if rank['id'] == current_rank:
                current_rank_index = i
                break
    if rank_index != current_rank_index + 1:
        return jsonify({'error': 'You must purchase ranks in order!'}), 400
    user_tokens = users[username].get('tokens', 0)
    if user_tokens < rank_data['price']:
        return jsonify({'error': 'Insufficient tokens'}), 400
    users[username]['tokens'] -= rank_data['price']
    users[username]['rank'] = rank_id
    save_json(USERS_FILE, users)
    log_transaction('destruction', rank_data['price'], username, 'rank_purchase', f'Rank: {rank_id}')
    return jsonify({
        'success': True,
        'new_balance': users[username]['tokens'],
        'rank': rank_data['name']
    })

@app.route('/api/add_tokens/<int:amount>', methods=['POST'])
@login_required
def add_tokens(amount):
    username = session['username']
    users[username]['tokens'] += amount
    save_json(USERS_FILE, users)
    return jsonify({'success': True, 'new_balance': users[username]['tokens']})

@app.route('/idle_dice_rewards')
@login_required
def idle_dice_rewards():
    """Display Idle Dice achievement rewards page with manual claim buttons"""
    username = session['username']

    # Organize achievements by category
    categories = {
        'Basic': [],
        'Advanced': [],
        'Expert': [],
        'Legendary': [],
        'Godlike': [],
        'Lustslike': []
    }

    # Get user's claimed achievements
    user_claims = idle_dice_claims.get(username, [])

    # Organize achievements
    total_possible_tokens = 0
    total_earned_tokens = 0

    for ach_id, ach_data in idle_dice_achievements.items():
        category = ach_data.get('category', 'Basic')
        is_claimed = ach_id in user_claims

        achievement_info = {
            'id': ach_id,
            'name': ach_data['name'],
            'description': ach_data['description'],
            'tokens': ach_data['tokens'],
            'check': ach_data['check'],
            'claimed': is_claimed
        }

        categories[category].append(achievement_info)
        total_possible_tokens += ach_data['tokens']

        if is_claimed:
            total_earned_tokens += ach_data['tokens']

    # Sort achievements by token amount (lowest to highest) within each category
    for category in categories:
        categories[category].sort(key=lambda x: x['tokens'])

    # Category descriptions
    category_descriptions = {
        'Basic': 'Basic Achievements are unlocked at the start of the game. There are 17 achievements you can earn. This section includes a variety of requirements with rewards that will help you progress in the game including reaching a certain amount of points, rolling manually/automatically a certain amount of times, and reaching a certain prestige multiplier. Keep in mind that not all achievements you can receive in Idle Dice give you Tokens on StudyHall, "only" those listed below.',
        'Advanced': 'Advanced Achievements are all card-related achievements. There are 21 of them and they are unlocked after getting the Double the Fun achievement which is accomplished by having a prestige multiplier of 200%.',
        'Expert': 'Expert Achievements are mostly achievements that involve roulette. There are 22 of them and they are unlocked once you have access to the roulette which requires you to draw 10 cards in one run.',
        'Legendary': 'Legendary achievements involve golden cards and 13 of them are golden card achievements to accomplish, most are similar to advanced achievements but with golden cards. They are unlocked when you have access to the decks which is obtained by having 52 regular cards and converting them which results in one deck.',
        'Godlike': 'Godlike Achievements almost all have something to do with casinos in one way or another. They are unlocked when you invest your first casino.',
        'Lustslike': 'This achievements tab involves the slot machine and duel dice. They are unlocked when you hit the highest item in the slot machine which is the Cup Point. The name \'Lustslike\' originates from the name of the German person (not the owner of this website) who created this game many years ago.'
    }

    # Check if it's January (NY timezone)
    import pytz
    from datetime import datetime
    ny_tz = pytz.timezone('America/New_York')
    current_time = datetime.now(ny_tz)
    is_january = current_time.month == 1

    return render_template('idle_dice_rewards.html',
                         categories=categories,
                         category_descriptions=category_descriptions,
                         total_possible_tokens=total_possible_tokens,
                         total_earned_tokens=total_earned_tokens,
                         current_tokens=users[username].get('tokens', 0),
                         is_january=is_january)

@app.route('/api/claim_idle_dice_achievement', methods=['POST'])
@login_required
def claim_idle_dice_achievement():
    """Claim tokens for completing an Idle Dice achievement (one-time only per account)"""
    username = session['username']
    data = request.get_json()
    achievement_id = data.get('achievement_id')

    # Check if it's January (NY timezone) - only award tokens during January
    import pytz
    from datetime import datetime
    ny_tz = pytz.timezone('America/New_York')
    current_time = datetime.now(ny_tz)
    is_january = current_time.month == 1

    # Validate achievement exists
    if achievement_id not in idle_dice_achievements:
        return jsonify({'error': 'Invalid achievement'}), 400

    # Check if already claimed
    if username not in idle_dice_claims:
        idle_dice_claims[username] = []

    if achievement_id in idle_dice_claims[username]:
        return jsonify({'error': 'Achievement already claimed'}), 400

    # Award tokens (only during January)
    achievement = idle_dice_achievements[achievement_id]
    tokens = achievement['tokens'] if is_january else 0

    if is_january:
        users[username]['tokens'] = users[username].get('tokens', 0) + tokens

    # Record claim
    idle_dice_claims[username].append(achievement_id)

    # Save data
    save_json(USERS_FILE, users)
    save_json(IDLE_DICE_CLAIMS_FILE, idle_dice_claims)

    # Log transaction (only if tokens were awarded)
    if is_january:
        log_transaction('creation', tokens, username, 'idle_dice_achievement',
                       f"{achievement['name']} ({achievement_id})")

        # Send notification to lounge
        timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        achievement_message = {
            'from': 'system',
            'message': f"{username} earned {tokens}🎟️ from unlocking {achievement['name']} in Idle Dice!",
            'timestamp': timestamp,
            'display_time': get_ny_time().strftime('%I:%M %p'),
            'type': 'achievement',
            'achievement_name': achievement['name'],
            'tokens': tokens,
            'username': username
        }
        lounge_messages.append(achievement_message)
        save_json(LOUNGE_FILE, lounge_messages)

        # Broadcast achievement to lounge via WebSocket
        message_for_broadcast = achievement_message.copy()
        message_for_broadcast['index'] = len(lounge_messages) - 1
        socketio.emit('new_lounge_message', {
            'message': message_for_broadcast,
            'profile_picture': None,
            'user_rank': None
        }, room='lounge')

        # Notifications handled by polling in notifications.js

    return jsonify({
        'success': True,
        'tokens_awarded': tokens,
        'new_balance': users[username]['tokens'],
        'achievement_name': achievement['name'],
        'is_january': is_january
    })

@app.route('/debug_achievements')
@login_required
def debug_achievements():
    """Debug page to show all Idle Dice achievement keys"""
    return render_template('debug_achievements.html')

@app.route('/show_amount')
@login_required
def show_amount():
    """Debug route to show Idle Dice game data from localStorage"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Idle Dice Debug</title>
        <style>
            body {
                font-family: monospace;
                padding: 20px;
                background: #1a1a1a;
                color: #00ff00;
            }
            pre {
                background: #000;
                padding: 20px;
                border-radius: 8px;
                overflow-x: auto;
            }
            .key {
                color: #ffaa00;
                font-weight: bold;
            }
            .value {
                color: #00ffff;
            }
            .points {
                font-size: 24px;
                color: #ff0;
                margin: 20px 0;
                padding: 10px;
                background: #333;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <h1>🎲 Idle Dice LocalStorage Debug</h1>
        <div id="output"></div>

        <script>
            const output = document.getElementById('output');

            // Find all localStorage keys
            const allKeys = Object.keys(localStorage);
            output.innerHTML += '<h2>All localStorage keys:</h2>';
            output.innerHTML += '<pre>' + JSON.stringify(allKeys, null, 2) + '</pre>';

            // Find idle-dice related keys
            const gameKeys = allKeys.filter(key =>
                key.toLowerCase().includes('idle') ||
                key.toLowerCase().includes('dice') ||
                key.toLowerCase().includes('save')
            );

            output.innerHTML += '<h2>Game-related keys found: ' + gameKeys.length + '</h2>';

            if (gameKeys.length === 0) {
                output.innerHTML += '<p style="color: red;">❌ No Idle Dice save data found. Play the game first!</p>';
            }

            gameKeys.forEach(key => {
                try {
                    const data = JSON.parse(localStorage.getItem(key));

                    output.innerHTML += '<hr>';
                    output.innerHTML += '<h3 class="key">Key: ' + key + '</h3>';

                    // Try to find points
                    const possiblePoints = [
                        data.money,
                        data.totalMoney,
                        data.points,
                        data.totalPoints,
                        data.total,
                        data.score,
                        data.totalScore
                    ];

                    let foundPoints = null;
                    for (let i = 0; i < possiblePoints.length; i++) {
                        if (possiblePoints[i] !== undefined && possiblePoints[i] !== null) {
                            foundPoints = possiblePoints[i];
                            break;
                        }
                    }

                    if (foundPoints !== null) {
                        output.innerHTML += '<div class="points">💰 POINTS FOUND: ' +
                            (typeof foundPoints === 'number' ? foundPoints.toLocaleString() : foundPoints) +
                            '</div>';

                        if (parseFloat(foundPoints) >= 1000000) {
                            output.innerHTML += '<div style="color: #0f0; font-size: 20px; padding: 10px; background: #004400; border-radius: 5px; margin: 10px 0;">✅ MILLIONAIRE ACHIEVED! (≥ 1,000,000)</div>';
                        }
                    }

                    // Check for achievements
                    const achievements = data.achievements ||
                                       data.achievementsUnlocked ||
                                       data.unlockedAchievements ||
                                       [];

                    if (achievements.length > 0) {
                        output.innerHTML += '<h4>Achievements:</h4>';
                        output.innerHTML += '<pre>' + JSON.stringify(achievements, null, 2) + '</pre>';
                    }

                    // Show full data structure
                    output.innerHTML += '<h4>Full Save Data Structure:</h4>';
                    output.innerHTML += '<pre>' + JSON.stringify(data, null, 2).substring(0, 5000) + '...</pre>';

                } catch (e) {
                    output.innerHTML += '<p style="color: orange;">⚠️ Could not parse key "' + key + '" - not JSON</p>';
                }
            });

            // Manual claim button for testing
            output.innerHTML += '<hr><h2>Manual Test</h2>';
            output.innerHTML += '<button onclick="testClaim()" style="padding: 10px 20px; font-size: 16px; cursor: pointer; background: #0066cc; color: white; border: none; border-radius: 5px;">Test Claim Millionaire Achievement</button>';
            output.innerHTML += '<div id="claimResult" style="margin-top: 10px;"></div>';

            window.testClaim = function() {
                const resultDiv = document.getElementById('claimResult');
                resultDiv.innerHTML = 'Claiming...';

                fetch('/api/claim_idle_dice_achievement', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        achievement_id: 'points1m'
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        resultDiv.innerHTML = '<div style="color: #0f0; padding: 10px; background: #004400; border-radius: 5px;">✅ SUCCESS! Awarded ' + data.tokens_awarded + ' tokens. New balance: ' + data.new_balance + '</div>';
                    } else {
                        resultDiv.innerHTML = '<div style="color: #f00; padding: 10px; background: #440000; border-radius: 5px;">❌ ERROR: ' + data.error + '</div>';
                    }
                })
                .catch(error => {
                    resultDiv.innerHTML = '<div style="color: #f00; padding: 10px; background: #440000; border-radius: 5px;">❌ NETWORK ERROR: ' + error + '</div>';
                });
            };
        </script>
    </body>
    </html>
    '''

@app.route('/api/leaderboard')
@login_required
def get_leaderboard():
    sorted_users = sorted(users.items(), key=lambda x: x[1].get('tokens', 0), reverse=True)
    top_5 = sorted_users[:5]
    leaderboard = []
    for idx, (username, user_data) in enumerate(top_5, 1):
        leaderboard.append({
            'rank': idx,
            'username': username,
            'tokens': user_data.get('tokens', 0)
        })
    return jsonify({'leaderboard': leaderboard})

@app.route('/api/claim_rank_pass', methods=['POST'])
@login_required
def claim_rank_pass():
    username = session['username']
    user_rank = users[username].get('rank')
    if not user_rank:
        return jsonify({'error': 'You need a rank to claim this reward'}), 400
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    today = now.strftime('%Y-%m-%d')
    if username in rank_pass_state:
        last_claim = rank_pass_state[username].get('last_claim_date')
        if last_claim == today:
            return jsonify({'error': 'Already claimed today! Come back tomorrow'}), 400
    rank_rewards = {
        'bronze': 5,
        'silver': 10,
        'vip': 20,
        'platinum': 25,
        'elite': 30,
        'grandmaster': 67,
        'minister': 100
    }
    reward = rank_rewards.get(user_rank, 0)
    if reward == 0:
        return jsonify({'error': 'Invalid rank'}), 400
    users[username]['tokens'] = users[username].get('tokens', 0) + reward
    rank_pass_state[username] = {
        'last_claim_date': today,
        'last_claim_time': now.strftime('%Y-%m-%d %H:%M:%S')
    }
    save_json(USERS_FILE, users)
    save_json(RANK_PASS_FILE, rank_pass_state)
    log_transaction('creation', reward, username, 'daily_reward')
    return jsonify({
        'success': True,
        'reward': reward,
        'new_balance': users[username]['tokens']
    })

@app.route('/api/rank_pass_status')
@login_required
def rank_pass_status():
    username = session['username']
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    today = now.strftime('%Y-%m-%d')
    claimed_today = False
    if username in rank_pass_state:
        last_claim = rank_pass_state[username].get('last_claim_date')
        if last_claim == today:
            claimed_today = True
    return jsonify({
        'claimed_today': claimed_today,
        'current_date': today
    })

@app.route('/api/create_code', methods=['POST'])
@panel_access_required
def create_code():
    code = request.form.get('code', '').strip().upper()
    amount = request.form.get('amount', 0)
    try:
        amount = int(amount)
    except ValueError:
        return jsonify({'error': 'Invalid amount'}), 400
    if amount > 100:
        return jsonify({'error': 'Amount cannot exceed 100 tokens'}), 400
    if not code or amount <= 0:
        return jsonify({'error': 'Invalid code or amount'}), 400
    if code in codes:
        return jsonify({'error': 'Code already exists'}), 400
    codes[code] = {
        'tokens': amount,
        'created_by': session['username'],
        'created_at': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
        'active': True
    }
    save_json(CODES_FILE, codes)
    return jsonify({'success': True})

@app.route('/api/delete_code/<code>', methods=['POST'])
@panel_access_required
def delete_code(code):
    if code in codes:
        del codes[code]
        save_json(CODES_FILE, codes)
        return jsonify({'success': True})
    return jsonify({'error': 'Code not found'}), 404

@app.route('/api/redeem_code/<code>', methods=['POST'])
@login_required
def redeem_code(code):
    username = session['username']
    code = code.strip().upper()
    if code not in codes:
        return jsonify({'error': 'Code not found'}), 404
    if not codes[code]['active']:
        return jsonify({'error': 'Code is no longer active'}), 400
    if username not in redeemed_codes:
        redeemed_codes[username] = []
    if code in redeemed_codes[username]:
        return jsonify({'error': 'You already redeemed this code'}), 400
    tokens = codes[code]['tokens']
    users[username]['tokens'] += tokens
    redeemed_codes[username].append(code)
    save_json(USERS_FILE, users)
    save_json(REDEEMED_CODES_FILE, redeemed_codes)
    log_transaction('creation', tokens, username, 'code_redeem', f'Code: {code}')

    return jsonify({'success': True, 'tokens': tokens, 'new_balance': users[username]['tokens']})

@app.route('/api/get_codes')
@panel_access_required
def get_codes():
    codes_list = []
    for code, data in codes.items():
        codes_list.append({
            'code': code,
            'tokens': data['tokens'],
            'created_by': data['created_by'],
            'created_at': data['created_at'],
            'active': data['active']
        })
    return jsonify({'codes': codes_list})

@app.route('/api/get_play_stats')
@panel_access_required
def get_play_stats():
    stats = []
    for username, user_plays in plays.items():
        user_games = []
        for game_id, play_count in user_plays.items():
            if game_id in games:
                user_games.append({
                    'game_name': games[game_id]['name'],
                    'plays': play_count
                })
        if user_games:
            stats.append({
                'username': username,
                'games': user_games
            })
    stats.sort(key=lambda x: x['username'])
    return jsonify({'stats': stats})

@app.route('/download/<game_id>')
@login_required
def download(game_id):
    if game_id not in games:
        return "Game not found", 404
    if not games[game_id].get('available', True):
        return "This game is currently unavailable for maintenance", 503
    game = games[game_id]
    file_data = io.BytesIO(game['html_content'].encode('utf-8'))
    file_data.seek(0)
    return send_file(
        file_data,
        mimetype='text/html',
        as_attachment=True,
        download_name=f'{game_id}.html'
    )

@app.route('/panel')
@panel_access_required
def admin_panel():
    username = session['username']
    user_role = users[username].get('role', 'user')

    # Build permissions object for this user
    user_permissions = {}
    for perm, roles in PERMISSIONS.items():
        user_permissions[perm] = user_role in roles

    # Build games metadata
    games_metadata = {}
    for game_id, game_data in games.items():
        games_metadata[game_id] = {
            'name': game_data['name'],
            'available': game_data.get('available', True),
            'price': game_data.get('price', 0),
            'free_for_all': game_data.get('free_for_all', True),
            'is_own_game': game_data.get('is_own_game', False),
            'is_roblox_game': game_data.get('is_roblox_game', False),
            'is_minecraft_game': game_data.get('is_minecraft_game', False),
            'is_pokemon_game': game_data.get('is_pokemon_game', False),
            'background_image': game_data.get('background_image')
        }

    # Build groups data
    groups_data = []
    for group_id, group_data in groups.items():
        all_members = [group_data['leader']] + group_data.get('members', [])
        message_count = len(group_messages.get(group_id, []))
        groups_data.append({
            'id': group_id,
            'name': group_data['name'],
            'leader': group_data['leader'],
            'members': group_data.get('members', []),
            'all_members': all_members,
            'member_count': len(all_members),
            'image': group_data.get('image'),
            'created_at': group_data.get('created_at'),
            'message_count': message_count,
            'rank': group_data.get('rank', 0),
            'rank_display': GROUP_RANKS[group_data.get('rank', 0)]['display'],
            'bank': group_data.get('bank', 0)
        })
    groups_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    # Get pending reports count
    pending_reports = len([r for r in reported_messages if r['status'] == 'pending'])

    # Get pending paychecks count
    pending_paychecks = len(paychecks.get('pending', []))

    # Calculate total messages and snaps in private chats (from Jan 3, 2026 9 PM NY time onwards)
    ny_tz = pytz.timezone('America/New_York')
    reset_date = datetime(2026, 1, 3, 21, 0, 0, tzinfo=ny_tz)  # January 3rd, 2026 at 9 PM NY time
    total_messages = 0
    total_snaps = 0
    for chat_key, chat_messages in messages.items():
        for msg in chat_messages:
            # Only count messages after reset date
            msg_timestamp = msg.get('timestamp')
            should_count = False
            if msg_timestamp:
                try:
                    msg_date = datetime.strptime(msg_timestamp, '%Y-%m-%d %H:%M:%S')
                    # Make msg_date timezone-aware (assume it's in NY time)
                    msg_date = ny_tz.localize(msg_date)
                    if msg_date >= reset_date:
                        should_count = True
                except:
                    # If parsing fails, don't count it
                    should_count = False

            if should_count:
                if msg.get('type') == 'snap':
                    total_snaps += 1
                elif msg.get('type') != 'token_gift':  # Don't count system messages
                    total_messages += 1

    # Filter feedback and website requests based on role
    filtered_feedback = feedback
    filtered_website_requests = website_requests

    if user_role == 'pr_director':
        # PR Directors only see items that haven't been forwarded yet
        filtered_feedback = [item for item in feedback if not item.get('forwarded', False)]
        filtered_website_requests = [item for item in website_requests if not item.get('forwarded', False)]
    elif user_role == 'admin':
        # Admin sees all items, but we'll sort them (forwarded first)
        filtered_feedback = sorted(feedback, key=lambda x: (not x.get('forwarded', False), x.get('timestamp', '')))
        filtered_website_requests = sorted(website_requests, key=lambda x: (not x.get('forwarded', False), x.get('timestamp', '')))

    return render_template('admin.html',
        users=users,
        games=games_metadata,
        announcements=announcements,
        feedback=filtered_feedback,
        website_requests=filtered_website_requests,
        user_role=user_role,
        user_permissions=user_permissions,
        purchases=purchases,
        login_notifications=login_notifications.get(username, []),
        rps_history=rps_history,
        groups=groups_data,
        codes=codes,
        lottery_state=lottery_state,
        maintenance_mode=maintenance_mode,
        STAFF_ROLES=STAFF_ROLES,
        pending_reports=pending_reports,
        pending_paychecks=pending_paychecks,
        reported_messages=reported_messages,
        total_messages=total_messages,
        total_snaps=total_snaps
    )

@app.route('/api/message_stats')
@panel_access_required
def get_message_stats():
    """Get total messages and snaps counts (from Jan 3, 2026 9 PM NY time onwards)"""
    ny_tz = pytz.timezone('America/New_York')
    reset_date = datetime(2026, 1, 3, 21, 0, 0, tzinfo=ny_tz)  # January 3rd, 2026 at 9 PM NY time
    total_messages = 0
    total_snaps = 0
    for chat_key, chat_messages in messages.items():
        for msg in chat_messages:
            # Only count messages after reset date
            msg_timestamp = msg.get('timestamp')
            should_count = False
            if msg_timestamp:
                try:
                    msg_date = datetime.strptime(msg_timestamp, '%Y-%m-%d %H:%M:%S')
                    # Make msg_date timezone-aware (assume it's in NY time)
                    msg_date = ny_tz.localize(msg_date)
                    if msg_date >= reset_date:
                        should_count = True
                except:
                    # If parsing fails, don't count it
                    should_count = False

            if should_count:
                if msg.get('type') == 'snap':
                    total_snaps += 1
                elif msg.get('type') != 'token_gift':  # Don't count system messages
                    total_messages += 1

    return jsonify({
        'success': True,
        'total_messages': total_messages,
        'total_snaps': total_snaps
    })

@app.route('/api/get_game_html/<game_id>')
@admin_required
def get_game_html(game_id):
    if game_id not in games:
        return jsonify({'error': 'Game not found'}), 404
    return jsonify({
        'success': True,
        'html_content': games[game_id]['html_content']
    })

@app.route('/api/get_game_play_counts')
@panel_access_required
def get_game_play_counts():
    """Calculate total plays per game across all users"""
    game_play_counts = {}

    for username, user_plays in plays.items():
        for game_id, play_count in user_plays.items():
            if game_id in games:
                if game_id not in game_play_counts:
                    game_play_counts[game_id] = 0
                game_play_counts[game_id] += play_count

    return jsonify({
        'success': True,
        'play_counts': game_play_counts
    })

@app.route('/panel/edit_token/<username>/<int:amount>', methods=['GET', 'POST'])
@admin_required
def edit_token(username, amount):
    if username in users:
        users[username]['tokens'] = amount
        save_json(USERS_FILE, users)
        log_action(
            actor=session['username'],
            action_type='edit_tokens',
            target=username,
            details=f'Set tokens to {amount}'
        )
    return redirect(url_for('admin_panel'))

@app.route('/panel/change_password/<username>', methods=['POST'])
@panel_access_required
def change_password(username):
    if not has_permission(session['username'], 'change_passwords'):
        return redirect(url_for('admin_panel'))

    if username in users and username != 'admin':
        new_password = request.form.get('new_password')
        reason = request.form.get('reason', '').strip()
        if new_password:
            users[username]['password'] = new_password
            save_json(USERS_FILE, users)
            log_action(
                actor=session['username'],
                action_type='change_password',
                target=username,
                details='Password updated via admin panel',
                reason=reason or 'No reason provided'
            )
    return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game_price/<game_id>', methods=['POST'])
@admin_required
def toggle_game_price(game_id):
    if game_id in games:
        games[game_id]['free_for_all'] = not games[game_id].get('free_for_all', True)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/api/update_game_details/<game_id>', methods=['POST'])
@admin_required
def update_game_details(game_id):
    """Update game price, background image, and featured status"""
    if game_id not in games:
        return jsonify({'error': 'Game not found'}), 404

    data = request.json

    # Update price if provided
    if 'price' in data:
        try:
            games[game_id]['price'] = int(data['price'])
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid price'}), 400

    # Update background image if provided
    if 'background_image' in data:
        bg = data['background_image'].strip()
        games[game_id]['background_image'] = bg if bg else None

    # Update featured status if provided
    if 'is_own_game' in data:
        games[game_id]['is_own_game'] = bool(data['is_own_game'])

    save_json(GAMES_FILE, games)

    return jsonify({
        'success': True,
        'game': {
            'id': game_id,
            'name': games[game_id]['name'],
            'price': games[game_id].get('price', 0),
            'background_image': games[game_id].get('background_image'),
            'is_own_game': games[game_id].get('is_own_game', False)
        }
    })

@app.route('/panel/update_game_price/<game_id>', methods=['POST'])
@admin_required
def update_game_price(game_id):
    if game_id in games:
        price = request.form.get('price', '0')
        try:
            games[game_id]['price'] = int(price)
            save_json(GAMES_FILE, games)
        except ValueError:
            pass
    return redirect(url_for('admin_panel'))

@app.route('/panel/update_game_background/<game_id>', methods=['POST'])
@admin_required
def update_game_background(game_id):
    if game_id in games:
        background_image = request.form.get('background_image', '').strip()
        games[game_id]['background_image'] = background_image if background_image else None
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/delete_feedback/<int:index>', methods=['GET', 'POST'])
@panel_access_required
def delete_feedback(index):
    if 0 <= index < len(feedback):
        feedback.pop(index)
        save_json(FEEDBACK_FILE, feedback)
    return redirect(url_for('admin_panel'))

@app.route('/panel/forward_feedback/<int:index>', methods=['POST'])
@panel_access_required
def forward_feedback(index):
    username = session['username']
    if not has_permission(username, 'manage_feedback'):
        return jsonify({'error': 'No permission'}), 403

    if 0 <= index < len(feedback):
        # Mark as forwarded by this user
        feedback[index]['forwarded'] = True
        feedback[index]['forwarded_by'] = username
        feedback[index]['forwarded_at'] = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        save_json(FEEDBACK_FILE, feedback)
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid index'}), 400

@app.route('/panel/delete_website_request/<int:index>', methods=['GET', 'POST'])
@panel_access_required
def delete_website_request(index):
    username = session['username']
    if not has_permission(username, 'manage_feedback'):
        return redirect(url_for('admin_panel'))
    if 0 <= index < len(website_requests):
        website_requests.pop(index)
        save_json(WEBSITE_REQUESTS_FILE, website_requests)
    return redirect(url_for('admin_panel'))

@app.route('/panel/forward_website_request/<int:index>', methods=['POST'])
@panel_access_required
def forward_website_request(index):
    username = session['username']
    if not has_permission(username, 'manage_feedback'):
        return jsonify({'error': 'No permission'}), 403

    if 0 <= index < len(website_requests):
        # Mark as forwarded by this user
        website_requests[index]['forwarded'] = True
        website_requests[index]['forwarded_by'] = username
        website_requests[index]['forwarded_at'] = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        save_json(WEBSITE_REQUESTS_FILE, website_requests)
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid index'}), 400

@app.route('/panel/create_user', methods=['POST'])
@panel_access_required
def create_user():
    if not has_permission(session['username'], 'create_users'):
        return redirect(url_for('admin_panel'))

    username = request.form.get('username')
    password = request.form.get('password')
    if username and password and username not in users:
        users[username] = {
            'password': password,
            'role': 'user',
            'banned': False,
            'tokens': 0,
            'ban_reason': ''
        }
        save_json(USERS_FILE, users)

        log_action(
            actor=session['username'],
            action_type='create_user',
            target=username,
            details='Created user from admin panel'
        )
    return redirect(url_for('admin_panel'))

@app.route('/panel/promote_ambassador/<username>')
@admin_required
def promote_ambassador(username):
    if username in users and username != 'admin':
        users[username]['role'] = 'ambassador'
        save_json(USERS_FILE, users)
        log_action(
            actor=session['username'],
            action_type='promote_ambassador',
            target=username,
            details='Promoted to ambassador'
        )
    return redirect(url_for('admin_panel'))

@app.route('/panel/demote_ambassador/<username>')
@admin_required
def demote_ambassador(username):
    if username in users and username != 'admin':
        users[username]['role'] = 'user'
        save_json(USERS_FILE, users)
        log_action(
            actor=session['username'],
            action_type='demote_ambassador',
            target=username,
            details='Demoted to user'
        )
    return redirect(url_for('admin_panel'))

@app.route('/panel/ban_user', methods=['POST'])
@panel_access_required
def ban_user():
    if not has_permission(session['username'], 'ban_users'):
        return redirect(url_for('admin_panel'))

    username = request.form.get('username')
    reason = request.form.get('reason', 'No reason provided')
    if username in users and username != 'admin':
        users[username]['banned'] = True
        users[username]['ban_reason'] = reason
        save_json(USERS_FILE, users)
        log_action(
            actor=session['username'],
            action_type='ban_user',
            target=username,
            details='Manual ban from admin panel',
            reason=reason
        )
    return redirect(url_for('admin_panel'))

@app.route('/panel/unban_user/<username>', methods=['GET', 'POST'])
@panel_access_required
def unban_user(username):
    if not has_permission(session['username'], 'ban_users'):
        return redirect(url_for('admin_panel'))

    if username in users:
        users[username]['banned'] = False
        users[username]['ban_reason'] = ''
        save_json(USERS_FILE, users)
        log_action(
            actor=session['username'],
            action_type='unban_user',
            target=username,
            details='User unbanned from admin panel'
        )
    return redirect(url_for('admin_panel'))

@app.route('/panel/delete_user/<username>')
@admin_required
def delete_user(username):
    if username in users and username != 'admin':
        del users[username]
        save_json(USERS_FILE, users)
        log_action(
            actor=session['username'],
            action_type='delete_user',
            target=username,
            details='Deleted user from admin panel'
        )
    return redirect(url_for('admin_panel'))

@app.route('/panel/add_game', methods=['POST'])
@admin_required
def add_game():
    game_name = request.form.get('game_name')
    price = request.form.get('price', '0')
    free_for_all = request.form.get('free_for_all') == 'on'
    is_own_game = request.form.get('is_own_game') == 'on'
    is_roblox_game = request.form.get('is_roblox_game') == 'on'
    is_minecraft_game = request.form.get('is_minecraft_game') == 'on'
    is_pokemon_game = 'is_pokemon_game' in request.form
    background_image = request.form.get('background_image', '').strip()
    html_source = request.form.get('html_source', 'textarea')

    # Get HTML content from either textarea or file upload
    html_content = None
    if html_source == 'file' and 'html_file' in request.files:
        file = request.files['html_file']
        if file and file.filename:
            try:
                html_content = file.read().decode('utf-8')
            except Exception as e:
                print(f"Error reading file: {e}")
                return "Error reading uploaded file", 400
    else:
        html_content = request.form.get('html_content', '')

    if game_name and html_content:
        try:
            price = int(price)
        except ValueError:
            price = 0
        game_id = game_name.lower().replace(' ', '_').replace('+', '_plus')
        games[game_id] = {
            'name': game_name,
            'html_content': html_content,
            'available': True,
            'price': price,
            'free_for_all': free_for_all,
            'is_own_game': is_own_game,
            'is_roblox_game': is_roblox_game,
            'is_minecraft_game': is_minecraft_game,
            'is_pokemon_game': is_pokemon_game,
            'background_image': background_image if background_image else None
        }
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game_roblox/<game_id>', methods=['GET', 'POST'])
@admin_required
def toggle_game_roblox(game_id):
    if game_id in games:
        games[game_id]['is_roblox_game'] = not games[game_id].get('is_roblox_game', False)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game_minecraft/<game_id>', methods=['GET', 'POST'])
@admin_required
def toggle_game_minecraft(game_id):
    if game_id in games:
        games[game_id]['is_minecraft_game'] = not games[game_id].get('is_minecraft_game', False)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game_pokemon/<game_id>', methods=['GET', 'POST'])
@admin_required
def toggle_game_pokemon(game_id):
    if game_id in games:
        games[game_id]['is_pokemon_game'] = not games[game_id].get('is_pokemon_game', False)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game_own/<game_id>', methods=['GET', 'POST'])
@admin_required
def toggle_game_own(game_id):
    if game_id in games:
        games[game_id]['is_own_game'] = not games[game_id].get('is_own_game', False)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/update_game/<game_id>', methods=['POST'])
@admin_required
def update_game(game_id):
    if game_id not in games:
        if request.is_json:
            return jsonify({'error': 'Game not found'}), 404
        else:
            return redirect(url_for('admin_panel'))

    # Support both form and JSON data
    if request.is_json:
        data = request.json
        html_content = data.get('html_content')
    else:
        html_content = request.form.get('html_content')

    if html_content:
        games[game_id]['html_content'] = html_content
        save_json(GAMES_FILE, games)

        if request.is_json:
            return jsonify({'success': True})
        else:
            return redirect(url_for('admin_panel'))

    if request.is_json:
        return jsonify({'error': 'No HTML content provided'}), 400
    else:
        return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game/<game_id>', methods=['GET', 'POST'])
@admin_required
def toggle_game(game_id):
    if game_id in games:
        games[game_id]['available'] = not games[game_id].get('available', True)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/delete_game/<game_id>', methods=['GET', 'POST'])
@admin_required
def delete_game(game_id):
    if game_id in games:
        del games[game_id]
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/add_announcement', methods=['POST'])
@admin_required
def add_announcement():
    announcement_text = request.form.get('announcement')
    announcement_title = request.form.get('title', '')
    if announcement_text:
        import uuid
        announcements.append({
            'id': str(uuid.uuid4()),
            'title': announcement_title,
            'text': announcement_text,
            'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_json(ANNOUNCEMENTS_FILE, announcements)
    return redirect(url_for('admin_panel'))

@app.route('/panel/delete_announcement/<int:index>', methods=['GET', 'POST'])
@admin_required
def delete_announcement(index):
    if 0 <= index < len(announcements):
        announcements.pop(index)
        save_json(ANNOUNCEMENTS_FILE, announcements)
    return redirect(url_for('admin_panel'))

@app.route('/api/toggle_maintenance', methods=['POST'])
@admin_required
def toggle_maintenance():
    global maintenance_mode
    maintenance_mode['enabled'] = not maintenance_mode.get('enabled', False)
    save_json(MAINTENANCE_FILE, maintenance_mode)
    return jsonify({'success': True, 'enabled': maintenance_mode['enabled']})

@app.route('/api/get_maintenance_status')
@admin_required
def get_maintenance_status():
    return jsonify({'enabled': maintenance_mode.get('enabled', False)})

@app.route('/api/tower_start', methods=['POST'])
@login_required
def tower_start():
    username = session['username']
    data = request.json
    bet_amount = data.get('amount')
    mode = data.get('mode')  # 2 or 3 piles
    # Validate input
    if not bet_amount or not mode:
        return jsonify({'error': 'Invalid request'}), 400
    try:
        bet_amount = int(bet_amount)
    except ValueError:
        return jsonify({'error': 'Invalid bet amount'}), 400
    if bet_amount < 5:
        return jsonify({'error': 'Minimum bet is 5 tokens'}), 400
    if mode not in [2, 3]:
        return jsonify({'error': 'Invalid mode'}), 400
    user_tokens = users[username].get('tokens', 0)
    if user_tokens < bet_amount:
        return jsonify({'error': 'Insufficient tokens'}), 400
    users[username]['tokens'] -= bet_amount
    save_json(USERS_FILE, users)
    pattern = []
    for level in range(9):
        if mode == 2:
            pattern.append([random.randint(0, 1)])
        else:
            rand = random.random()
            if rand < 0.6:
                bobcat_pos = random.randint(0, 2)
                pattern.append([i for i in range(3) if i != bobcat_pos])
            else:
                pattern.append([random.randint(0, 2)])
    rigged_level = -1
    # -------------------------------
    # 🔹 Save active game session
    # -------------------------------
    tower_games[username] = {
        'bet': bet_amount,
        'mode': mode,
        'level': 0,
        'pattern': pattern,
        'active': True,
        'rigged_level': rigged_level
    }
    # -------------------------------
    # 🔹 Return fair game start
    # -------------------------------
    return jsonify({
        'success': True,
        'message': 'Game started successfully.',
        'pattern': pattern,  # normally hidden on frontend for fairness
        'new_balance': users[username]['tokens']
    })

@app.route('/api/tower_select', methods=['POST'])
@login_required
def tower_select():
    username = session['username']
    if username not in tower_games or not tower_games[username]['active']:
        return jsonify({'error': 'No active game'}), 400

    game = tower_games[username]
    data = request.json
    level = data.get('level')
    tile = data.get('tile')

    if level != game['level']:
        return jsonify({'error': 'Invalid level'}), 400

    # Check if hit egg or bobcat
    if game['mode'] == 2:
        # Mode 2: pattern contains egg position
        hit_egg = (tile == game['pattern'][level][0])
    else:
        # Mode 3: pattern contains list of egg positions
        hit_egg = (tile in game['pattern'][level])


    if hit_egg:
        # Success! Move to next level
        game['level'] += 1
        multipliers = {
            2: [1.5, 2.25, 3.38, 5.06, 7.59, 11.39, 17.09, 25.63, 38.44],
            3: [1.2, 1.44, 1.73, 2.07, 2.49, 2.99, 3.58, 4.30, 5.16]
        }
        multiplier = multipliers[game['mode']][game['level'] - 1]

        return jsonify({
            'success': True,
            'hit_egg': True,
            'level': game['level'],
            'multiplier': multiplier
        })
    else:
        # Hit bobcat - game over
        game['active'] = False
        save_json(USERS_FILE, users)
        log_casino_game('tower', username, game['bet'], False, -game['bet'])
        log_transaction('destruction', game['bet'], username, 'casino_tower')

        return jsonify({
            'success': True,
            'hit_egg': False,
            'new_balance': users[username]['tokens']
        })

@app.route('/api/tower_cashout', methods=['POST'])
@login_required
def tower_cashout():
    username = session['username']
    if username not in tower_games or not tower_games[username]['active']:
        return jsonify({'error': 'No active game'}), 400
    game = tower_games[username]
    if game['level'] == 0:
        return jsonify({'error': 'Must complete at least one level'}), 400
    # Calculate winnings
    multipliers = {
        2: [1.5, 2.25, 3.38, 5.06, 7.59, 11.39, 17.09, 25.63, 38.44],
        3: [1.2, 1.44, 1.73, 2.07, 2.49, 2.99, 3.58, 4.30, 5.16]
    }
    multiplier = multipliers[game['mode']][game['level'] - 1]
    profit = int(game['bet'] * multiplier)
    # Add winnings
    users[username]['tokens'] += profit
    save_json(USERS_FILE, users)
    # Add to recent wins (keep only last 3)
    global tower_recent_wins
    tower_recent_wins.insert(0, {
        'username': username,
        'level': game['level'],
        'profit': profit,
        'multiplier': f"{multiplier:.2f}"
    })
    tower_recent_wins = tower_recent_wins[:3]
    save_json(TOWER_WINS_FILE, tower_recent_wins)
    log_casino_game('tower', username, game['bet'], True, profit - game['bet'])
    log_transaction('creation', profit, username, 'casino_tower')
    game['active'] = False
    return jsonify({
        'success': True,
        'profit': profit,
        'multiplier': multiplier,
        'new_balance': users[username]['tokens']
    })

@app.route('/api/update_maintenance_notes', methods=['POST'])
@admin_required
def update_maintenance_notes():
    global maintenance_mode
    data = request.json
    maintenance_mode['title'] = data.get('title', "What's Coming")
    maintenance_mode['notes'] = data.get('notes', [])
    save_json(MAINTENANCE_FILE, maintenance_mode)
    return jsonify({'success': True})

@app.route('/api/get_maintenance_notes')
@admin_required
def get_maintenance_notes():
    return jsonify({
        'title': maintenance_mode.get('title', "What's Coming"),
        'notes': maintenance_mode.get('notes', [])
    })

@app.route('/panel/toggle_game_access/<username>/<game_id>/<action>', methods=['POST'])
@admin_required
def toggle_game_access(username, game_id, action):
    if username not in users:
        return jsonify({'error': 'User not found'}), 404

    if game_id not in games:
        return jsonify({'error': 'Game not found'}), 404

    if action not in ['grant', 'remove']:
        return jsonify({'error': 'Invalid action'}), 400

    if username not in purchases:
        purchases[username] = []

    if action == 'grant':
        if game_id not in purchases[username]:
            purchases[username].append(game_id)
    elif action == 'remove':
        if game_id in purchases[username]:
            purchases[username].remove(game_id)

    save_json(PURCHASES_FILE, purchases)
    return jsonify({'success': True, 'message': f'{"Granted" if action == "grant" else "Removed"} access for {username}'})

# ===== LOTTERY ROUTES =====

@app.route('/api/lottery_info')
@login_required
def get_lottery_info():
    """Get current lottery information"""
    global lottery_state, lottery_tickets

    # Check if lottery ended
    if lottery_state.get('active') and lottery_state.get('end_time'):
        ny_tz = pytz.timezone('America/New_York')
        now = datetime.now(ny_tz)
        end_time = datetime.strptime(lottery_state['end_time'], '%Y-%m-%d %H:%M:%S')
        end_time = ny_tz.localize(end_time)

        if now >= end_time:
            # Lottery ended - pick winner
            end_lottery()

    # Get user's ticket count
    username = session['username']
    user_tickets = lottery_tickets.get(username, 0)

    # Get all participants
    participants = []
    total_tickets = 0
    for user, count in lottery_tickets.items():
        participants.append({
            'username': user,
            'tickets': count
        })
        total_tickets += count

    # Sort by ticket count descending
    participants.sort(key=lambda x: x['tickets'], reverse=True)

    return jsonify({
        'active': lottery_state.get('active', False),
        'prize_pool': lottery_state.get('prize_pool', 0),
        'ticket_price': lottery_state.get('ticket_price', 0),
        'end_time': lottery_state.get('end_time'),
        'user_tickets': user_tickets,
        'total_tickets': total_tickets,
        'participants': participants,
        'winner': lottery_state.get('winner'),
        'winner_tickets': lottery_state.get('winner_tickets'),
        'total_tickets_won': lottery_state.get('total_tickets'),
        'won_at': lottery_state.get('won_at'),
        'won_amount': lottery_state.get('won_amount')
    })

@app.route('/api/lottery_purchase', methods=['POST'])
@login_required
def purchase_lottery_ticket():
    """Purchase lottery tickets"""
    global lottery_state, lottery_tickets

    if not lottery_state.get('active'):
        return jsonify({'error': 'No active lottery'}), 400

    data = request.json
    ticket_count = data.get('count', 1)

    if ticket_count < 1:
        return jsonify({'error': 'Must purchase at least 1 ticket'}), 400

    username = session['username']
    ticket_price = lottery_state.get('ticket_price', 0)
    total_cost = ticket_price * ticket_count

    # Check balance
    user_tokens = users[username].get('tokens', 0)
    if user_tokens < total_cost:
        return jsonify({'error': 'Insufficient tokens'}), 400

    # Deduct tokens (tokens just disappear, don't add to prize pool)
    users[username]['tokens'] -= total_cost

    # Add tickets
    if username not in lottery_tickets:
        lottery_tickets[username] = 0
    lottery_tickets[username] += ticket_count

    # ✅ REMOVED: Prize pool accumulation - it's now fixed by admin

    save_json(USERS_FILE, users)
    save_json(LOTTERY_TICKETS_FILE, lottery_tickets)
    log_transaction('destruction', total_cost, username, 'lottery_ticket')

    return jsonify({
        'success': True,
        'new_balance': users[username]['tokens'],
        'total_tickets': lottery_tickets[username]
    })

def end_lottery():
    """End the lottery and pick a winner"""
    global lottery_state, lottery_tickets

    if not lottery_tickets:
        # No participants - cancel lottery
        lottery_state['active'] = False
        save_json(LOTTERY_FILE, lottery_state)
        return

    # Create weighted list of participants
    weighted_participants = []
    for username, ticket_count in lottery_tickets.items():
        for _ in range(ticket_count):
            weighted_participants.append(username)

    # Pick winner (check for predetermined winner first)
    if lottery_state.get('predetermined_winner') and lottery_state.get('predetermined_winner') in lottery_tickets:
        winner = lottery_state['predetermined_winner']
    else:
        winner = random.choice(weighted_participants)

    # Award prize
    prize = lottery_state['prize_pool']
    users[winner]['tokens'] = users[winner].get('tokens', 0) + prize

    # Calculate totals
    total_tickets = sum(lottery_tickets.values())
    winner_tickets = lottery_tickets[winner]

    # Update lottery state
    lottery_state['active'] = False
    lottery_state['winner'] = winner
    lottery_state['winner_tickets'] = winner_tickets
    lottery_state['total_tickets'] = total_tickets
    lottery_state['won_at'] = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    lottery_state['won_amount'] = prize
    lottery_state['ended_at'] = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

    # Archive to history
    global lottery_history
    lottery_history_entry = {
        'prize_pool': lottery_state['prize_pool'],
        'ticket_price': lottery_state['ticket_price'],
        'total_tickets': total_tickets,
        'winner': winner,
        'winner_tickets': winner_tickets,
        'created_at': lottery_state.get('created_at'),
        'ended_at': lottery_state['ended_at'],
        'won_amount': prize
    }
    lottery_history.insert(0, lottery_history_entry)  # Add to beginning (most recent first)
    save_json(LOTTERY_HISTORY_FILE, lottery_history)

    # Clear tickets
    lottery_tickets.clear()

    save_json(USERS_FILE, users)
    save_json(LOTTERY_FILE, lottery_state)
    save_json(LOTTERY_TICKETS_FILE, lottery_tickets)
    log_transaction('creation', prize, winner, 'lottery_win')

    # Post to lounge
    timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    lounge_messages.append({
        'from': 'system',
        'message': f'🎰 LOTTERY WINNER: {winner} won {prize} tokens with {winner_tickets}/{total_tickets} tickets! 🎉',
        'timestamp': timestamp,
        'display_time': get_ny_time().strftime('%I:%M %p'),
        'type': 'text'
    })
    save_json(LOUNGE_FILE, lounge_messages)

# ===== ADMIN LOTTERY ROUTES =====

@app.route('/api/lottery_create', methods=['POST'])
@admin_required
def create_lottery():
    """Create a new lottery"""
    global lottery_state, lottery_tickets

    if lottery_state.get('active'):
        return jsonify({'error': 'A lottery is already active'}), 400

    data = request.json
    ticket_price = data.get('ticket_price', 0)
    prize_pool = data.get('prize_pool', 0)  # ✅ NEW: Admin sets prize pool
    duration_hours = data.get('duration_hours', 0)

    if ticket_price < 1:
        return jsonify({'error': 'Ticket price must be at least 1 token'}), 400

    if prize_pool < 1:  # ✅ NEW: Validate prize pool
        return jsonify({'error': 'Prize pool must be at least 1 token'}), 400

    if duration_hours < 1:
        return jsonify({'error': 'Duration must be at least 1 hour'}), 400

    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    end_time = now + timedelta(hours=duration_hours)

    lottery_state = {
        'active': True,
        'prize_pool': prize_pool,  # ✅ CHANGED: Now set by admin
        'ticket_price': ticket_price,
        'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
        'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'winner': None,
        'winner_tickets': None,
        'total_tickets': None,
        'won_at': None,
        'won_amount': None
    }

    lottery_tickets.clear()

    save_json(LOTTERY_FILE, lottery_state)
    save_json(LOTTERY_TICKETS_FILE, lottery_tickets)

    return jsonify({'success': True})

@app.route('/api/lottery_end', methods=['POST'])
@admin_required
def manually_end_lottery():
    """Manually end the current lottery"""
    if not lottery_state.get('active'):
        return jsonify({'error': 'No active lottery'}), 400

    end_lottery()

    return jsonify({'success': True})

@app.route('/api/lottery_cancel', methods=['POST'])
@admin_required
def cancel_lottery():
    """Cancel the current lottery - NO refunds since prize pool is separate"""
    global lottery_state, lottery_tickets

    if not lottery_state.get('active'):
        return jsonify({'error': 'No active lottery'}), 400

    # ✅ CHANGED: No refunds - tokens spent are gone
    # Admin can manually refund if they want via token management

    # Archive cancelled lottery to history if there were participants
    global lottery_history
    if lottery_tickets:  # Only archive if there were participants
        total_tickets = sum(lottery_tickets.values())
        lottery_history_entry = {
            'prize_pool': lottery_state['prize_pool'],
            'ticket_price': lottery_state['ticket_price'],
            'total_tickets': total_tickets,
            'winner': None,
            'winner_tickets': 0,
            'created_at': lottery_state.get('created_at'),
            'ended_at': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
            'cancelled': True,
            'won_amount': 0
        }
        lottery_history.insert(0, lottery_history_entry)
        save_json(LOTTERY_HISTORY_FILE, lottery_history)

    # Clear lottery
    lottery_state['active'] = False
    lottery_state['prize_pool'] = 0
    lottery_tickets.clear()

    save_json(LOTTERY_FILE, lottery_state)
    save_json(LOTTERY_TICKETS_FILE, lottery_tickets)

    return jsonify({'success': True})

GAME_SAVES_FILE = os.path.join(DATA_DIR, 'game_saves.json')

# Load game saves
game_saves = load_json(GAME_SAVES_FILE, {})

@app.route('/api/save_game_progress', methods=['POST'])
@login_required
def save_game_progress():
    username = session['username']
    data = request.json

    game = data.get('game')
    key = data.get('key')
    value = data.get('data')

    if not game or not key:
        return jsonify({'error': 'Invalid request'}), 400

    # Initialize user's game saves if needed
    if username not in game_saves:
        game_saves[username] = {}
    if game not in game_saves[username]:
        game_saves[username][game] = {}

    # Save the data
    game_saves[username][game][key] = value
    save_json(GAME_SAVES_FILE, game_saves)

    return jsonify({'success': True})

@app.route('/api/load_game_progress', methods=['POST'])
@login_required
def load_game_progress():
    username = session['username']
    data = request.json

    game = data.get('game')

    if not game:
        return jsonify({'error': 'Invalid request'}), 400

    # Get user's saves for this game
    user_saves = game_saves.get(username, {}).get(game, {})

    return jsonify({'success': True, 'saves': user_saves})

# ===============================================================
# Rock Paper Scissors Game API
# ===============================================================

def get_rps_game_key(user1, user2):
    """Get consistent game key for two users"""
    return '-'.join(sorted([user1, user2]))

def determine_rps_winner(move1, move2):
    """Determine winner of RPS round. Returns 'move1', 'move2', or 'tie'"""
    if move1 == move2:
        return 'tie'

    # Rock beats Scissors
    if move1 == 'rock' and move2 == 'scissors':
        return 'move1'
    if move2 == 'rock' and move1 == 'scissors':
        return 'move2'

    # Paper beats Rock
    if move1 == 'paper' and move2 == 'rock':
        return 'move1'
    if move2 == 'paper' and move1 == 'rock':
        return 'move2'

    # Scissors beats Paper
    if move1 == 'scissors' and move2 == 'paper':
        return 'move1'
    if move2 == 'scissors' and move1 == 'paper':
        return 'move2'

    # Should never reach here
    return 'tie'

def check_rps_timeouts():
    """Check for expired invites and moves, handle timeouts"""
    current_time = get_ny_time().timestamp()
    games_to_remove = []

    for game_key, game in list(rps_games.items()):  # Use list() to avoid dict size change during iteration
        # Check invite timeout (1 hour)
        if game['status'] == 'pending' and game.get('invite_time'):
            if current_time - game['invite_time'] > 3600:  # 1 hour
                games_to_remove.append(game_key)

        # Check move timeout during active game (1 hour)
        elif game['status'] == 'active':
            last_move_time = game.get('last_move_time', game.get('start_time', current_time))
            if current_time - last_move_time > 3600:  # 1 hour
                # Find who didn't respond
                if game.get('player1_move') and not game.get('player2_move'):
                    # Player 2 didn't respond, player 1 wins
                    winner = game['player1']
                    loser = game['player2']
                elif game.get('player2_move') and not game.get('player1_move'):
                    # Player 1 didn't respond, player 2 wins
                    winner = game['player2']
                    loser = game['player1']
                else:
                    # Both haven't moved (shouldn't happen but handle it), refund both
                    amount = game['bet_amount']
                    users[game['player1']]['tokens'] = users[game['player1']].get('tokens', 0) + amount
                    users[game['player2']]['tokens'] = users[game['player2']].get('tokens', 0) + amount
                    games_to_remove.append(game_key)
                    save_json(USERS_FILE, users)
                    continue

                # Award tokens to winner
                total_pot = game['bet_amount'] * 2
                users[winner]['tokens'] = users[winner].get('tokens', 0) + total_pot

                # Mark game as completed with timeout
                game['status'] = 'completed'
                game['winner'] = winner
                game['timeout_win'] = True
                game['completion_time'] = current_time
                save_json(USERS_FILE, users)

                # Log the game to history
                log_rps_game(game)

                # Don't remove yet - let the UI show winner for 10 seconds

    # Remove expired pending invites immediately
    for game_key in games_to_remove:
        if game_key in rps_games:
            del rps_games[game_key]

    # Remove completed games after 10 seconds
    completed_to_remove = []
    for game_key, game in list(rps_games.items()):
        if game['status'] == 'completed' and game.get('completion_time'):
            if current_time - game['completion_time'] > 10:  # 10 seconds
                completed_to_remove.append(game_key)

    for game_key in completed_to_remove:
        if game_key in rps_games:
            del rps_games[game_key]

    if games_to_remove or completed_to_remove:
        save_json(RPS_GAMES_FILE, rps_games)

def log_rps_game(game):
    """Log completed RPS game to history"""
    loser = game['player2'] if game['winner'] == game['player1'] else game['player1']
    total_pot = game['bet_amount'] * 2

    history_entry = {
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
        'winner': game['winner'],
        'loser': loser,
        'amount_won': total_pot,
        'bet_amount': game['bet_amount'],
        'player1': game['player1'],
        'player2': game['player2'],
        'player1_wins': game.get('player1_wins', 0),
        'player2_wins': game.get('player2_wins', 0),
        'timeout_win': game.get('timeout_win', False),
        'total_rounds': game.get('current_round', 1)
    }

    rps_history.insert(0, history_entry)  # Add to beginning (most recent first)

    # Keep only last 100 games
    if len(rps_history) > 100:
        rps_history.pop()

    save_json(RPS_HISTORY_FILE, rps_history)

@app.route('/api/rps/invite/<other_user>', methods=['POST'])
@login_required
def rps_invite(other_user):
    """Invite another user to play Rock Paper Scissors"""
    current_user = session['username']

    if other_user not in users:
        return jsonify({'error': 'User not found'}), 404

    if other_user == current_user:
        return jsonify({'error': 'Cannot play against yourself'}), 400

    # Check if current user already has a pending/active game with ANYONE
    for existing_key in rps_games:
        existing_game = rps_games[existing_key]
        if existing_game['status'] in ['pending', 'active']:
            if current_user in [existing_game['player1'], existing_game['player2']]:
                return jsonify({'error': 'You already have an active or pending game'}), 400

    # Check if other user already has a pending/active game with ANYONE
    for existing_key in rps_games:
        existing_game = rps_games[existing_key]
        if existing_game['status'] in ['pending', 'active']:
            if other_user in [existing_game['player1'], existing_game['player2']]:
                return jsonify({'error': f'{other_user} is already in a game'}), 400

    data = request.json
    bet_amount = int(data.get('bet_amount', 5))

    if bet_amount < 5:
        return jsonify({'error': 'Minimum bet is 5 tokens'}), 400

    # Check if both users have enough tokens
    if users[current_user].get('tokens', 0) < bet_amount:
        return jsonify({'error': 'You do not have enough tokens'}), 400

    if users[other_user].get('tokens', 0) < bet_amount:
        return jsonify({'error': f'{other_user} does not have enough tokens'}), 400

    game_key = get_rps_game_key(current_user, other_user)

    # Create game
    rps_games[game_key] = {
        'player1': current_user,
        'player2': other_user,
        'bet_amount': bet_amount,
        'status': 'pending',
        'invite_time': get_ny_time().timestamp(),
        'player1_wins': 0,
        'player2_wins': 0,
        'rounds': [],
        'current_round': None
    }
    save_json(RPS_GAMES_FILE, rps_games)

    # Add RPS notification to chat messages for notification system
    chat_key = get_chat_key(current_user, other_user)
    if chat_key not in messages:
        messages[chat_key] = []

    new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    messages[chat_key].append({
        'from': current_user,
        'to': other_user,
        'type': 'rps_invite',
        'text': f'I am challenging you to RPS for {bet_amount} tokens! Lets play it the Bobcat Way.',
        'timestamp': new_timestamp,
        'read': False
    })
    save_json(MESSAGES_FILE, messages)

    return jsonify({'success': True, 'game_key': game_key})

@app.route('/api/rps/accept/<other_user>', methods=['POST'])
@login_required
def rps_accept(other_user):
    """Accept an RPS game invite"""
    current_user = session['username']
    game_key = get_rps_game_key(current_user, other_user)

    if game_key not in rps_games:
        return jsonify({'error': 'No pending game found'}), 404

    game = rps_games[game_key]

    if game['status'] != 'pending':
        return jsonify({'error': 'Game is not pending'}), 400

    if game['player2'] != current_user:
        return jsonify({'error': 'You are not the invited player'}), 403

    # Check if both users still have enough tokens (re-check player1 too)
    if users[game['player1']].get('tokens', 0) < game['bet_amount']:
        del rps_games[game_key]
        save_json(RPS_GAMES_FILE, rps_games)
        return jsonify({'error': f'{game["player1"]} no longer has enough tokens'}), 400

    if users[current_user].get('tokens', 0) < game['bet_amount']:
        del rps_games[game_key]
        save_json(RPS_GAMES_FILE, rps_games)
        return jsonify({'error': 'You no longer have enough tokens'}), 400

    # Deduct tokens from BOTH players when game starts
    users[game['player1']]['tokens'] -= game['bet_amount']
    users[current_user]['tokens'] -= game['bet_amount']
    save_json(USERS_FILE, users)

    # Start game
    game['status'] = 'active'
    game['start_time'] = get_ny_time().timestamp()
    game['last_move_time'] = get_ny_time().timestamp()
    game['current_round'] = 1
    save_json(RPS_GAMES_FILE, rps_games)

    return jsonify({'success': True, 'game': game})

@app.route('/api/rps/decline/<other_user>', methods=['POST'])
@login_required
def rps_decline(other_user):
    """Decline an RPS game invite"""
    current_user = session['username']
    game_key = get_rps_game_key(current_user, other_user)

    if game_key not in rps_games:
        return jsonify({'error': 'No pending game found'}), 404

    game = rps_games[game_key]

    if game['status'] != 'pending':
        return jsonify({'error': 'Game is not pending'}), 400

    if game['player2'] != current_user:
        return jsonify({'error': 'You are not the invited player'}), 403

    # Remove game (no tokens to refund since they weren't deducted yet)
    del rps_games[game_key]
    save_json(RPS_GAMES_FILE, rps_games)

    return jsonify({'success': True})

@app.route('/api/rps/status/<other_user>')
@login_required
def rps_status(other_user):
    """Get RPS game status"""
    current_user = session['username']
    game_key = get_rps_game_key(current_user, other_user)

    # Check for timeouts first
    check_rps_timeouts()

    if game_key not in rps_games:
        return jsonify({'game': None})

    # Get fresh copy after timeout check
    if game_key not in rps_games:
        return jsonify({'game': None})

    game = rps_games[game_key].copy()

    # Don't reveal opponent's move until both have moved
    if game['status'] == 'active':
        if game.get('player1_move') and game.get('player2_move'):
            # Both moved, show both
            pass
        else:
            # Hide opponent's move - show "chosen" if they've moved but you haven't
            if current_user == game['player1']:
                if game.get('player2_move') and not game.get('player1_move'):
                    # Opponent has moved but you haven't - hide their move
                    game['player2_move'] = 'chosen'
                elif not game.get('player2_move'):
                    game['player2_move'] = None
            else:  # current_user == player2
                if game.get('player1_move') and not game.get('player2_move'):
                    # Opponent has moved but you haven't - hide their move
                    game['player1_move'] = 'chosen'
                elif not game.get('player1_move'):
                    game['player1_move'] = None

    return jsonify({'game': game})

@app.route('/api/rps/move/<other_user>', methods=['POST'])
@login_required
def rps_move(other_user):
    """Make a move in RPS game"""
    current_user = session['username']
    game_key = get_rps_game_key(current_user, other_user)

    if game_key not in rps_games:
        return jsonify({'error': 'No active game found'}), 404

    game = rps_games[game_key]

    if game['status'] != 'active':
        return jsonify({'error': 'Game is not active'}), 400

    data = request.json
    move = data.get('move')  # 'rock', 'paper', or 'scissors'

    if move not in ['rock', 'paper', 'scissors']:
        return jsonify({'error': 'Invalid move'}), 400

    # Determine which player this is
    is_player1 = (current_user == game['player1'])
    move_key = 'player1_move' if is_player1 else 'player2_move'

    # Check if already moved this round
    if game.get(move_key):
        return jsonify({'error': 'You have already made your move this round'}), 400

    # Record move
    game[move_key] = move
    game['last_move_time'] = get_ny_time().timestamp()

    # Check if both players have moved
    if game.get('player1_move') and game.get('player2_move'):
        # Determine winner of this round using helper function
        p1_move = game['player1_move']
        p2_move = game['player2_move']

        # Use helper function to determine which move wins
        move_winner = determine_rps_winner(p1_move, p2_move)

        if move_winner == 'tie':
            winner = 'tie'
        elif move_winner == 'move1':
            # Player1's move wins
            winner = 'player1'
            game['player1_wins'] += 1
        else:  # move_winner == 'move2'
            # Player2's move wins
            winner = 'player2'
            game['player2_wins'] += 1

        # Record round
        round_data = {
            'round': game['current_round'],
            'player1_move': p1_move,
            'player2_move': p2_move,
            'winner': winner
        }
        game['rounds'].append(round_data)

        # Check if game is over (first to 3 wins)
        if game['player1_wins'] >= 3:
            # Player 1 wins
            total_pot = game['bet_amount'] * 2
            users[game['player1']]['tokens'] = users[game['player1']].get('tokens', 0) + total_pot
            game['status'] = 'completed'
            game['winner'] = game['player1']
            game['completion_time'] = get_ny_time().timestamp()
            game['timeout_win'] = False
            save_json(USERS_FILE, users)

            # Log the game to history
            log_rps_game(game)

            # Don't delete - let UI show winner for 10 seconds
        elif game['player2_wins'] >= 3:
            # Player 2 wins
            total_pot = game['bet_amount'] * 2
            users[game['player2']]['tokens'] = users[game['player2']].get('tokens', 0) + total_pot
            game['status'] = 'completed'
            game['winner'] = game['player2']
            game['completion_time'] = get_ny_time().timestamp()
            game['timeout_win'] = False
            save_json(USERS_FILE, users)

            # Log the game to history
            log_rps_game(game)

            # Don't delete - let UI show winner for 10 seconds
        else:
            # Next round
            game['current_round'] += 1
            game['player1_move'] = None
            game['player2_move'] = None

    # Create response with hidden moves if needed
    # Check if game was deleted (completed) - use the game dict before deletion
    if game_key not in rps_games:
        return jsonify({
            'success': True,
            'game': {
                'status': 'completed',
                'winner': game.get('winner'),
                'player1_wins': game.get('player1_wins', 0),
                'player2_wins': game.get('player2_wins', 0)
            }
        })

    # Only save if game still exists (not deleted)
    if game_key in rps_games:
        save_json(RPS_GAMES_FILE, rps_games)

    game_response = game.copy()
    if game['status'] == 'active':
        if game.get('player1_move') and game.get('player2_move'):
            # Both moved, show both
            pass
        else:
            # Hide opponent's move from response
            if is_player1:
                if game.get('player2_move') and not game.get('player1_move'):
                    game_response['player2_move'] = 'chosen'
            else:
                if game.get('player1_move') and not game.get('player2_move'):
                    game_response['player1_move'] = 'chosen'

    return jsonify({'success': True, 'game': game_response})

@app.route('/api/toggle_glow_effect', methods=['POST'])
@login_required
def toggle_glow_effect():
    """Toggle the glow effect on or off"""
    username = session['username']

    # Check if glow effect is unlocked
    if 'glow_effect' not in users[username] or not users[username]['glow_effect'].get('unlocked', False):
        return jsonify({'success': False, 'error': 'Glow effect not unlocked'}), 403

    # Toggle the enabled state
    current_state = users[username]['glow_effect'].get('enabled', True)
    users[username]['glow_effect']['enabled'] = not current_state
    save_json(USERS_FILE, users)

    return jsonify({
        'success': True,
        'enabled': users[username]['glow_effect']['enabled']
    })

# ===============================================================
# Groups Feature Routes
# ===============================================================

def get_group_unread_count(username, group_id):
    """Count unread messages in a group for a user"""
    if group_id not in group_messages or not group_messages[group_id]:
        return 0

    last_read = group_read_receipts.get(username, {}).get(group_id, '')

    # Count messages from others that are newer than last_read
    return sum(1 for msg in group_messages[group_id]
               if msg.get('from') != username and msg.get('from') != 'system' and msg['timestamp'] > last_read)

def get_total_group_unread_count(username):
    """Get total unread count across all groups user is member of"""
    total = 0
    for group_id, group_data in groups.items():
        if username == group_data['leader'] or username in group_data.get('members', []):
            total += get_group_unread_count(username, group_id)
    return total

@app.route('/groups')
@maintenance_check
@login_required
def groups_list():
    """Display list of all groups"""
    username = session['username']
    unread_count = get_unread_count(username)  # Only count private chat messages
    group_unread_count = get_total_group_unread_count(username)  # Track group messages separately
    lounge_unread_count = get_lounge_unread_count(username)

    # Get groups with unread counts
    groups_data = []
    for group_id, group_data in groups.items():
        is_member = username == group_data['leader'] or username in group_data.get('members', [])
        unread = get_group_unread_count(username, group_id) if is_member else 0

        # Get last message preview
        last_message = None
        if group_id in group_messages and group_messages[group_id]:
            last_msg = group_messages[group_id][-1]
            if last_msg.get('type') == 'snap':
                preview = '📷 Snap'
            elif last_msg.get('type') == 'voice':
                preview = '🎤 Voice message'
            else:
                preview = last_msg.get('text', '')[:40] + ('...' if len(last_msg.get('text', '')) > 40 else '')
            last_message = {
                'preview': preview,
                'timestamp': last_msg['timestamp'],
                'from': last_msg['from']
            }

        groups_data.append({
            'id': group_id,
            'name': group_data['name'],
            'leader': group_data['leader'],
            'members': group_data.get('members', []),
            'image': group_data.get('image'),
            'is_member': is_member,
            'unread': unread,
            'last_message': last_message,
            'member_count': len(group_data.get('members', [])) + 1,  # +1 for leader
            'rank': group_data.get('rank', 0),
            'rank_display': GROUP_RANKS[group_data.get('rank', 0)]['display'],
            'bank': group_data.get('bank', 0)
        })

    # Sort by bank amount (highest first)
    groups_data.sort(key=lambda x: x['bank'], reverse=True)

    # Check if user already has a group they lead
    user_has_group = any(g['leader'] == username for g in groups.values())

    # Redirect to main chat page which has groups
    return redirect(url_for('chat'))

@app.route('/group/<group_id>')
@maintenance_check
@login_required
def group_chat(group_id):
    """Display group chat or group info"""
    if group_id not in groups:
        return "Group not found", 404

    username = session['username']
    group_data = groups[group_id]
    is_member = username == group_data['leader'] or username in group_data.get('members', [])

    if not is_member:
        # Show group info page for non-members
        return render_template('group_info.html',
            group=group_data,
            group_id=group_id,
            profiles=profiles,
            user_role=users[username]['role']
        )

    # Mark as read on page load
    if group_id in group_messages and group_messages[group_id]:
        if username not in group_read_receipts:
            group_read_receipts[username] = {}
        group_read_receipts[username][group_id] = group_messages[group_id][-1]['timestamp']
        save_json(GROUP_READ_RECEIPTS_FILE, group_read_receipts)

    can_manage_messages = username == group_data['leader']

    # Get reactions for this group
    reactions = group_reactions.get(group_id, {})

    return render_template('group_chat.html',
        group=group_data,
        group_id=group_id,
        messages=group_messages.get(group_id, []),
        reactions=reactions,
        current_user=username,
        is_leader=username == group_data['leader'],
        can_manage_messages=can_manage_messages,
        user_role=users[username]['role'],
        profiles=profiles,
        all_users=[u for u in users.keys() if u != username and u != group_data['leader'] and u not in group_data.get('members', [])],
        STAFF_ROLES=STAFF_ROLES,
        RANKS=RANKS,
        users=users,
        GROUP_RANKS=GROUP_RANKS
    )

@app.route('/api/group/create', methods=['POST'])
@login_required
def create_group():
    """Create a new group"""
    username = session['username']

    # Check if user already has a group
    if any(g['leader'] == username for g in groups.values()):
        return jsonify({'error': 'You can only create one group'}), 400

    # Check tokens
    if users[username].get('tokens', 0) < 100:
        return jsonify({'error': 'Insufficient tokens. You need 100 tokens to create a group'}), 400

    data = request.json
    group_name = data.get('name', '').strip()
    members = data.get('members', [])
    image = data.get('image')  # Base64 image or None

    # Validation
    if not group_name:
        return jsonify({'error': 'Group name is required'}), 400

    if len(group_name) > 30:
        return jsonify({'error': 'Group name must be 30 characters or less'}), 400

    # Check if group name already exists
    if any(g['name'].lower() == group_name.lower() for g in groups.values()):
        return jsonify({'error': 'A group with this name already exists'}), 400

    # Check member limit (new groups start at rank 0, which has 4 total member cap)
    # Ambassadors cannot bypass this - everyone follows same cap rules except "Ambassadors" group
    member_cap = GROUP_RANKS[0]['member_cap']
    if len(members) + 1 > member_cap:  # +1 for the leader
        return jsonify({'error': f'Maximum {member_cap - 1} members allowed ({member_cap} total including you)'}), 400

    # Validate members exist
    for member in members:
        if member not in users:
            return jsonify({'error': f'User {member} does not exist'}), 400
        if member == username:
            return jsonify({'error': 'You cannot add yourself as a member'}), 400

    # Deduct tokens
    users[username]['tokens'] -= 100
    save_json(USERS_FILE, users)

    # Create group
    import uuid
    group_id = str(uuid.uuid4())[:8]

    groups[group_id] = {
        'id': group_id,
        'name': group_name,
        'leader': username,
        'members': members,
        'image': image,
        'created_at': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
        'rank': 0,
        'bank': 0
    }

    # Initialize messages
    group_messages[group_id] = [{
        'from': 'system',
        'text': f'{username} created the group "{group_name}"',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    }]

    save_json(GROUPS_FILE, groups)
    save_json(GROUP_MESSAGES_FILE, group_messages)

    # Send notifications to added members via chat
    for member in members:
        chat_key = get_chat_key(username, member)
        if chat_key not in messages:
            messages[chat_key] = []
        messages[chat_key].append({
            'from': 'system',
            'to': member,
            'type': 'group_invite',
            'text': f'{username} added you to the group "{group_name}"',
            'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
            'read': False
        })
    save_json(MESSAGES_FILE, messages)

    return jsonify({
        'success': True,
        'group_id': group_id,
        'new_balance': users[username]['tokens']
    })

@app.route('/api/group/<group_id>/send', methods=['POST'])
@login_required
def send_group_message(group_id):
    """Send a message to a group"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    # Check if user is member
    if username != group_data['leader'] and username not in group_data.get('members', []):
        return jsonify({'error': 'You are not a member of this group'}), 403

    message_text = request.form.get('message', '').strip()
    if not message_text:
        return jsonify({'error': 'Message cannot be empty'}), 400

    reply_to_index = request.form.get('reply_to_index')
    reply_to = None
    if reply_to_index is not None and str(reply_to_index).strip() != '':
        try:
            reply_to = {
                'index': int(reply_to_index),
                'sender': request.form.get('reply_to_sender', ''),
                'preview': request.form.get('reply_to_preview', ''),
                'type': request.form.get('reply_to_type', 'text')
            }
        except ValueError:
            reply_to = None

    if group_id not in group_messages:
        group_messages[group_id] = []

    new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

    group_messages[group_id].append({
        'from': username,
        'text': message_text,
        'timestamp': new_timestamp,
        'reply_to': reply_to
    })

    save_json(GROUP_MESSAGES_FILE, group_messages)

    # Mark as read for sender
    if username not in group_read_receipts:
        group_read_receipts[username] = {}
    group_read_receipts[username][group_id] = new_timestamp
    save_json(GROUP_READ_RECEIPTS_FILE, group_read_receipts)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/messages')
@login_required
def get_group_messages(group_id):
    """Get messages for a group"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    # Check if user is member
    if username != group_data['leader'] and username not in group_data.get('members', []):
        return jsonify({'error': 'You are not a member of this group'}), 403

    # Performance optimization: Add pagination support
    limit = request.args.get('limit', 100, type=int)  # Default 100 messages
    since = request.args.get('since', '', type=str)  # Timestamp filter

    chat_messages = group_messages.get(group_id, [])

    # Filter messages newer than 'since' timestamp if provided
    if since:
        chat_messages = [m for m in chat_messages if m.get('timestamp', '') > since]

    # Limit to last N messages
    chat_messages = chat_messages[-limit:]

    return jsonify({
        'messages': chat_messages,
        'reactions': group_reactions.get(group_id, {}),
        'group': group_data
    })

@app.route('/api/group/<group_id>/mark_read', methods=['POST'])
@login_required
def mark_group_read(group_id):
    """Mark group messages as read"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']

    if group_id in group_messages and group_messages[group_id]:
        if username not in group_read_receipts:
            group_read_receipts[username] = {}
        group_read_receipts[username][group_id] = group_messages[group_id][-1]['timestamp']
        save_json(GROUP_READ_RECEIPTS_FILE, group_read_receipts)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/send_snap', methods=['POST'])
@login_required
def send_group_snap(group_id):
    """Send a snap to a group"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username != group_data['leader'] and username not in group_data.get('members', []):
        return jsonify({'error': 'You are not a member of this group'}), 403

    photo_data = request.json.get('photo')
    if not photo_data:
        return jsonify({'error': 'No photo provided'}), 400

    if group_id not in group_messages:
        group_messages[group_id] = []

    new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

    group_messages[group_id].append({
        'from': username,
        'type': 'snap',
        'photo': photo_data,
        'opened_by': [],
        'timestamp': new_timestamp
    })

    save_json(GROUP_MESSAGES_FILE, group_messages)

    # Mark as read for sender
    if username not in group_read_receipts:
        group_read_receipts[username] = {}
    group_read_receipts[username][group_id] = new_timestamp
    save_json(GROUP_READ_RECEIPTS_FILE, group_read_receipts)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/send_voice', methods=['POST'])
@login_required
def send_group_voice(group_id):
    """Send a voice message to a group"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username != group_data['leader'] and username not in group_data.get('members', []):
        return jsonify({'error': 'You are not a member of this group'}), 403

    audio_data = request.json.get('audio')
    duration = request.json.get('duration', 0)

    if not audio_data:
        return jsonify({'error': 'No audio provided'}), 400

    if group_id not in group_messages:
        group_messages[group_id] = []

    new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

    group_messages[group_id].append({
        'from': username,
        'type': 'voice',
        'audio': audio_data,
        'duration': duration,
        'timestamp': new_timestamp
    })

    save_json(GROUP_MESSAGES_FILE, group_messages)

    # Mark as read for sender
    if username not in group_read_receipts:
        group_read_receipts[username] = {}
    group_read_receipts[username][group_id] = new_timestamp
    save_json(GROUP_READ_RECEIPTS_FILE, group_read_receipts)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/open_snap/<int:message_index>', methods=['POST'])
@login_required
def open_group_snap(group_id, message_index):
    """Open a snap in a group"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username != group_data['leader'] and username not in group_data.get('members', []):
        return jsonify({'error': 'You are not a member of this group'}), 403

    if group_id not in group_messages or message_index >= len(group_messages[group_id]):
        return jsonify({'error': 'Snap not found'}), 404

    msg = group_messages[group_id][message_index]

    if msg.get('type') != 'snap':
        return jsonify({'error': 'Not a snap'}), 400

    if msg.get('from') == username:
        return jsonify({'error': "You can't view your own snaps!"}), 400

    if username in msg.get('opened_by', []):
        return jsonify({'error': 'Already opened'}), 400

    if 'opened_by' not in msg:
        msg['opened_by'] = []
    msg['opened_by'].append(username)

    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({
        'success': True,
        'photo': msg['photo'],
        'opened_count': len(msg['opened_by'])
    })

@app.route('/api/group/<group_id>/react/<int:message_index>', methods=['POST'])
@login_required
def react_to_group_message(group_id, message_index):
    """React to a message in a group"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username != group_data['leader'] and username not in group_data.get('members', []):
        return jsonify({'error': 'You are not a member of this group'}), 403

    emoji = request.json.get('emoji')
    if not emoji:
        return jsonify({'error': 'No emoji provided'}), 400

    if group_id not in group_messages or message_index >= len(group_messages[group_id]):
        return jsonify({'error': 'Message not found'}), 404

    if group_id not in group_reactions:
        group_reactions[group_id] = {}

    msg_key = str(message_index)
    if msg_key not in group_reactions[group_id]:
        group_reactions[group_id][msg_key] = {}

    if emoji not in group_reactions[group_id][msg_key]:
        group_reactions[group_id][msg_key][emoji] = []

    if username in group_reactions[group_id][msg_key][emoji]:
        group_reactions[group_id][msg_key][emoji].remove(username)
        if not group_reactions[group_id][msg_key][emoji]:
            del group_reactions[group_id][msg_key][emoji]
    else:
        group_reactions[group_id][msg_key][emoji].append(username)

    save_json(GROUP_REACTIONS_FILE, group_reactions)

    return jsonify({'success': True, 'reactions': group_reactions[group_id].get(msg_key, {})})

@app.route('/api/group/<group_id>/add_member', methods=['POST'])
@login_required
def add_group_member(group_id):
    """Add a member to a group (leader only)"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username != group_data['leader']:
        return jsonify({'error': 'Only the group leader can add members'}), 403

    member_username = request.json.get('username')
    if not member_username:
        return jsonify({'error': 'Username is required'}), 400

    if member_username not in users:
        return jsonify({'error': 'User does not exist'}), 400

    if member_username == username:
        return jsonify({'error': 'You cannot add yourself'}), 400

    if member_username in group_data.get('members', []):
        return jsonify({'error': 'User is already a member'}), 400

    # Check member limit based on group rank
    # Only "Ambassadors" group has unlimited cap
    if group_data['name'] != 'Ambassadors':
        current_rank = group_data.get('rank', 0)
        member_cap = GROUP_RANKS[current_rank]['member_cap']
        current_total = len(group_data.get('members', [])) + 1  # +1 for leader
        if current_total >= member_cap:
            return jsonify({'error': f'Group is full (maximum {member_cap} members including leader). Upgrade group rank to increase capacity.'}), 400

    # Add member
    if 'members' not in groups[group_id]:
        groups[group_id]['members'] = []
    groups[group_id]['members'].append(member_username)

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []
    group_messages[group_id].append({
        'from': 'system',
        'text': f'{member_username} was added to the group by {username}',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })

    save_json(GROUPS_FILE, groups)
    save_json(GROUP_MESSAGES_FILE, group_messages)

    # Send notification to added member via chat
    chat_key = get_chat_key(username, member_username)
    if chat_key not in messages:
        messages[chat_key] = []
    messages[chat_key].append({
        'from': 'system',
        'to': member_username,
        'type': 'group_invite',
        'text': f'🎊 {username} added you to the group "{group_data["name"]}"!',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
        'read': False
    })
    save_json(MESSAGES_FILE, messages)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/kick_member', methods=['POST'])
@login_required
def kick_group_member(group_id):
    """Kick a member from a group (leader only)"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username != group_data['leader']:
        return jsonify({'error': 'Only the group leader can kick members'}), 403

    member_username = request.json.get('username')
    if not member_username:
        return jsonify({'error': 'Username is required'}), 400

    if member_username not in group_data.get('members', []):
        return jsonify({'error': 'User is not a member'}), 400

    # Remove member
    groups[group_id]['members'].remove(member_username)

    # Add system message
    group_messages[group_id].append({
        'from': 'system',
        'text': f'{member_username} was removed from the group',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })

    save_json(GROUPS_FILE, groups)
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    """Leave a group"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username == group_data['leader']:
        return jsonify({'error': 'Leaders cannot leave their own group. Delete the group instead.'}), 400

    if username not in group_data.get('members', []):
        return jsonify({'error': 'You are not a member of this group'}), 400

    # Remove member
    groups[group_id]['members'].remove(username)

    # Add system message
    group_messages[group_id].append({
        'from': 'system',
        'text': f'{username} left the group',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })

    save_json(GROUPS_FILE, groups)
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    """Delete a group (leader only)"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username != group_data['leader']:
        return jsonify({'error': 'Only the group leader can delete the group'}), 403

    # Delete group and all associated data
    del groups[group_id]
    if group_id in group_messages:
        del group_messages[group_id]
    if group_id in group_reactions:
        del group_reactions[group_id]

    # Remove from read receipts
    for user in group_read_receipts:
        if group_id in group_read_receipts[user]:
            del group_read_receipts[user][group_id]

    save_json(GROUPS_FILE, groups)
    save_json(GROUP_MESSAGES_FILE, group_messages)
    save_json(GROUP_REACTIONS_FILE, group_reactions)
    save_json(GROUP_READ_RECEIPTS_FILE, group_read_receipts)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/delete_message/<int:message_index>', methods=['POST'])
@login_required
def delete_group_message(group_id, message_index):
    """Delete a message from group (leader only)"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    if username != group_data['leader']:
        return jsonify({'error': 'Only the group leader can delete messages'}), 403

    if group_id not in group_messages or message_index >= len(group_messages[group_id]):
        return jsonify({'error': 'Message not found'}), 404

    # Delete message
    group_messages[group_id].pop(message_index)

    # Update reactions indices
    if group_id in group_reactions:
        new_reactions = {}
        for key, reactions in group_reactions[group_id].items():
            idx = int(key)
            if idx < message_index:
                new_reactions[key] = reactions
            elif idx > message_index:
                new_reactions[str(idx - 1)] = reactions
        group_reactions[group_id] = new_reactions

    save_json(GROUP_MESSAGES_FILE, group_messages)
    save_json(GROUP_REACTIONS_FILE, group_reactions)

    return jsonify({'success': True})

@app.route('/api/group/<group_id>/deposit', methods=['POST'])
@login_required
def deposit_to_group_bank(group_id):
    """Deposit tokens from personal account to group bank"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    # Check if user is member
    if username != group_data['leader'] and username not in group_data.get('members', []):
        return jsonify({'error': 'You are not a member of this group'}), 403

    data = request.json
    amount = data.get('amount', 0)

    # Validation
    if not isinstance(amount, int) or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    if users[username].get('tokens', 0) < amount:
        return jsonify({'error': 'Insufficient tokens'}), 400

    # Transfer tokens
    users[username]['tokens'] -= amount
    groups[group_id]['bank'] = groups[group_id].get('bank', 0) + amount

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []

    group_messages[group_id].append({
        'from': 'system',
        'text': f'{username} deposited {amount} tokens to the group bank. Bank balance: {groups[group_id]["bank"]} tokens',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })

    save_json(USERS_FILE, users)
    save_json(GROUPS_FILE, groups)
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({
        'success': True,
        'new_balance': users[username]['tokens'],
        'bank_balance': groups[group_id]['bank']
    })

@app.route('/api/group/<group_id>/upgrade', methods=['POST'])
@login_required
def upgrade_group_rank(group_id):
    """Upgrade group to next rank (leader only)"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    # Only leader can upgrade
    if username != group_data['leader']:
        return jsonify({'error': 'Only the group leader can upgrade the group'}), 403

    current_rank = group_data.get('rank', 0)

    # Check if already at max rank
    if current_rank >= 5:
        return jsonify({'error': 'Group is already at maximum rank'}), 400

    next_rank = current_rank + 1
    upgrade_cost = GROUP_RANKS[next_rank]['cost']
    bank_balance = group_data.get('bank', 0)

    # Check if enough tokens in bank
    if bank_balance < upgrade_cost:
        return jsonify({'error': f'Insufficient tokens in bank. Need {upgrade_cost} tokens, have {bank_balance}'}), 400

    # Perform upgrade
    groups[group_id]['bank'] = bank_balance - upgrade_cost
    groups[group_id]['rank'] = next_rank

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []

    group_messages[group_id].append({
        'from': 'system',
        'text': f'{username} upgraded the group to {GROUP_RANKS[next_rank]["name"]}. Cost: {upgrade_cost} tokens. Bank balance: {groups[group_id]["bank"]} tokens. Member cap increased to {GROUP_RANKS[next_rank]["member_cap"]}.',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })

    save_json(GROUPS_FILE, groups)
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({
        'success': True,
        'new_rank': next_rank,
        'rank_name': GROUP_RANKS[next_rank]['name'],
        'bank_balance': groups[group_id]['bank'],
        'member_cap': GROUP_RANKS[next_rank]['member_cap']
    })

@app.route('/api/group/<group_id>/send_from_bank', methods=['POST'])
@login_required
def send_from_group_bank(group_id):
    """Send tokens from group bank to a member (leader only)"""
    if group_id not in groups:
        return jsonify({'error': 'Group not found'}), 404

    username = session['username']
    group_data = groups[group_id]

    # Only leader can send from bank
    if username != group_data['leader']:
        return jsonify({'error': 'Only the group leader can send tokens from the bank'}), 403

    data = request.json
    recipient = data.get('recipient')
    amount = data.get('amount', 0)

    # Validation
    if not recipient:
        return jsonify({'error': 'Recipient is required'}), 400

    if recipient not in users:
        return jsonify({'error': 'Recipient does not exist'}), 400

    if not isinstance(amount, int) or amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400

    bank_balance = group_data.get('bank', 0)
    if bank_balance < amount:
        return jsonify({'error': f'Insufficient tokens in bank. Bank has {bank_balance} tokens'}), 400

    # Check if recipient is a member or leader
    if recipient != group_data['leader'] and recipient not in group_data.get('members', []):
        return jsonify({'error': 'Recipient must be a member of the group'}), 400

    # Transfer tokens
    groups[group_id]['bank'] = bank_balance - amount
    users[recipient]['tokens'] = users[recipient].get('tokens', 0) + amount

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []

    group_messages[group_id].append({
        'from': 'system',
        'text': f'{username} sent {amount} tokens from the bank to {recipient}. Bank balance: {groups[group_id]["bank"]} tokens',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })

    save_json(GROUPS_FILE, groups)
    save_json(USERS_FILE, users)
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({
        'success': True,
        'bank_balance': groups[group_id]['bank'],
        'recipient_balance': users[recipient]['tokens']
    })

@app.route('/api/groups/unread_count')
@login_required
def get_groups_unread_count():
    """Get total unread count for groups"""
    username = session['username']
    return jsonify({'count': get_total_group_unread_count(username)})

@app.route('/api/chat/unread_count')
@login_required
def get_chat_unread_count():
    """Get unread count for private chats only (not groups)"""
    username = session['username']
    chat_unread = get_unread_count(username)
    return jsonify({
        'success': True,
        'chat_unread': chat_unread,
        'total': chat_unread  # Only return chat unread, not groups
    })

@app.route('/api/lounge/unread_count')
@login_required
def get_lounge_unread_count_api():
    """Get unread count for lounge"""
    username = session['username']
    lounge_unread = get_lounge_unread_count(username)
    return jsonify({
        'success': True,
        'count': lounge_unread
    })

@app.route('/api/lounge_notifications')
@login_required
def get_lounge_notifications():
    """Get unread lounge notifications for polling"""
    username = session['username']

    if not lounge_messages:
        return jsonify({'notifications': []})

    last_read = lounge_read_receipts.get(username, '')

    # Get unread messages from others
    unread_messages = []
    for msg in lounge_messages:
        if msg.get('from') == username:
            continue
        if not last_read or msg['timestamp'] > last_read:
            unread_messages.append({
                'from': msg.get('from', 'Unknown'),
                'message': msg.get('message', ''),
                'timestamp': msg['timestamp'],
                'type': msg.get('type', 'text')
            })

    return jsonify({'notifications': unread_messages})

# ===============================================================
# Admin Group Management Routes
# ===============================================================

@app.route('/api/admin/groups')
@panel_access_required
def admin_get_groups():
    """Get all groups for admin panel"""
    if not has_permission(session['username'], 'manage_groups'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    groups_list = []
    for group_id, group_data in groups.items():
        all_members = [group_data['leader']] + group_data.get('members', [])
        message_count = len(group_messages.get(group_id, []))
        groups_list.append({
            'id': group_id,
            'name': group_data['name'],
            'leader': group_data['leader'],
            'members': group_data.get('members', []),
            'all_members': all_members,
            'member_count': len(all_members),
            'image': group_data.get('image'),
            'created_at': group_data.get('created_at'),
            'message_count': message_count
        })
    # Sort by creation date (newest first)
    groups_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify({'success': True, 'groups': groups_list})

@app.route('/api/admin/group/<group_id>/rename', methods=['POST'])
@panel_access_required
def admin_rename_group(group_id):
    """Admin rename a group"""
    if not has_permission(session['username'], 'manage_groups'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    if group_id not in groups:
        return jsonify({'success': False, 'error': 'Group not found'}), 404

    data = request.json
    new_name = data.get('name', '').strip()

    if not new_name:
        return jsonify({'success': False, 'error': 'Group name cannot be empty'}), 400

    if len(new_name) > 30:
        return jsonify({'success': False, 'error': 'Group name must be 30 characters or less'}), 400

    # Check if name already exists (excluding current group)
    if any(g['name'].lower() == new_name.lower() and gid != group_id for gid, g in groups.items()):
        return jsonify({'success': False, 'error': 'A group with this name already exists'}), 400

    old_name = groups[group_id]['name']
    groups[group_id]['name'] = new_name
    save_json(GROUPS_FILE, groups)

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []
    group_messages[group_id].append({
        'from': 'system',
        'text': f'Group renamed from "{old_name}" to "{new_name}" by admin',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({'success': True, 'new_name': new_name})

@app.route('/api/admin/group/<group_id>/delete', methods=['POST'])
@panel_access_required
def admin_delete_group(group_id):
    """Admin delete a group"""
    if not has_permission(session['username'], 'manage_groups'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    if group_id not in groups:
        return jsonify({'success': False, 'error': 'Group not found'}), 404

    group_name = groups[group_id]['name']

    # Delete all group data
    del groups[group_id]
    if group_id in group_messages:
        del group_messages[group_id]
    if group_id in group_reactions:
        del group_reactions[group_id]

    # Clean up read receipts
    for username in list(group_read_receipts.keys()):
        if group_id in group_read_receipts[username]:
            del group_read_receipts[username][group_id]

    save_json(GROUPS_FILE, groups)
    save_json(GROUP_MESSAGES_FILE, group_messages)
    save_json(GROUP_REACTIONS_FILE, group_reactions)
    save_json(GROUP_READ_RECEIPTS_FILE, group_read_receipts)

    return jsonify({'success': True, 'deleted_name': group_name})

@app.route('/api/admin/group/<group_id>/kick/<member>', methods=['POST'])
@panel_access_required
def admin_kick_member(group_id, member):
    """Admin kick a member from a group"""
    if not has_permission(session['username'], 'manage_groups'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    if group_id not in groups:
        return jsonify({'success': False, 'error': 'Group not found'}), 404

    group_data = groups[group_id]

    if member == group_data['leader']:
        return jsonify({'success': False, 'error': 'Cannot kick the group leader'}), 400

    if member not in group_data.get('members', []):
        return jsonify({'success': False, 'error': 'User is not a member of this group'}), 400

    groups[group_id]['members'].remove(member)
    save_json(GROUPS_FILE, groups)

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []
    group_messages[group_id].append({
        'from': 'system',
        'text': f'{member} was removed from the group by admin',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({'success': True})

@app.route('/api/admin/group/<group_id>/transfer/<new_leader>', methods=['POST'])
@panel_access_required
def admin_transfer_leadership(group_id, new_leader):
    """Admin transfer group leadership"""
    if not has_permission(session['username'], 'manage_groups'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    if group_id not in groups:
        return jsonify({'success': False, 'error': 'Group not found'}), 404

    group_data = groups[group_id]
    old_leader = group_data['leader']

    if new_leader not in users:
        return jsonify({'success': False, 'error': 'User does not exist'}), 400

    # Check if new leader is a member or the current leader
    all_members = [old_leader] + group_data.get('members', [])
    if new_leader not in all_members:
        return jsonify({'success': False, 'error': 'New leader must be a current member of the group'}), 400

    if new_leader == old_leader:
        return jsonify({'success': False, 'error': 'User is already the leader'}), 400

    # Transfer leadership
    groups[group_id]['leader'] = new_leader

    # Update members list: remove new leader, add old leader
    members = group_data.get('members', [])
    if new_leader in members:
        members.remove(new_leader)
    if old_leader not in members:
        members.append(old_leader)
    groups[group_id]['members'] = members

    save_json(GROUPS_FILE, groups)

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []
    group_messages[group_id].append({
        'from': 'system',
        'text': f'Leadership transferred from {old_leader} to {new_leader} by admin',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({'success': True, 'new_leader': new_leader})

@app.route('/api/admin/group/<group_id>/add_member', methods=['POST'])
@panel_access_required
def admin_add_member(group_id):
    """Admin add a member to a group"""
    if not has_permission(session['username'], 'manage_groups'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    if group_id not in groups:
        return jsonify({'success': False, 'error': 'Group not found'}), 404

    data = request.json
    new_member = data.get('username', '').strip()

    if not new_member:
        return jsonify({'success': False, 'error': 'Username is required'}), 400

    if new_member not in users:
        return jsonify({'success': False, 'error': 'User does not exist'}), 400

    group_data = groups[group_id]
    all_members = [group_data['leader']] + group_data.get('members', [])

    if new_member in all_members:
        return jsonify({'success': False, 'error': 'User is already a member'}), 400

    # Check member limit - even admin must respect cap (except for "Ambassadors" group)
    if group_data['name'] != 'Ambassadors':
        current_rank = group_data.get('rank', 0)
        member_cap = GROUP_RANKS[current_rank]['member_cap']
        current_total = len(all_members)
        if current_total >= member_cap:
            return jsonify({'success': False, 'error': f'Group is full (maximum {member_cap} members including leader)'}), 400

    if 'members' not in groups[group_id]:
        groups[group_id]['members'] = []
    groups[group_id]['members'].append(new_member)
    save_json(GROUPS_FILE, groups)

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []
    group_messages[group_id].append({
        'from': 'system',
        'text': f'{new_member} was added to the group by admin',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({'success': True})

@app.route('/api/report_message', methods=['POST'])
@login_required
def report_message():
    """Report a message in private chat or a group"""
    data = request.json
    chat_key = data.get('chat_key')
    group_id = data.get('group_id')
    message_index = data.get('message_index')
    reason = data.get('reason', '')
    sender_hint = data.get('sender')
    preview_hint = data.get('preview', '')
    timestamp_hint = data.get('timestamp', '')

    if (not chat_key and not group_id) or message_index is None:
        return jsonify({'error': 'Invalid request'}), 400

    try:
        message_index = int(message_index)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid message index'}), 400

    reporter = session['username']

    # Group message reporting
    if group_id:
        group_id = str(group_id)
        if group_id not in groups:
            return jsonify({'error': 'Group not found'}), 404

        group_data = groups[group_id]
        if reporter != group_data['leader'] and reporter not in group_data.get('members', []):
            return jsonify({'error': 'You are not a member of this group'}), 403

        if group_id not in group_messages or message_index >= len(group_messages[group_id]):
            return jsonify({'error': 'Message not found'}), 404

        msg = group_messages[group_id][message_index]
        key_for_report = f'group:{group_id}'

        # Can't report your own messages
        if msg.get('from') == reporter:
            return jsonify({'error': 'Cannot report your own message'}), 400

        for report in reported_messages:
            if report['chat_key'] == key_for_report and report['message_index'] == message_index:
                return jsonify({'error': 'Message already reported'}), 400

        content_preview = msg.get('text', '[Media Message]')
        msg_type = msg.get('type', 'text')
        if msg_type == 'snap':
            content_preview = '📸 [Snap Message]'
        elif msg_type == 'voice':
            content_preview = '🎤 [Voice Message]'

        report = {
            'id': len(reported_messages) + 1,
            'chat_key': key_for_report,
            'message_index': message_index,
            'message_content': content_preview,
            'message_type': msg_type,
            'sender': msg.get('from'),
            'reporter': reporter,
            'reason': reason,
            'status': 'pending',
            'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
            'resolved_by': None,
            'resolved_at': None,
            'resolution_note': None
        }

        reported_messages.insert(0, report)
        save_json(REPORTED_MESSAGES_FILE, reported_messages)

        return jsonify({'success': True, 'message': 'Report submitted'})

    # Private chat messages
    if chat_key not in messages:
        return jsonify({'error': 'Message not found'}), 404

    chat_msgs = messages[chat_key]
    app.logger.info('[report_message] incoming', extra={
        'chat_key': chat_key,
        'len': len(chat_msgs),
        'incoming_index': message_index,
        'sender_hint': sender_hint,
        'preview_hint': preview_hint,
        'timestamp_hint': timestamp_hint,
        'reporter': reporter
    })

    def normalize_text(val):
        return str(val or '').strip().lower()

    def build_preview_text(m):
        mtype = m.get('type', 'text')
        if mtype == 'snap':
            return '📸 [Snap Message]'
        if mtype == 'voice':
            return '🎤 [Voice Message]'
        return m.get('text', '[Message]')

    # Validate provided index first
    if not (0 <= message_index < len(chat_msgs)):
        return jsonify({'error': 'Message not found'}), 404

    normalized_hint = normalize_text(preview_hint)
    hint_has_preview = normalized_hint not in ('', '[message]')
    ts_hint = str(timestamp_hint or '').strip()

    def preview_of(m):
        mtype = m.get('type', 'text')
        if mtype == 'snap':
            return '📸 [Snap Message]'
        if mtype == 'voice':
            return '🎤 [Voice Message]'
        if mtype == 'token_gift':
            return m.get('text', '🎁 Token Gift')
        return m.get('text', '[Message]')

    def matches_all(m, require_sender=False, require_preview=False, require_timestamp=False):
        if require_sender and sender_hint and m.get('from') != sender_hint:
            return False
        if require_timestamp and ts_hint:
            if str(m.get('timestamp', '')).strip() != ts_hint:
                return False
        if require_preview and hint_has_preview:
            if normalized_hint not in normalize_text(preview_of(m)):
                return False
        return True

    def search_messages(require_sender=False, require_preview=False, require_timestamp=False):
        for idx in range(len(chat_msgs) - 1, -1, -1):
            cand = chat_msgs[idx]
            if matches_all(cand, require_sender, require_preview, require_timestamp):
                return idx, cand
        return None, None

    # Priority: exact timestamp+sender+preview -> timestamp+sender -> sender+preview -> timestamp -> sender -> preview -> provided index
    chosen_idx, msg = (None, None)
    search_order = [
        (True, True, True),
        (True, False, True),
        (True, True, False),
        (False, False, True),
        (True, False, False),
        (False, True, False),
    ]
    for req_sender, req_preview, req_ts in search_order:
        if (req_sender and not sender_hint) or (req_preview and not hint_has_preview) or (req_ts and not ts_hint):
            continue
        chosen_idx, msg = search_messages(req_sender, req_preview, req_ts)
        if msg:
            break

    # Fallback to provided index if no match found via hints
    if not msg:
        chosen_idx = message_index
        msg = chat_msgs[message_index]

    app.logger.info('[report_message] resolved', extra={
        'resolved_index': chosen_idx,
        'resolved_sender': msg.get('from'),
        'resolved_type': msg.get('type'),
        'resolved_preview': preview_of(msg),
        'resolved_timestamp': msg.get('timestamp', '')
    })

    # Can't report your own messages
    if msg.get('from') == reporter:
        return jsonify({'error': 'Cannot report your own message'}), 400

    # Use resolved index for duplicate check
    for report in reported_messages:
        if report['chat_key'] == chat_key and report['message_index'] == chosen_idx:
            return jsonify({'error': 'Message already reported'}), 400

    msg_type = msg.get('type', 'text')
    content_preview = preview_of(msg)

    report = {
        'id': len(reported_messages) + 1,
        'chat_key': chat_key,
        'message_index': chosen_idx,
        'message_content': content_preview,
        'message_type': msg_type,
        'sender': msg.get('from'),
        'reporter': reporter,
        'reason': reason,
        'status': 'pending',  # pending, dismissed, warned, banned
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
        'resolved_by': None,
        'resolved_at': None,
        'resolution_note': None
    }

    reported_messages.insert(0, report)
    save_json(REPORTED_MESSAGES_FILE, reported_messages)

    return jsonify({'success': True, 'message': 'Report submitted'})

@app.route('/api/reported_messages')
@login_required
def get_reported_messages():
    """Get all reported messages (for moderators)"""
    if not has_permission(session['username'], 'view_reported_messages'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    # Filter by status if requested
    status = request.args.get('status', 'all')

    if status == 'all':
        filtered = reported_messages
    else:
        filtered = [r for r in reported_messages if r['status'] == status]

    return jsonify({'success': True, 'reports': filtered})

@app.route('/api/resolve_report/<int:report_id>', methods=['POST'])
@login_required
def resolve_report(report_id):
    """Resolve a reported message"""
    if not has_permission(session['username'], 'view_reported_messages'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.json
    action = data.get('action')  # dismiss, warn, ban
    reason = data.get('reason', '')

    if action not in ['dismiss', 'warn', 'ban']:
        return jsonify({'success': False, 'error': 'Invalid action'}), 400

    # Require reason for all actions
    if not reason:
        return jsonify({'success': False, 'error': 'Reason is required'}), 400

    # Find the report
    report = None
    for r in reported_messages:
        if r['id'] == report_id:
            report = r
            break

    if not report:
        return jsonify({'success': False, 'error': 'Report not found'}), 404

    if report['status'] != 'pending':
        return jsonify({'success': False, 'error': 'Report already resolved'}), 400

    actor = session['username']

    # Update report
    report['status'] = action + 'ed' if action != 'ban' else 'banned'
    report['resolved_by'] = actor
    report['resolved_at'] = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    report['resolution_note'] = reason

    # If banning, actually ban the user
    if action == 'ban':
        sender = report['sender']
        if sender in users and sender != 'admin':
            users[sender]['banned'] = True
            users[sender]['ban_reason'] = f"Banned for reported message: {reason}"
            save_json(USERS_FILE, users)

    save_json(REPORTED_MESSAGES_FILE, reported_messages)

    # Log the action
    log_action(
        actor=actor,
        action_type=f'resolve_report_{action}',
        target=report['sender'],
        details=f"Report #{report_id} - {report['message_content'][:50]}",
        reason=reason
    )

    return jsonify({'success': True})


# ===============================================================
# PAYCHECK ROUTES
# ===============================================================

@app.route('/api/paychecks')
@login_required
def get_paychecks():
    """Get paycheck information"""
    username = session['username']
    user_role = users[username].get('role', 'user')

    # Calculate next Monday
    now = get_ny_time()
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = now + timedelta(days=days_until_monday)
    next_monday = next_monday.replace(hour=23, minute=59, second=59)

    response = {
        'success': True,
        'next_payday': next_monday.strftime('%Y-%m-%d %H:%M:%S'),
        'days_until_payday': days_until_monday
    }

    # If admin or president, show all pending paychecks
    if user_role in ['admin', 'president']:
        response['pending'] = paychecks.get('pending', [])
        response['history'] = paychecks.get('history', [])[:50]
        response['can_approve'] = True
    elif user_role in ['economy_director', 'pr_director', 'master_moderator']:
        # Show only their own paycheck status
        my_pending = [p for p in paychecks.get('pending', []) if p['username'] == username]
        my_history = [p for p in paychecks.get('history', []) if p['username'] == username][:20]
        response['pending'] = my_pending  # Changed from 'my_pending' to 'pending' for consistency
        response['history'] = my_history  # Changed from 'my_history' to 'history' for consistency
        response['my_role'] = STAFF_ROLES.get(user_role, {})
        response['can_approve'] = False
    else:
        response['can_approve'] = False

    return jsonify(response)

@app.route('/api/generate_paychecks', methods=['POST'])
@login_required
def generate_paychecks():
    """Generate weekly paychecks (usually automated, but can be manual)"""
    if not has_permission(session['username'], 'approve_paychecks'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    # Check if paychecks already generated this week
    now = get_ny_time()
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0)

    for pending in paychecks.get('pending', []):
        pending_time = datetime.strptime(pending['generated_at'], '%Y-%m-%d %H:%M:%S')
        if pending_time >= week_start.replace(tzinfo=None):
            return jsonify({'success': False, 'error': 'Paychecks already generated this week'}), 400

    # Generate paychecks for all eligible roles
    generated = []
    for uname, user_data in users.items():
        role = user_data.get('role', 'user')
        role_info = STAFF_ROLES.get(role, {})
        weekly_pay = role_info.get('weekly_pay', 0)

        if weekly_pay > 0:
            paycheck = {
                'id': len(paychecks.get('pending', [])) + len(paychecks.get('history', [])) + 1,
                'username': uname,
                'role': role,
                'base_amount': weekly_pay,
                'final_amount': weekly_pay,
                'adjustment': 0,
                'adjustment_reason': None,
                'status': 'pending',
                'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'approved_at': None,
                'approved_by': None,
                'president_note': None,
                'admin_feedback': None
            }
            if 'pending' not in paychecks:
                paychecks['pending'] = []
            paychecks['pending'].append(paycheck)
            generated.append(paycheck)

    save_json(PAYCHECKS_FILE, paychecks)

    return jsonify({'success': True, 'count': len(generated)})


@app.route('/api/adjust_paycheck/<int:paycheck_id>', methods=['POST'])
@login_required
def adjust_paycheck(paycheck_id):
    """Adjust a pending paycheck amount (President only)"""
    if not has_permission(session['username'], 'approve_paychecks'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.json
    new_amount = data.get('amount')
    reason = data.get('reason', '')

    if new_amount is None or new_amount < 0:
        return jsonify({'success': False, 'error': 'Invalid amount'}), 400

    if not reason:
        return jsonify({'success': False, 'error': 'Reason is required for adjustment'}), 400

    # Find the paycheck
    for paycheck in paychecks.get('pending', []):
        if paycheck['id'] == paycheck_id:
            original = paycheck['base_amount']
            paycheck['final_amount'] = new_amount
            paycheck['adjustment'] = new_amount - original
            paycheck['adjustment_reason'] = reason
            save_json(PAYCHECKS_FILE, paychecks)

            log_action(
                actor=session['username'],
                action_type='adjust_paycheck',
                target=paycheck['username'],
                details=f"Adjusted from {original} to {new_amount}",
                reason=reason
            )

            return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Paycheck not found'}), 404


@app.route('/api/approve_paycheck/<int:paycheck_id>', methods=['POST'])
@login_required
def approve_paycheck(paycheck_id):
    """Approve a pending paycheck"""
    if not has_permission(session['username'], 'approve_paychecks'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.json
    president_note = data.get('president_note', '')
    admin_feedback = data.get('admin_feedback', '')

    if not president_note:
        return jsonify({'success': False, 'error': 'Note to recipient is required'}), 400

    actor = session['username']
    actor_role = users[actor].get('role', 'user')

    # President must provide admin feedback
    if actor_role == 'president' and not admin_feedback:
        return jsonify({'success': False, 'error': 'Feedback to admin is required'}), 400

    # Find and approve the paycheck
    for i, paycheck in enumerate(paychecks.get('pending', [])):
        if paycheck['id'] == paycheck_id:
            recipient = paycheck['username']
            amount = paycheck['final_amount']

            # Pay the user
            if recipient in users:
                users[recipient]['tokens'] = users[recipient].get('tokens', 0) + amount
                save_json(USERS_FILE, users)

                # Log the transaction
                log_transaction(
                    transaction_type='creation',
                    amount=amount,
                    user=recipient,
                    source='weekly_paycheck',
                    details=f"Weekly paycheck for {paycheck['role']}"
                )

            # Update paycheck record
            paycheck['status'] = 'approved'
            paycheck['approved_at'] = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
            paycheck['approved_by'] = actor
            paycheck['president_note'] = president_note
            paycheck['admin_feedback'] = admin_feedback

            # Move to history
            paychecks['pending'].pop(i)
            if 'history' not in paychecks:
                paychecks['history'] = []
            paychecks['history'].insert(0, paycheck)

            save_json(PAYCHECKS_FILE, paychecks)

            # Send notification to recipient
            if recipient in login_notifications:
                if not isinstance(login_notifications[recipient], list):
                    login_notifications[recipient] = []
            else:
                login_notifications[recipient] = []

            login_notifications[recipient].append({
                'type': 'paycheck_approved',
                'message': f'Your paycheck of {amount} 🎟️ has been approved!',
                'note': president_note,
                'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
                'approved_by': actor
            })
            save_json(LOGIN_NOTIFICATIONS_FILE, login_notifications)

            log_action(
                actor=actor,
                action_type='approve_paycheck',
                target=recipient,
                details=f"Approved {amount} 🎟️ paycheck",
                reason=president_note
            )

            return jsonify({'success': True, 'amount': amount})

    return jsonify({'success': False, 'error': 'Paycheck not found'}), 404


# ===============================================================
# ACTION LOG ROUTES
# ===============================================================

@app.route('/api/action_logs')
@login_required
def get_action_logs():
    """Get action logs (Admin and President only)"""
    if not has_permission(session['username'], 'view_action_logs'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    action_type = request.args.get('action_type', 'all')
    limit = int(request.args.get('limit', 100))

    if action_type == 'all':
        filtered = action_logs[:limit]
    else:
        filtered = [log for log in action_logs if log['action_type'] == action_type][:limit]

    # Get unique action types for filter
    action_types = list(set(log['action_type'] for log in action_logs))

    return jsonify({
        'success': True,
        'logs': filtered,
        'action_types': sorted(action_types)
    })


# ===============================================================
# TOKEN STATISTICS ROUTES
# ===============================================================

@app.route('/api/token_statistics')
@login_required
def get_token_stats_api():
    """Get token statistics (Economy Director+)"""
    if not has_permission(session['username'], 'view_token_stats'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    stats = get_token_statistics()

    # Calculate totals for the frontend
    created_total = sum(stats.get('created_by_source', {}).values())
    destroyed_total = sum(stats.get('destroyed_by_source', {}).values())

    # Add per-user breakdown if requested
    user_filter = request.args.get('user')
    user_transactions = None
    if user_filter:
        user_transactions = [tx for tx in token_transactions if tx['user'] == user_filter][:100]

    return jsonify({
        'success': True,
        'total_circulation': stats['total_circulation'],
        'created_by_source': stats.get('created_by_source', {}),
        'destroyed_by_source': stats.get('destroyed_by_source', {}),
        'created_total': created_total,
        'destroyed_total': destroyed_total,
        'daily_totals': stats.get('daily_totals', {}),
        'total_transactions': stats.get('total_transactions', 0),
        'user_transactions': user_transactions
    })

@app.route('/api/casino_statistics')
@login_required
def get_casino_stats_api():
    """Get casino statistics (Economy Director+)"""
    if not has_permission(session['username'], 'view_casino_stats'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    stats = get_casino_statistics()

    # Add daily breakdown for graphs
    daily_stats = {}
    for game_type in ['coinflip', 'tower', 'blackjack']:
        daily_stats[game_type] = {}
        for game in casino_stats.get(game_type, []):
            date = game['timestamp'].split(' ')[0]
            if date not in daily_stats[game_type]:
                daily_stats[game_type][date] = {'profit': 0, 'games': 0}
            daily_stats[game_type][date]['games'] += 1
            if not game['won']:
                daily_stats[game_type][date]['profit'] += abs(game['profit_loss'])
            else:
                daily_stats[game_type][date]['profit'] -= game['profit_loss']

    # Get lottery history with profit calculation
    lottery_hist = []
    for lottery in lottery_history[:20]:
        tickets_sold = lottery.get('total_tickets', 0)
        ticket_price = lottery.get('ticket_price', 0)
        prize_pool = lottery.get('prize_pool', 0)
        revenue = tickets_sold * ticket_price
        profit = revenue - prize_pool
        lottery_entry = dict(lottery)
        lottery_entry['profit'] = profit
        lottery_entry['revenue'] = revenue
        lottery_entry['tickets_sold'] = tickets_sold
        lottery_hist.append(lottery_entry)

    return jsonify({
        'success': True,
        'coinflip': stats.get('coinflip', {'total_games': 0, 'house_profit': 0}),
        'tower': stats.get('tower', {'total_games': 0, 'house_profit': 0}),
        'blackjack': stats.get('blackjack', {'total_games': 0, 'house_profit': 0}),
        'rps': stats.get('rps', {'total_games': 0, 'total_pot': 0}),
        'daily_breakdown': daily_stats,
        'lottery_history': lottery_hist
    })

@app.route('/api/lottery_statistics')
@login_required
def get_lottery_stats_api():
    """Get lottery statistics (Economy Director+)"""
    if not has_permission(session['username'], 'view_casino_stats'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    # Calculate total lottery profit
    total_profit = 0
    history_with_profit = []
    for lottery in lottery_history:
        tickets_sold = lottery.get('total_tickets', 0)
        ticket_price = lottery.get('ticket_price', 0)
        prize_pool = lottery.get('prize_pool', 0)
        revenue = tickets_sold * ticket_price
        profit = revenue - prize_pool
        lottery_entry = dict(lottery)
        lottery_entry['profit'] = profit
        lottery_entry['revenue'] = revenue
        history_with_profit.append(lottery_entry)
        total_profit += profit

    return jsonify({
        'success': True,
        'history': history_with_profit[:50],
        'total_profit': total_profit,
        'total_lotteries': len(lottery_history)
    })

# ===============================================================
# ROLE MANAGEMENT ROUTES
# ===============================================================

@app.route('/api/assign_role/<username>', methods=['POST'])
@login_required
def assign_role(username):
    """Assign a role to a user"""
    if not has_permission(session['username'], 'assign_roles'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    if username not in users:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    if username == 'admin':
        return jsonify({'success': False, 'error': 'Cannot change admin role'}), 400

    data = request.json
    new_role = data.get('role')
    reason = data.get('reason', '')

    if not reason:
        return jsonify({'success': False, 'error': 'Reason is required'}), 400

    if new_role not in STAFF_ROLES:
        return jsonify({'success': False, 'error': 'Invalid role'}), 400

    old_role = users[username].get('role', 'user')
    users[username]['role'] = new_role
    save_json(USERS_FILE, users)

    log_action(
        actor=session['username'],
        action_type='assign_role',
        target=username,
        details=f"Changed role from {old_role} to {new_role}",
        reason=reason
    )

    return jsonify({'success': True, 'old_role': old_role, 'new_role': new_role})

def get_gmail_service(username):
    """Get Gmail API service for a user"""
    if username not in gmail_tokens:
        return None

    token_data = gmail_tokens[username]
    creds = Credentials(
        token=token_data['token'],
        refresh_token=token_data.get('refresh_token'),
        token_uri=token_data['token_uri'],
        client_id=token_data['client_id'],
        client_secret=token_data['client_secret'],
        scopes=token_data['scopes']
    )

    # Refresh token if expired
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())

        # Save refreshed token
        gmail_tokens[username] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        save_json(GMAIL_TOKENS_FILE, gmail_tokens)

    return build('gmail', 'v1', credentials=creds)

@app.route('/gmail')
@maintenance_check
@login_required
def gmail_page():
    """Gmail inbox page"""
    username = session['username']

    # FORCE: Check if user has purchased access (admins bypass)
    is_admin = users.get(username, {}).get('role') == 'admin'
    has_purchased = username in site_access and 'gmail' in site_access.get(username, [])

    # If not admin and hasn't purchased, BLOCK access and clear any tokens
    if not is_admin and not has_purchased:
        # Clear any existing Gmail tokens if they haven't purchased
        if username in gmail_tokens:
            del gmail_tokens[username]
            save_json(GMAIL_TOKENS_FILE, gmail_tokens)
        return redirect(url_for('proxy'))

    unread_count = get_unread_count(username)  # Only count private chat messages
    group_unread_count = get_total_group_unread_count(username)  # Track group messages separately
    lounge_unread_count = get_lounge_unread_count(username)

    # Check if user has Gmail connected
    has_gmail = username in gmail_tokens
    gmail_email = None

    if has_gmail:
        try:
            service = get_gmail_service(username)
            if service:
                profile = service.users().getProfile(userId='me').execute()
                gmail_email = profile.get('emailAddress')
        except Exception as e:
            print(f"Error getting Gmail profile: {e}")
            has_gmail = False

    return render_template('gmail.html',
        username=username,
        has_gmail=has_gmail,
        gmail_email=gmail_email,
        unread_count=unread_count,
        group_unread_count=group_unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role']
    )

@app.route('/oauth/authorize')
@login_required
def oauth_authorize():
    username = session['username']

    # FORCE: Check if user has purchased access (admins bypass)
    is_admin = users.get(username, {}).get('role') == 'admin'
    has_purchased = username in site_access and 'gmail' in site_access.get(username, [])

    if not is_admin and not has_purchased:
        return redirect(url_for('proxy'))

    # Use https on production, http on local dev if you want.
    if os.getenv("FLASK_ENV") == "production":
        redirect_uri = url_for('oauth_callback', _external=True, _scheme='https')
    else:
        redirect_uri = url_for('oauth_callback', _external=True)

    flow = Flow.from_client_secrets_file(
        GMAIL_CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    session['oauth_state'] = state
    session['oauth_username'] = username

    return redirect(authorization_url)


@app.route('/oauth/callback')
def oauth_callback():
    if 'oauth_state' not in session:
        return "Invalid OAuth state", 400

    username = session.get('oauth_username')
    if not username:
        return "Invalid session", 400

    if os.getenv("FLASK_ENV") == "production":
        redirect_uri = url_for('oauth_callback', _external=True, _scheme='https')
    else:
        redirect_uri = url_for('oauth_callback', _external=True)

    flow = Flow.from_client_secrets_file(
        GMAIL_CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        state=session['oauth_state']
    )

    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    gmail_tokens[username] = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    save_json(GMAIL_TOKENS_FILE, gmail_tokens)

    session.pop('oauth_state', None)
    session.pop('oauth_username', None)

    return redirect(url_for('gmail_page'))


@app.route('/oauth/disconnect', methods=['POST'])
@login_required
def oauth_disconnect():
    """Disconnect Gmail account"""
    username = session['username']

    if username in gmail_tokens:
        del gmail_tokens[username]
        save_json(GMAIL_TOKENS_FILE, gmail_tokens)

    return jsonify({'success': True})

@app.route('/api/gmail/messages')
@login_required
def get_gmail_messages():
    """Get Gmail messages"""
    username = session['username']

    # FORCE: Check if user has purchased access (admins bypass)
    is_admin = users.get(username, {}).get('role') == 'admin'
    has_purchased = username in site_access and 'gmail' in site_access.get(username, [])

    if not is_admin and not has_purchased:
        return jsonify({'error': 'Access denied - Purchase required'}), 403

    if username not in gmail_tokens:
        return jsonify({'error': 'Gmail not connected'}), 400

    try:
        service = get_gmail_service(username)
        if not service:
            return jsonify({'error': 'Failed to connect to Gmail'}), 500

        # Get query parameters
        max_results = int(request.args.get('max_results', 20))
        page_token = request.args.get('page_token')
        query = request.args.get('q', '')  # Search query
        label_id = request.args.get('label', 'INBOX')  # Default to INBOX

        # List messages
        list_params = {
            'userId': 'me',
            'maxResults': max_results,
            'labelIds': [label_id]
        }

        if page_token:
            list_params['pageToken'] = page_token
        if query:
            list_params['q'] = query

        results = service.users().messages().list(**list_params).execute()

        messages = results.get('messages', [])
        next_page_token = results.get('nextPageToken')

        # Get full message details
        message_list = []
        for msg in messages:
            message = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='metadata',
                metadataHeaders=['From', 'To', 'Subject', 'Date']
            ).execute()

            headers = {h['name']: h['value'] for h in message['payload']['headers']}
            labels = message.get('labelIds', [])

            message_list.append({
                'id': message['id'],
                'thread_id': message['threadId'],
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', '(No Subject)'),
                'date': headers.get('Date', ''),
                'snippet': message.get('snippet', ''),
                'labels': labels,
                'unread': 'UNREAD' in labels
            })

        return jsonify({
            'success': True,
            'messages': message_list,
            'next_page_token': next_page_token
        })

    except Exception as e:
        print(f"Error fetching Gmail messages: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/message/<message_id>')
@login_required
def get_gmail_message(message_id):
    """Get full Gmail message"""
    username = session['username']

    # FORCE: Check if user has purchased access (admins bypass)
    is_admin = users.get(username, {}).get('role') == 'admin'
    has_purchased = username in site_access and 'gmail' in site_access.get(username, [])

    if not is_admin and not has_purchased:
        return jsonify({'error': 'Access denied - Purchase required'}), 403

    if username not in gmail_tokens:
        return jsonify({'error': 'Gmail not connected'}), 400

    try:
        service = get_gmail_service(username)
        if not service:
            return jsonify({'error': 'Failed to connect to Gmail'}), 500

        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in message['payload']['headers']}

        # Extract BOTH plain text and HTML
        def get_body(payload):
            plain_text = ''
            html_text = ''

            if 'body' in payload and payload['body'].get('data'):
                data = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
                if payload.get('mimeType') == 'text/html':
                    html_text = data
                else:
                    plain_text = data
            elif 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                        plain_text = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    elif part['mimeType'] == 'text/html' and 'data' in part['body']:
                        html_text = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    # Recursively search in nested parts
                    elif 'parts' in part:
                        nested_plain, nested_html = get_body(part)
                        if not plain_text:
                            plain_text = nested_plain
                        if not html_text:
                            html_text = nested_html

            return plain_text, html_text

        plain_body, html_body = get_body(message['payload'])

        return jsonify({
            'success': True,
            'message': {
                'id': message['id'],
                'thread_id': message['threadId'],
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', '(No Subject)'),
                'date': headers.get('Date', ''),
                'body_plain': plain_body,
                'body_html': html_body,
                'labels': message.get('labelIds', [])
            }
        })

    except Exception as e:
        print(f"Error fetching Gmail message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/send', methods=['POST'])
@login_required
def send_gmail_message():
    """Send a Gmail message"""
    username = session['username']

    # FORCE: Check if user has purchased access (admins bypass)
    is_admin = users.get(username, {}).get('role') == 'admin'
    has_purchased = username in site_access and 'gmail' in site_access.get(username, [])

    if not is_admin and not has_purchased:
        return jsonify({'error': 'Access denied - Purchase required'}), 403

    if username not in gmail_tokens:
        return jsonify({'error': 'Gmail not connected'}), 400

    try:
        service = get_gmail_service(username)
        if not service:
            return jsonify({'error': 'Failed to connect to Gmail'}), 500

        data = request.json
        to = data.get('to')
        subject = data.get('subject')
        body = data.get('body')

        if not to or not subject or not body:
            return jsonify({'error': 'Missing required fields'}), 400

        # Create message
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        sent_message = service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()

        return jsonify({
            'success': True,
            'message_id': sent_message['id']
        })

    except Exception as e:
        print(f"Error sending Gmail message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/mark_read/<message_id>', methods=['POST'])
@login_required
def mark_gmail_read(message_id):
    """Mark a Gmail message as read"""
    username = session['username']

    # FORCE: Check if user has purchased access (admins bypass)
    is_admin = users.get(username, {}).get('role') == 'admin'
    has_purchased = username in site_access and 'gmail' in site_access.get(username, [])

    if not is_admin and not has_purchased:
        return jsonify({'error': 'Access denied - Purchase required'}), 403

    if username not in gmail_tokens:
        return jsonify({'error': 'Gmail not connected'}), 400

    try:
        service = get_gmail_service(username)
        if not service:
            return jsonify({'error': 'Failed to connect to Gmail'}), 500

        # Remove UNREAD label
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error marking message as read: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/mark_unread/<message_id>', methods=['POST'])
@login_required
def mark_gmail_unread(message_id):
    """Mark a Gmail message as unread"""
    username = session['username']

    # FORCE: Check if user has purchased access (admins bypass)
    is_admin = users.get(username, {}).get('role') == 'admin'
    has_purchased = username in site_access and 'gmail' in site_access.get(username, [])

    if not is_admin and not has_purchased:
        return jsonify({'error': 'Access denied - Purchase required'}), 403

    if username not in gmail_tokens:
        return jsonify({'error': 'Gmail not connected'}), 400

    try:
        service = get_gmail_service(username)
        if not service:
            return jsonify({'error': 'Failed to connect to Gmail'}), 500

        # Add UNREAD label
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'addLabelIds': ['UNREAD']}
        ).execute()

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error marking message as unread: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gmail/delete/<message_id>', methods=['POST'])
@login_required
def delete_gmail_message(message_id):
    """Delete a Gmail message (move to trash)"""
    username = session['username']

    # FORCE: Check if user has purchased access (admins bypass)
    is_admin = users.get(username, {}).get('role') == 'admin'
    has_purchased = username in site_access and 'gmail' in site_access.get(username, [])

    if not is_admin and not has_purchased:
        return jsonify({'error': 'Access denied - Purchase required'}), 403

    if username not in gmail_tokens:
        return jsonify({'error': 'Gmail not connected'}), 400

    try:
        service = get_gmail_service(username)
        if not service:
            return jsonify({'error': 'Failed to connect to Gmail'}), 500

        # Move to trash
        service.users().messages().trash(
            userId='me',
            id=message_id
        ).execute()

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error deleting message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/user_chats/<username>')
@admin_required
def get_user_chats(username):
    """Get all chat histories for a specific user (admin only)"""
    if username not in users:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    user_chats = []

    # Go through all message keys
    for chat_key, chat_messages in messages.items():
        participants = chat_key.split('-')

        # Check if this user is in the chat
        if username not in participants:
            continue

        # Get the other user
        other_user = participants[0] if participants[1] == username else participants[1]

        # Filter messages to only those involving this user
        relevant_messages = []
        for msg in chat_messages:
            message_data = {
                'from': msg.get('from'),
                'to': msg.get('to'),
                'text': msg.get('text', '[Media Message]'),
                'type': msg.get('type', 'text'),
                'timestamp': msg.get('timestamp'),
                'read': msg.get('read', False)
            }

            # Include snap data if it's a snap
            if msg.get('type') == 'snap':
                message_data['photo'] = msg.get('photo')
                message_data['opened'] = msg.get('opened', False)

            # Include voice message data
            if msg.get('type') == 'voice':
                message_data['audio'] = msg.get('audio')
                message_data['duration'] = msg.get('duration', 0)

            relevant_messages.append(message_data)

        if relevant_messages:
            user_chats.append({
                'chat_key': chat_key,
                'other_user': other_user,
                'message_count': len(relevant_messages),
                'messages': relevant_messages,
                'last_message': relevant_messages[-1] if relevant_messages else None
            })

    # Sort by last message timestamp
    user_chats.sort(key=lambda x: x['last_message']['timestamp'] if x['last_message'] else '', reverse=True)

    return jsonify({
        'success': True,
        'username': username,
        'chats': user_chats,
        'total_chats': len(user_chats)
    })


# ===============================================================
# BLACKJACK GAME API
# ===============================================================

# Store active blackjack games in memory
blackjack_games = {}

def create_deck():
    """Create a standard 52-card deck"""
    suits = ['♠️', '♥️', '♦️', '♣️']
    ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
    deck = []
    for suit in suits:
        for rank in ranks:
            deck.append({'rank': rank, 'suit': suit})
    random.shuffle(deck)
    return deck

def calculate_hand_value(hand):
    """Calculate the value of a blackjack hand"""
    value = 0
    aces = 0

    for card in hand:
        rank = card['rank']
        if rank in ['J', 'Q', 'K']:
            value += 10
        elif rank == 'A':
            aces += 1
            value += 11
        else:
            value += int(rank)

    # Adjust for aces
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1

    return value

@app.route('/api/blackjack/start', methods=['POST'])
@login_required
def blackjack_start():
    """Start a new blackjack game"""
    username = session['username']
    data = request.json
    bet_amount = data.get('amount')

    # Validation
    if not bet_amount:
        return jsonify({'error': 'Invalid request'}), 400

    try:
        bet_amount = int(bet_amount)
    except ValueError:
        return jsonify({'error': 'Invalid bet amount'}), 400

    if bet_amount < 20:
        return jsonify({'error': 'Minimum bet is 20 tokens'}), 400

    user_tokens = users[username].get('tokens', 0)
    if user_tokens < bet_amount:
        return jsonify({'error': 'Insufficient tokens'}), 400

    # Deduct bet
    users[username]['tokens'] -= bet_amount
    save_json(USERS_FILE, users)

    # Create new game
    deck = create_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    game_id = f"{username}_{int(get_ny_time().timestamp())}"

    blackjack_games[game_id] = {
        'username': username,
        'bet': bet_amount,
        'deck': deck,
        'player_hand': player_hand,
        'dealer_hand': dealer_hand,
        'status': 'active',  # active, player_blackjack, dealer_blackjack, push, player_wins, dealer_wins
        'doubled': False,
        'split_hand': None,
        'current_hand': 'main'  # main or split
    }

    player_value = calculate_hand_value(player_hand)
    dealer_value = calculate_hand_value(dealer_hand)

    # Check for natural blackjack
    player_blackjack = (len(player_hand) == 2 and player_value == 21)
    dealer_blackjack = (len(dealer_hand) == 2 and dealer_value == 21)

    if player_blackjack and dealer_blackjack:
        # Push - return bet
        users[username]['tokens'] += bet_amount
        save_json(USERS_FILE, users)
        blackjack_games[game_id]['status'] = 'push'
        return jsonify({
            'success': True,
            'game_id': game_id,
            'player_hand': player_hand,
            'dealer_hand': dealer_hand,
            'player_value': player_value,
            'dealer_value': dealer_value,
            'status': 'push',
            'message': 'Push! Both have Blackjack.',
            'new_balance': users[username]['tokens']
        })
    elif player_blackjack:
        # Player blackjack - pay 3:2
        winnings = int(bet_amount * 2.5)  # Bet + 1.5x payout
        users[username]['tokens'] += winnings
        save_json(USERS_FILE, users)
        blackjack_games[game_id]['status'] = 'player_blackjack'
        log_casino_game('blackjack', username, bet_amount, True, winnings - bet_amount)
        log_transaction('creation', winnings - bet_amount, username, 'casino_blackjack')
        return jsonify({
            'success': True,
            'game_id': game_id,
            'player_hand': player_hand,
            'dealer_hand': dealer_hand,
            'player_value': player_value,
            'dealer_value': dealer_value,
            'status': 'player_blackjack',
            'message': f'Blackjack! Won {winnings - bet_amount} tokens!',
            'payout': winnings - bet_amount,
            'new_balance': users[username]['tokens']
        })
    elif dealer_blackjack:
        # Dealer blackjack - player loses
        blackjack_games[game_id]['status'] = 'dealer_blackjack'
        log_casino_game('blackjack', username, bet_amount, False, -bet_amount)
        log_transaction('destruction', bet_amount, username, 'casino_blackjack')
        return jsonify({
            'success': True,
            'game_id': game_id,
            'player_hand': player_hand,
            'dealer_hand': dealer_hand,
            'player_value': player_value,
            'dealer_value': dealer_value,
            'status': 'dealer_blackjack',
            'message': 'Dealer has Blackjack. You lose.',
            'new_balance': users[username]['tokens']
        })

    return jsonify({
        'success': True,
        'game_id': game_id,
        'player_hand': player_hand,
        'dealer_hand': dealer_hand,  # Send full hand
        'dealer_hidden': True,
        'player_value': player_value,
        'status': 'active',
        'can_split': (player_hand[0]['rank'] == player_hand[1]['rank']),
        'can_double': True,
        'new_balance': users[username]['tokens']
    })

@app.route('/api/blackjack/hit/<game_id>', methods=['POST'])
@login_required
def blackjack_hit(game_id):
    """Player hits"""
    username = session['username']

    if game_id not in blackjack_games:
        return jsonify({'error': 'Game not found'}), 404

    game = blackjack_games[game_id]

    if game['username'] != username:
        return jsonify({'error': 'Not your game'}), 403

    if game['status'] != 'active':
        return jsonify({'error': 'Game is not active'}), 400

    # Draw card
    card = game['deck'].pop()
    game['player_hand'].append(card)

    player_value = calculate_hand_value(game['player_hand'])

    # Check for bust
    if player_value > 21:
        game['status'] = 'dealer_wins'
        log_casino_game('blackjack', username, game['bet'], False, -game['bet'])
        log_transaction('destruction', game['bet'], username, 'casino_blackjack')
        return jsonify({
            'success': True,
            'card': card,
            'player_hand': game['player_hand'],
            'player_value': player_value,
            'status': 'bust',
            'message': 'Bust! You lose.',
            'new_balance': users[username]['tokens']
        })

    return jsonify({
        'success': True,
        'card': card,
        'player_hand': game['player_hand'],
        'player_value': player_value,
        'status': 'active',
        'can_double': False  # Can't double after hit
    })

@app.route('/api/blackjack/stand/<game_id>', methods=['POST'])
@login_required
def blackjack_stand(game_id):
    """Player stands - dealer plays"""
    username = session['username']

    if game_id not in blackjack_games:
        return jsonify({'error': 'Game not found'}), 404

    game = blackjack_games[game_id]

    if game['username'] != username:
        return jsonify({'error': 'Not your game'}), 403

    if game['status'] != 'active':
        return jsonify({'error': 'Game is not active'}), 400

    # Dealer plays - must hit until 17
    dealer_hand = game['dealer_hand']
    dealer_value = calculate_hand_value(dealer_hand)

    while dealer_value < 17:
        card = game['deck'].pop()
        dealer_hand.append(card)
        dealer_value = calculate_hand_value(dealer_hand)

    player_value = calculate_hand_value(game['player_hand'])

    # Determine winner
    if dealer_value > 21:
        # Dealer bust - player wins
        winnings = game['bet'] * 2
        users[username]['tokens'] += winnings
        save_json(USERS_FILE, users)
        game['status'] = 'player_wins'
        log_casino_game('blackjack', username, game['bet'], True, game['bet'])
        log_transaction('creation', game['bet'], username, 'casino_blackjack')
        message = f'Dealer busts! Won {game["bet"]} tokens!'
        payout = game['bet']
    elif player_value > dealer_value:
        # Player wins
        winnings = game['bet'] * 2
        users[username]['tokens'] += winnings
        save_json(USERS_FILE, users)
        game['status'] = 'player_wins'
        log_casino_game('blackjack', username, game['bet'], True, game['bet'])
        log_transaction('creation', game['bet'], username, 'casino_blackjack')
        message = f'You win! Won {game["bet"]} tokens!'
        payout = game['bet']
    elif player_value < dealer_value:
        # Dealer wins
        game['status'] = 'dealer_wins'
        log_casino_game('blackjack', username, game['bet'], False, -game['bet'])
        log_transaction('destruction', game['bet'], username, 'casino_blackjack')
        message = 'Dealer wins. You lose.'
        payout = 0
    else:
        # Push - return bet
        users[username]['tokens'] += game['bet']
        save_json(USERS_FILE, users)
        game['status'] = 'push'
        message = 'Push! Tie game.'
        payout = 0

    return jsonify({
        'success': True,
        'dealer_hand': dealer_hand,
        'dealer_value': dealer_value,
        'player_value': player_value,
        'status': game['status'],
        'message': message,
        'payout': payout,
        'new_balance': users[username]['tokens']
    })

@app.route('/api/blackjack/double/<game_id>', methods=['POST'])
@login_required
def blackjack_double(game_id):
    """Player doubles down"""
    username = session['username']

    if game_id not in blackjack_games:
        return jsonify({'error': 'Game not found'}), 404

    game = blackjack_games[game_id]

    if game['username'] != username:
        return jsonify({'error': 'Not your game'}), 403

    if game['status'] != 'active':
        return jsonify({'error': 'Game is not active'}), 400

    if game['doubled']:
        return jsonify({'error': 'Already doubled'}), 400

    # Check if player has enough tokens
    if users[username].get('tokens', 0) < game['bet']:
        return jsonify({'error': 'Insufficient tokens to double'}), 400

    # Deduct additional bet
    users[username]['tokens'] -= game['bet']
    save_json(USERS_FILE, users)
    game['bet'] *= 2
    game['doubled'] = True

    # Draw one card
    card = game['deck'].pop()
    game['player_hand'].append(card)

    player_value = calculate_hand_value(game['player_hand'])

    # Check for bust
    if player_value > 21:
        game['status'] = 'dealer_wins'
        log_casino_game('blackjack', username, game['bet'], False, -game['bet'])
        log_transaction('destruction', game['bet'], username, 'casino_blackjack')
        return jsonify({
            'success': True,
            'card': card,
            'player_hand': game['player_hand'],
            'player_value': player_value,
            'status': 'bust',
            'message': 'Bust! You lose.',
            'new_balance': users[username]['tokens']
        })

    # Dealer plays automatically after double
    dealer_hand = game['dealer_hand']
    dealer_value = calculate_hand_value(dealer_hand)

    while dealer_value < 17:
        dealer_card = game['deck'].pop()
        dealer_hand.append(dealer_card)
        dealer_value = calculate_hand_value(dealer_hand)

    # Determine winner
    if dealer_value > 21:
        winnings = game['bet'] * 2
        users[username]['tokens'] += winnings
        save_json(USERS_FILE, users)
        game['status'] = 'player_wins'
        log_casino_game('blackjack', username, game['bet'], True, game['bet'])
        log_transaction('creation', game['bet'], username, 'casino_blackjack')
        message = f'Dealer busts! Won {game["bet"]} tokens!'
        payout = game['bet']
    elif player_value > dealer_value:
        winnings = game['bet'] * 2
        users[username]['tokens'] += winnings
        save_json(USERS_FILE, users)
        game['status'] = 'player_wins'
        log_casino_game('blackjack', username, game['bet'], True, game['bet'])
        log_transaction('creation', game['bet'], username, 'casino_blackjack')
        message = f'You win! Won {game["bet"]} tokens!'
        payout = game['bet']
    elif player_value < dealer_value:
        game['status'] = 'dealer_wins'
        log_casino_game('blackjack', username, game['bet'], False, -game['bet'])
        log_transaction('destruction', game['bet'], username, 'casino_blackjack')
        message = 'Dealer wins. You lose.'
        payout = 0
    else:
        users[username]['tokens'] += game['bet']
        save_json(USERS_FILE, users)
        game['status'] = 'push'
        message = 'Push! Tie game.'
        payout = 0

    return jsonify({
        'success': True,
        'card': card,
        'player_hand': game['player_hand'],
        'player_value': player_value,
        'dealer_hand': dealer_hand,
        'dealer_value': dealer_value,
        'status': game['status'],
        'message': message,
        'payout': payout,
        'new_balance': users[username]['tokens']
    })

@app.route('/api/blackjack/split/<game_id>', methods=['POST'])
@login_required
def blackjack_split(game_id):
    """Player splits pair"""
    username = session['username']

    if game_id not in blackjack_games:
        return jsonify({'error': 'Game not found'}), 404

    game = blackjack_games[game_id]

    if game['username'] != username:
        return jsonify({'error': 'Not your game'}), 403

    if game['status'] != 'active':
        return jsonify({'error': 'Game is not active'}), 400

    player_hand = game['player_hand']

    if len(player_hand) != 2 or player_hand[0]['rank'] != player_hand[1]['rank']:
        return jsonify({'error': 'Cannot split this hand'}), 400

    # Check if player has enough tokens
    if users[username].get('tokens', 0) < game['bet']:
        return jsonify({'error': 'Insufficient tokens to split'}), 400

    # Deduct additional bet
    users[username]['tokens'] -= game['bet']
    save_json(USERS_FILE, users)

    # Split the hand
    split_hand = [player_hand.pop()]
    split_hand.append(game['deck'].pop())
    player_hand.append(game['deck'].pop())

    game['split_hand'] = split_hand
    game['current_hand'] = 'main'

    return jsonify({
        'success': True,
        'player_hand': player_hand,
        'split_hand': split_hand,
        'player_value': calculate_hand_value(player_hand),
        'split_value': calculate_hand_value(split_hand),
        'status': 'split',
        'current_hand': 'main',
        'message': 'Hand split! Play your first hand.',
        'new_balance': users[username]['tokens']
    })


# ===============================================================
# LOUNGE WEBSOCKET EVENT HANDLERS
# ===============================================================

# Track users currently in lounge: {username: session_id}
lounge_users = {}

@socketio.on('connect')
def handle_connect():
    """Client connected to SocketIO"""
    username = session.get('username', 'anonymous')
    print(f"[SOCKETIO] Client connected: {username} (SID: {request.sid})")

    # Update user activity on connect
    if username and username != 'anonymous':
        user_activity[username] = get_ny_time().timestamp()

@socketio.on('presence_heartbeat')
def handle_presence_heartbeat():
    """Receive presence heartbeat from any page (including games)"""
    try:
        username = session.get('username')
        if username:
            user_activity[username] = get_ny_time().timestamp()
    except Exception as e:
        print(f"Error in presence_heartbeat: {e}")

@socketio.on('join_chat')
def handle_join_chat(data):
    """User joins their personal chat room for receiving snap updates"""
    try:
        username = data.get('username') or session.get('username')
        if not username:
            return

        # Join personal chat room for this user
        room_name = f'chat_{username}'
        join_room(room_name)
        print(f"User {username} joined room: {room_name}")
    except Exception as e:
        print(f"Error in join_chat: {e}")

@socketio.on('join_lounge')
def handle_join_lounge():
    """User joins the lounge room"""
    try:
        username = session.get('username')
        if not username:
            return

        # Add user to lounge room
        join_room('lounge')
        lounge_users[username] = request.sid

        # Get user's profile for broadcast
        profile = profiles.get(username, {})
        profile_picture = profile.get('profile_picture') if profile.get('setup_complete') else None

        # Broadcast to all in lounge that user joined
        emit('user_joined', {
            'username': username,
            'profile_picture': profile_picture
        }, room='lounge', skip_sid=request.sid)

        # Build current online users list
        online_users_list = []
        for user, sid in lounge_users.items():
            user_profile = profiles.get(user, {})
            user_pic = user_profile.get('profile_picture') if user_profile.get('setup_complete') else None
            staff_tag = get_lounge_staff_tag(user)
            rank = users.get(user, {}).get('rank')
            online_users_list.append({
                'username': user,
                'profile_picture': user_pic,
                'staff_tag': staff_tag,
                'rank': rank
            })

        # Send updated online users list to EVERYONE in the room (including joiner)
        emit('online_users_update', {'users': online_users_list}, room='lounge')

        print(f"[LOUNGE] {username} joined. Total users: {len(lounge_users)}")

    except Exception as e:
        print(f"Error in join_lounge: {e}")


@socketio.on('leave_lounge')
def handle_leave_lounge():
    """User leaves the lounge room"""
    try:
        username = session.get('username')
        if not username:
            return

        # Remove from lounge room and tracking
        leave_room('lounge')
        if username in lounge_users:
            del lounge_users[username]

        # Broadcast to all that user left
        emit('user_left', {
            'username': username
        }, room='lounge')

        # Build updated online users list
        online_users_list = []
        for user, sid in lounge_users.items():
            user_profile = profiles.get(user, {})
            user_pic = user_profile.get('profile_picture') if user_profile.get('setup_complete') else None
            staff_tag = get_lounge_staff_tag(user)
            rank = users.get(user, {}).get('rank')
            online_users_list.append({
                'username': user,
                'profile_picture': user_pic,
                'staff_tag': staff_tag,
                'rank': rank
            })

        # Send updated online users list to everyone remaining
        emit('online_users_update', {'users': online_users_list}, room='lounge')

        print(f"[LOUNGE] {username} left. Total users: {len(lounge_users)}")

    except Exception as e:
        print(f"Error in leave_lounge: {e}")


@socketio.on('send_lounge_message')
def handle_send_message(data):
    """User sends a message to the lounge"""
    try:
        username = session.get('username')
        if not username or username not in lounge_users:
            return

        message_text = data.get('message', '').strip()
        if not message_text:
            return

        # Handle /clear command (admin/master moderator only)
        user_role = users[username].get('role', 'user')
        if message_text.lower() == '/clear':
            if user_role in ['admin', 'master_moderator']:
                lounge_messages.clear()
                lounge_reactions.clear()
                lounge_read_receipts.clear()
                save_json(LOUNGE_FILE, lounge_messages)
                save_json(LOUNGE_REACTIONS_FILE, lounge_reactions)
                save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)
                emit('lounge_cleared', room='lounge')
                return
            else:
                return

        # Create message object
        timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        display_time = get_ny_time().strftime('%I:%M %p')

        message = {
            'from': username,
            'message': message_text,
            'timestamp': timestamp,
            'display_time': display_time,
            'type': 'text'
        }

        # Save to lounge messages
        lounge_messages.append(message)
        save_json(LOUNGE_FILE, lounge_messages)

        # Get user's profile picture and staff tag for broadcast
        profile = profiles.get(username, {})
        profile_picture = profile.get('profile_picture') if profile.get('setup_complete') else None
        staff_tag = get_lounge_staff_tag(username)
        message_for_broadcast = message.copy()
        message_for_broadcast['index'] = len(lounge_messages) - 1

        # Broadcast message to all in lounge
        emit('new_lounge_message', {
            'message': message_for_broadcast,
            'profile_picture': profile_picture,
            'user_rank': staff_tag,  # kept for backwards compatibility
            'staff_tag': staff_tag
        }, room='lounge')

        # Notifications handled by polling in notifications.js
        print(f"[LOUNGE] Message from {username}: {message_text[:50]}...")

    except Exception as e:
        print(f"Error in send_lounge_message: {e}")


@socketio.on('lounge_typing')
def handle_typing():
    """User is typing in the lounge"""
    try:
        username = session.get('username')
        if not username or username not in lounge_users:
            return

        # Broadcast typing indicator to all except sender
        emit('user_typing', {
            'username': username
        }, room='lounge', skip_sid=request.sid)

    except Exception as e:
        print(f"Error in lounge_typing: {e}")


@socketio.on('lounge_stop_typing')
def handle_stop_typing():
    """User stopped typing in the lounge"""
    try:
        username = session.get('username')
        if not username or username not in lounge_users:
            return

        # Broadcast stop typing to all except sender
        emit('user_stop_typing', {
            'username': username
        }, room='lounge', skip_sid=request.sid)

    except Exception as e:
        print(f"Error in lounge_stop_typing: {e}")


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    try:
        username = session.get('username')
        if username and username in lounge_users:
            # Remove from lounge
            del lounge_users[username]

            # Broadcast user left
            emit('user_left', {
                'username': username
            }, room='lounge')

            # Build updated online users list
            online_users_list = []
            for user, sid in lounge_users.items():
                user_profile = profiles.get(user, {})
                user_pic = user_profile.get('profile_picture') if user_profile.get('setup_complete') else None
                staff_tag = get_lounge_staff_tag(user)
                rank = users.get(user, {}).get('rank')
                online_users_list.append({
                    'username': user,
                    'profile_picture': user_pic,
                    'staff_tag': staff_tag,
                    'rank': rank
                })

            # Send updated online users list to everyone remaining
            emit('online_users_update', {'users': online_users_list}, room='lounge')

            print(f"[LOUNGE] {username} disconnected. Total users: {len(lounge_users)}")

    except Exception as e:
        print(f"Error in disconnect: {e}")


# ===============================================================
# GIF SUPPORT FOR LOUNGE
# ===============================================================

@app.route('/lounge/send_gif', methods=['POST'])
@login_required
def send_lounge_gif():
    """Send a GIF to the lounge"""
    try:
        username = session['username']
        data = request.json
        gif_url = data.get('gif_url', '').strip()

        if not gif_url:
            return jsonify({'error': 'No GIF URL provided'}), 400

        # Create GIF message
        timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        display_time = get_ny_time().strftime('%I:%M %p')

        message = {
            'from': username,
            'gif_url': gif_url,
            'timestamp': timestamp,
            'display_time': display_time,
            'type': 'gif'
        }

        # Save to lounge messages
        lounge_messages.append(message)
        save_json(LOUNGE_FILE, lounge_messages)

        # Broadcast via WebSocket if user is in lounge
        if username in lounge_users:
            profile = profiles.get(username, {})
            profile_picture = profile.get('profile_picture') if profile.get('setup_complete') else None
            staff_tag = get_lounge_staff_tag(username)
            broadcast_message = message.copy()
            broadcast_message['index'] = len(lounge_messages) - 1

            socketio.emit('new_lounge_message', {
                'message': broadcast_message,
                'profile_picture': profile_picture,
                'user_rank': staff_tag,
                'staff_tag': staff_tag
            }, room='lounge')

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error sending GIF: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/lounge/delete_message/<int:message_index>', methods=['DELETE'])
@login_required
def delete_lounge_message(message_index):
    """Delete a lounge message (admin, president, master moderator)"""
    try:
        username = session['username']
        if not has_permission(username, 'delete_lounge_messages'):
            return jsonify({'error': 'Unauthorized: Only admins, presidents, or master moderators can delete messages'}), 403

        _, error = _delete_lounge_message_at_index(message_index)
        if error:
            return jsonify({'error': error}), 404

        # Broadcast deletion to all users in lounge via WebSocket
        socketio.emit('message_deleted', {
            'message_index': message_index
        }, room='lounge')

        user_role = users.get(username, {}).get('role', 'member')
        print(f"[LOUNGE] {username} ({user_role}) deleted message at index {message_index}")

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error deleting lounge message: {e}")
        return jsonify({'error': str(e)}), 500


# ===============================================================
# Google Classroom Initialization
# ===============================================================

def initialize_classroom():
    """Initialize Google Classroom scraper and background thread."""
    global CLASSROOM_ID

    print("\n" + "="*60)
    print("Google Classroom Integration")
    print("="*60)

    # ALWAYS load cached announcements if they exist (even without Selenium)
    load_classroom_announcements_cache()

    if not SELENIUM_AVAILABLE:
        print("⚠️  Selenium not installed - scraping disabled")
        print("   However, cached announcements will still be displayed if available")
        print("   To enable scraping, install: pip install selenium")
        print("="*60 + "\n")
        return

    # Load classroom configuration if exists
    if os.path.exists(CLASSROOM_CONFIG_FILE):
        with open(CLASSROOM_CONFIG_FILE, 'r') as f:
            config = json.load(f)
            CLASSROOM_ID = config.get('classroom_id')
            print(f"✅ Classroom ID loaded: {CLASSROOM_ID}")
    else:
        print("⚠️  No classroom configured yet")
        print("   To configure:")
        print("   1. Create a file: classroom_config.json")
        print("   2. Add: {\"classroom_id\": \"YOUR_CLASSROOM_ID\"}")
        print("   3. Login to Google Classroom and save cookies as google_cookies.pkl")

    # Start background scraper if configured
    if CLASSROOM_ID and os.path.exists(CLASSROOM_COOKIES_FILE):
        print("\n🔄 Performing initial classroom scrape...")
        scrape_classroom_announcements()

        # Start background scraper thread
        scraper_thread = threading.Thread(target=background_classroom_scraper, daemon=True)
        scraper_thread.start()
        print("✅ Background classroom scraper started (updates every 10 minutes)")

    print("="*60 + "\n")

# Initialize Google Classroom on module load (works with both gunicorn and direct run)
initialize_classroom()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8080)
