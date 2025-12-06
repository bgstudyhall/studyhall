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

# ===============================================================
# Flask App Configuration
# ===============================================================
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

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
        'icon': '👑',
        'level': 100,
        'weekly_pay': 0  # Admin doesn't get paid
    },
    'president': {
        'name': 'President',
        'color': '#9b59b6',
        'icon': '🎖️',
        'level': 90,
        'weekly_pay': 100
    },
    'economy_director': {
        'name': 'Economy Director',
        'color': '#f1c40f',
        'icon': '💰',
        'level': 80,
        'weekly_pay': 50
    },
    'pr_director': {
        'name': 'Director of Public Relations',
        'color': '#3498db',
        'icon': '📢',
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
        'icon': '🌟',
        'level': 50,
        'weekly_pay': 0  # Base ambassadors don't get paid
    },
    'user': {
        'name': 'User',
        'color': '#95a5a6',
        'icon': '👤',
        'level': 0,
        'weekly_pay': 0
    }
}

# Permission definitions
PERMISSIONS = {
    'create_users': ['admin', 'president', 'ambassador'],
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

FORTUNES = [
    "A quiet moment will help you understand something important.",
    "A good idea will come to you when your mind is calm.",
    "Your kindness will spread farther than you think.",
    "You will find comfort in something simple and familiar.",
    "The peace you give will return to you.",
    "Your next step will lead to something good.",
    "Something you’ve been hoping for will show up when you least expect it.",
    "Hope arrives quietly, like snow on rooftops.",
    "Did you know the backround music was established December 3th by the B-G band?"

]

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
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
GAMES_FILE = os.path.join(DATA_DIR, 'games.json')
ANNOUNCEMENTS_FILE = os.path.join(DATA_DIR, 'announcements.json')
FEEDBACK_FILE = os.path.join(DATA_DIR, 'feedback.json')
MESSAGES_FILE = os.path.join(DATA_DIR, 'messages.json')
READ_RECEIPTS_FILE = os.path.join(DATA_DIR, 'read_receipts1.json')
USER_ACTIVITY_FILE = os.path.join(DATA_DIR, 'user_activity.json')
LOUNGE_FILE = os.path.join(DATA_DIR, 'lounge.json')
COOKIE_FILE = os.path.join(DATA_DIR, 'cookie_state.json')
RANKS_FILE = os.path.join(DATA_DIR, 'ranks.json')
PURCHASES_FILE = os.path.join(DATA_DIR, 'purchases.json')
CODES_FILE = os.path.join(DATA_DIR, 'codes.json')
REDEEMED_CODES_FILE = os.path.join(DATA_DIR, 'redeemed_codes.json')
RANK_PASS_FILE = os.path.join(DATA_DIR, 'rank_pass.json')
PLAYS_FILE = os.path.join(DATA_DIR, 'game_plays.json')
LOUNGE_REACTIONS_FILE = os.path.join(DATA_DIR, 'lounge_reactions.json')
LOUNGE_READ_RECEIPTS_FILE = os.path.join(DATA_DIR, 'lounge_read_receipts1.json')
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
ADVENT_CALENDAR_FILE = os.path.join(DATA_DIR, 'advent_calendar.json')
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
messages = load_json(MESSAGES_FILE, {})
read_receipts = load_json(READ_RECEIPTS_FILE, {})
user_activity = load_json(USER_ACTIVITY_FILE, {})
lounge_messages = load_json(LOUNGE_FILE, [])
lounge_reactions = load_json(LOUNGE_REACTIONS_FILE, {})
lounge_read_receipts = load_json(LOUNGE_READ_RECEIPTS_FILE, {})
login_notifications = load_json(LOGIN_NOTIFICATIONS_FILE, {})
maintenance_mode = load_json(MAINTENANCE_FILE, {
    'enabled': False,
    'title': "What's Coming",
    'notes': []
})
tower_recent_wins = load_json(TOWER_WINS_FILE, [])
cookie_state = load_json(COOKIE_FILE, {
    'last_reset': get_ny_time().strftime('%Y-%m-%d %H:%M:%S'),
    'claimed': False,
    'claimed_by': None,
    'claimed_at': None,
    'fortune': None
})

profiles = load_json(PROFILES_FILE, {})

rps_games = load_json(RPS_GAMES_FILE, {})
rps_history = load_json(RPS_HISTORY_FILE, [])

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
advent_calendar = load_json(ADVENT_CALENDAR_FILE, {})

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
            if user_role not in ['admin', 'ambassador']:
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

def check_and_reset_cookie():
    """Reset cookie every 3 hours if needed"""
    global cookie_state
    now = get_ny_time()
    try:
        last_reset = datetime.strptime(cookie_state['last_reset'], '%Y-%m-%d %H:%M:%S')
        last_reset = pytz.timezone('America/New_York').localize(last_reset)
    except:
        last_reset = now - timedelta(hours=4)

    time_diff = (now - last_reset).total_seconds() / 3600
    if time_diff >= 3:
        cookie_state = {
            'last_reset': now.strftime('%Y-%m-%d %H:%M:%S'),
            'claimed': False,
            'claimed_by': None,
            'claimed_at': None,
            'fortune': random.choice(FORTUNES)
        }
        save_json(COOKIE_FILE, cookie_state)

    if cookie_state.get('fortune') is None:
        cookie_state['fortune'] = random.choice(FORTUNES)
        cookie_state['last_reset'] = now.strftime('%Y-%m-%d %H:%M:%S')
        save_json(COOKIE_FILE, cookie_state)

# Lunch menu data
lunch_menu = {
    '2025-12-01': {'food': 'Rodeo Cheeseburger & Sweet Potato Fries', 'fact': 'Sweet potato fries became trendy in the 2000s as a "healthier" alternative - sweet potatoes have more fiber and vitamin A than regular potatoes!'},
    '2025-12-02': {'food': 'Chicken Quesadilla w/ Meat & Cheese, Corn, Rice', 'fact': 'Quesadillas date back to the 16th century when Spanish colonizers introduced cheese to Mexico, where it was combined with traditional tortillas!'},
    '2025-12-03': {'food': 'Hot Dog, Tater Tots & Baked Beans', 'fact': 'Tater Tots were invented in 1953 by the Ore-Ida company as a way to use up leftover potato scraps - now over 70 million pounds are sold yearly!'},
    '2025-12-04': {'food': 'NY Beef & NY Broccoli w/ Rice & Egg Roll', 'fact': 'Beef and broccoli is actually an American-Chinese dish invented in the U.S. - it\'s rarely found in traditional Chinese cuisine!'},
    '2025-12-05': {'food': 'Assorted Pizza & Romaine Salad w/ Tomatoes & Cucumbers', 'fact': 'December 5th is National Sacher Torte Day, but pizza is always a celebration! The average American eats 46 slices of pizza per year!'},
    '2025-12-08': {'food': 'BBQ Rib on a Bun & French Fries', 'fact': 'BBQ ribs on sandwiches became popular in the American South during the early 1900s as a portable, finger-licking meal for workers!'},
    '2025-12-09': {'food': 'Tacos w/ Meat, Cheese, Salsa, Sour Cream, Refried Beans & Rice', 'fact': 'Taco Tuesday was actually trademarked by Taco John\'s in 1989, though the phrase has become so common it\'s hard to enforce!'},
    '2025-12-10': {'food': 'BBQ Pulled Chicken on Bun & Coleslaw', 'fact': 'Coleslaw comes from the Dutch word "koolsla" meaning "cabbage salad" - Dutch settlers brought the recipe to America in the 1600s!'},
    '2025-12-11': {'food': 'Holiday Meal: Baked Ziti, Garlic Bread, Green Beans & Cherry Cobbler', 'fact': 'Baked ziti is a classic Italian-American comfort food perfect for the holidays! It became popular in the U.S. in the early 20th century with Italian immigration!'},
    '2025-12-12': {'food': 'Assorted Pizza & Romaine Salad w/ Tomatoes & Cucumbers', 'fact': 'Pizza margherita was created in 1889 to honor Queen Margherita of Italy, featuring the colors of the Italian flag: red tomatoes, white mozzarella, and green basil!'},
    '2025-12-15': {'food': 'Chicken Patty, Curly Fries & Carrots', 'fact': 'Curly fries were popularized by Arby\'s in the 1980s - their signature spiral shape is created by pushing potatoes through a special cutting machine!'},
    '2025-12-16': {'food': 'Buffalo Chicken Dip w/ Tortilla Chips & Celery Sticks', 'fact': 'Buffalo chicken dip was invented in the 1990s as a party appetizer inspired by Buffalo wings - it quickly became a game day favorite across America!'},
    '2025-12-17': {'food': 'Baked Chicken, Pasta Salad, Baked Beans & WG Roll', 'fact': 'Baked beans became a Boston staple in colonial times - molasses was abundant due to the rum trade, making sweetened beans affordable and popular!'},
    '2025-12-18': {'food': 'NY Butternut Squash Mac & Cheese, Maple Roasted NY Brussels Sprouts, Garlic Breadstick & NY Apple Slices', 'fact': 'Brussels sprouts got their name from Brussels, Belgium, where they were widely grown in the 16th century! Roasting them brings out their natural sweetness!'},
    '2025-12-19': {'food': 'Three Cheese or Pepperoni Pizza Roll & Romaine Salad w/ Tomatoes & Cucumbers', 'fact': 'Pizza rolls were invented in 1951 by a Chinese-American restaurateur who wanted to create a snack that combined pizza and egg rolls!'},
    '2025-12-22': {'food': 'Chicken Tenders, French Fries, Green Beans & WG Dinner Roll', 'fact': 'Chicken tenders are actually a specific muscle from the chicken breast called the "tenderloin" - they\'re naturally tender, hence the name!'},
    '2025-12-23': {'food': 'Deep Dish Pizza & Roasted Broccoli', 'fact': 'Deep dish pizza was invented in Chicago in 1943 at Pizzeria Uno - its thick crust can hold way more toppings than traditional thin-crust pizza!'},
    '2025-12-24': {'food': 'Christmas Eve 🎄', 'fact': 'Merry Christmas Eve! Many cultures have special foods for tonight - from Italian Feast of the Seven Fishes to Mexican tamales and pozole!'},
    '2025-12-25': {'food': 'Merry Christmas! 🎅🎁', 'fact': 'Merry Christmas! Did you know that eating turkey for Christmas became popular in England in the 16th century, thanks to King Henry VIII?'},
    '2025-12-26': {'food': 'Winter Break ❄️', 'fact': 'December 26th is Boxing Day in many countries! It originated as a day when servants received gifts in boxes from their employers!'},
    '2025-12-29': {'food': 'Winter Break ❄️', 'fact': 'Enjoy your winter break! This is the perfect time to try making your favorite lunch items at home!'},
    '2025-12-30': {'food': 'Winter Break ❄️', 'fact': 'Fun fact: The period between Christmas and New Year\'s is sometimes called "Twixmas" in the UK!'},
    '2025-12-31': {'food': 'New Year\'s Eve 🎉', 'fact': 'Happy New Year\'s Eve! Did you know that eating 12 grapes at midnight is a Spanish tradition for good luck in each month of the new year?'}
}

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
    unread_count = get_unread_count(session['username'])
    lounge_unread_count = get_lounge_unread_count(session['username'])
    sorted_games = sorted(games.items(), key=lambda x: (
        not x[1].get('free_for_all', True),
        x[1].get('price', 0),
        x[1]['name'].lower()
    ))
    sorted_games = dict(sorted_games)
    username = session['username']
    current_rank = users[username].get('rank')
    current_rank_index = -1
    if current_rank:
        for i, rank in enumerate(RANKS):
            if rank['id'] == current_rank:
                current_rank_index = i
                break
    return render_template('main.html',
    games=sorted_games,
    announcements=announcements,
    users=users,
    purchases=purchases,
    user_role=users[username]['role'],
    unread_count=unread_count,
    lounge_unread_count=lounge_unread_count,
    RANKS=RANKS,
    current_rank_index=current_rank_index,
    session=session,
    profiles=profiles
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

@app.route('/casino')
@maintenance_check
@login_required
def casino():
    username = session['username']

    unread_count = get_unread_count(username)
    lounge_unread_count = get_lounge_unread_count(username)
    return render_template('casino.html',
        user_tokens=users[username].get('tokens', 0),
        username=username,
        unread_count=unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role']
    )

@app.route('/profile', methods=['GET', 'POST'])
@maintenance_check
@login_required
def profile():
    username = session['username']
    unread_count = get_unread_count(username)
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
                lounge_unread_count=lounge_unread_count,
                user_role=users[username]['role'],
                success="Profile updated successfully!"
            )

    return render_template('profile.html',
        profile=profile_data,
        user_tokens=users[username].get('tokens', 0),
        username=username,
        unread_count=unread_count,
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
        lounge_unread_count=lounge_unread_count,
        user_role=users[current_user]['role']
    )

@app.route('/api/get_profile/<username>')
@login_required
def get_profile_data(username):
    if username not in profiles:
        return jsonify({'has_profile': False})

    profile = profiles[username]
    if not profile.get('setup_complete', False):
        return jsonify({'has_profile': False})

    return jsonify({
        'has_profile': True,
        'profile_picture': profile.get('profile_picture')
    })


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
            'member_count': len(group_data.get('members', [])) + 1
        })

    # Sort by last message timestamp
    groups_data.sort(key=lambda x: x['last_message']['timestamp'] if x['last_message'] else '', reverse=True)

    # Check if user already has a group they lead
    user_has_group = any(g['leader'] == current_user for g in groups.values())

    return render_template('chat_list.html',
        users=user_list,
        user_unread=user_unread,
        user_last_message=user_last_message,
        RANKS=RANKS,
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

    return render_template('chat_conversation.html',
        other_user=other_user,
        messages=messages[chat_key],
        current_user=current_user,
        read_receipts=read_receipts,
        users=users,
        session=session
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

        messages[chat_key].append({
            'from': current_user,
            'to': other_user,
            'text': message_text,
            'timestamp': new_timestamp,
            'read': False
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
    return jsonify({'messages': messages[chat_key]})

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

        messages[chat_key].append({
            'from': current_user,
            'to': other_user,
            'type': 'snap',
            'photo': photo_data,
            'opened': False,
            'timestamp': new_timestamp,
            'read': False
        })
        save_json(MESSAGES_FILE, messages)

        # ✅ Mark as read for yourself after sending
        if current_user not in read_receipts:
            read_receipts[current_user] = {}
        read_receipts[current_user][chat_key] = new_timestamp
        save_json(READ_RECEIPTS_FILE, read_receipts)

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

        messages[chat_key].append({
            'from': current_user,
            'to': other_user,
            'type': 'voice',
            'audio': audio_data,
            'duration': duration,
            'timestamp': new_timestamp,
            'read': False
        })
        save_json(MESSAGES_FILE, messages)

        # ✅ Mark as read for yourself after sending
        if current_user not in read_receipts:
            read_receipts[current_user] = {}
        read_receipts[current_user][chat_key] = new_timestamp
        save_json(READ_RECEIPTS_FILE, read_receipts)

        return jsonify({'success': True})

@app.route('/chat/<other_user>/open_snap/<int:message_index>', methods=['POST'])
@login_required
def open_snap(other_user, message_index):
    current_user = session['username']
    chat_key = get_chat_key(current_user, other_user)
    if chat_key in messages and message_index < len(messages[chat_key]):
        msg = messages[chat_key][message_index]
        if msg.get('type') == 'snap' and msg.get('to') == current_user:
            msg['opened'] = True
            save_json(MESSAGES_FILE, messages)
            return jsonify({'success': True, 'photo': msg['photo']})
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

    messages[chat_key].append({
        'from': 'system',
        'to': other_user,
        'type': 'token_gift',
        'text': f'{current_user} sent {amount} tokens to {other_user}!️',
        'timestamp': new_timestamp,
        'read': False
    })
    save_json(MESSAGES_FILE, messages)


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
    current_user = session['username']
    current_time = get_ny_time().timestamp()
    online_threshold = 30
    users_by_rank = {}

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
            'last_message_timestamp': last_message_timestamp
        })

    return jsonify({'users_by_rank': users_by_rank})

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
    check_and_reset_cookie()

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
        cookie_state=cookie_state,
        current_user=username,
        user_role=users[username]['role'],
        reactions=lounge_reactions
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
    current_user = session['username']

    if message_text:
        new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

        lounge_messages.append({
            'from': current_user,
            'text': message_text,
            'timestamp': new_timestamp
        })
        save_json(LOUNGE_FILE, lounge_messages)

        # ✅ CRITICAL: Mark lounge as read for yourself after sending
        lounge_read_receipts[current_user] = new_timestamp
        save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

        return jsonify({'success': True})

    return jsonify({'error': 'No message provided'}), 400

@app.route('/lounge/messages')
@login_required
def get_lounge_messages():
    check_and_reset_cookie()

    # ✅ DO NOT mark as read when polling - only when user explicitly marks

    return jsonify({
        'messages': lounge_messages,
        'cookie_state': cookie_state,
        'reactions': lounge_reactions,
        'user_role': users[session['username']]['role']
    })

@app.route('/lounge/claim_cookie', methods=['POST'])
@login_required
def claim_cookie():
    global cookie_state
    check_and_reset_cookie()
    if cookie_state['claimed']:
        return jsonify({'error': 'Cookie already claimed'}), 400
    username = session['username']
    cookie_state['claimed'] = True
    cookie_state['claimed_by'] = username
    cookie_state['claimed_at'] = get_ny_time().strftime('%I:%M %p')
    cookie_state['last_reset'] = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')  # ✅ ADD THIS LINE
    users[username]['tokens'] = users[username].get('tokens', 0) + 5  # ✅ FIXED TO 5
    save_json(COOKIE_FILE, cookie_state)
    save_json(USERS_FILE, users)
    log_transaction('creation', 5, username, 'fortune_cookie')
    lounge_messages.append({
        'from': 'system',
        'text': f'🥠 {username} claimed the fortune cookie! "{cookie_state["fortune"]}"',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_json(LOUNGE_FILE, lounge_messages)
    return jsonify({
        'success': True,
        'fortune': cookie_state['fortune'],
        'new_balance': users[username]['tokens']
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

@app.route('/lounge/delete/<int:message_index>', methods=['POST'])
@panel_access_required
def delete_lounge_message(message_index):
    if message_index >= len(lounge_messages):
        return jsonify({'error': 'Message not found'}), 404
    lounge_messages.pop(message_index)
    save_json(LOUNGE_FILE, lounge_messages)
    global lounge_reactions
    new_reactions = {}
    for key, reactions in lounge_reactions.items():
        idx = int(key)
        if idx < message_index:
            new_reactions[key] = reactions
        elif idx > message_index:
            new_reactions[str(idx - 1)] = reactions
    lounge_reactions = new_reactions
    save_json(LOUNGE_REACTIONS_FILE, lounge_reactions)
    return jsonify({'success': True})

@app.route('/lounge/send_snap', methods=['POST'])
@login_required
def send_lounge_snap():
    photo_data = request.json.get('photo')
    current_user = session['username']

    if photo_data:
        new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

        lounge_messages.append({
            'from': current_user,
            'type': 'snap',
            'photo': photo_data,
            'opened_by': [],
            'timestamp': new_timestamp
        })
        save_json(LOUNGE_FILE, lounge_messages)

        # ✅ CRITICAL: Mark lounge as read for yourself after sending snap
        lounge_read_receipts[current_user] = new_timestamp
        save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

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

        lounge_messages.append({
            'from': current_user,
            'type': 'voice',
            'audio': audio_data,
            'duration': duration,
            'timestamp': new_timestamp
        })
        save_json(LOUNGE_FILE, lounge_messages)

        # Mark lounge as read for yourself after sending voice
        lounge_read_receipts[current_user] = new_timestamp
        save_json(LOUNGE_READ_RECEIPTS_FILE, lounge_read_receipts)

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
    unread_count = get_unread_count(username)
    lounge_unread_count = get_lounge_unread_count(username)
    return render_template('proxy.html',
        user_tokens=users[username].get('tokens', 0),
        username=username,
        unread_count=unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role'],
        site_access=site_access
    )

@app.route('/youtube')
@maintenance_check
@login_required
def youtube():
    username = session['username']
    # Check if user has youtube access
    if username not in site_access or 'youtube' not in site_access[username]:
        return render_template('no_access.html',
            site_name='YouTube',
            purchase_url=url_for('proxy')
        )
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

@app.route('/reddit')
@maintenance_check
@login_required
def reddit():
    username = session['username']
    # Check if user has reddit access
    if username not in site_access or 'reddit' not in site_access[username]:
        return render_template('no_access.html',
            site_name='Reddit',
            purchase_url=url_for('proxy')
        )
    return render_template('twitch.html')

# Serve UV config
@app.route('/uv.config.js')
def serve_config():
    config = """
self.__uv$config = {
    prefix: '/service/',
    bare: 'https://uv.holy.how/bare/',
    encodeUrl: Ultraviolet.codec.xor.encode,
    decodeUrl: Ultraviolet.codec.xor.decode,
    handler: '/uv.handler.js',
    client: '/uv.client.js',
    bundle: '/static/uv/uv.bundle.js',
    config: '/uv.config.js',
    sw: '/uv.sw.js',
};

// Disable bare-mux, use direct bare client
self.__uv$bareOptions = {
    type: 'fetch'
};
"""
    return Response(config, mimetype='application/javascript')

# Serve WRAPPER service worker that imports everything
@app.route('/uv.sw.js')
def serve_sw():
    wrapper = """// Import Ultraviolet bundle first
importScripts('/static/uv/uv.bundle.js');
importScripts('/uv.config.js');

// Completely stub out BareMux to prevent it from initializing
if (!self.BareMux) {
    self.BareMux = {};
}
// Stub the function that tries to create bare-mux connection
self.BareMux.createChannel = async () => {
    throw new Error('BareMux disabled');
};

// Patch BareClient constructor to skip BareMux
const OriginalBareClient = Ultraviolet.BareClient;
Ultraviolet.BareClient = class PatchedBareClient extends OriginalBareClient {
    constructor(server) {
        super();
        // Directly set the server, bypassing BareMux initialization
        this.server = server || __uv$config.bare;
        this.working = true;
    }
};

importScripts('/uv.sw-core.js');

// Instantiate the service worker
const uv = new UVServiceWorker(__uv$config);

// Set up event listeners
self.addEventListener('fetch', (event) => {
    if (uv.route(event)) {
        event.respondWith(
            (async () => {
                try {
                    return await uv.fetch(event);
                } catch (err) {
                    console.error('UV fetch error:', err);
                    return new Response('Proxy error: ' + err.message, {
                        status: 500,
                        headers: { 'Content-Type': 'text/plain' }
                    });
                }
            })()
        );
    }
});
"""
    response = Response(wrapper, mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    return response

# Serve the ACTUAL service worker code
@app.route('/uv.sw-core.js')
def serve_sw_core():
    try:
        file_path = os.path.join(app.root_path, 'static', 'service', 'uv.sw.js')
        with open(file_path, 'r') as f:
            content = f.read()
        return Response(content, mimetype='application/javascript')
    except Exception as e:
        return str(e), 500

# Serve other UV files
@app.route('/uv.handler.js')
def serve_handler():
    try:
        return send_from_directory(
            os.path.join(app.root_path, 'static', 'service'),
            'uv.handler.js',
            mimetype='application/javascript'
        )
    except Exception as e:
        return str(e), 500

@app.route('/uv.client.js')
def serve_client():
    try:
        return send_from_directory(
            os.path.join(app.root_path, 'static', 'service'),
            'uv.client.js',
            mimetype='application/javascript'
        )
    except Exception as e:
        return str(e), 500

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
        lounge_messages.append({
            'from': 'system',
            'text': f'🗑️ Lounge history was cleared by {session["username"]}',
            'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_json(LOUNGE_FILE, lounge_messages)

        return jsonify({'success': True, 'message': 'Lounge history cleared'})

    except Exception as e:
        print(f"Error clearing lounge history: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
        'fact': 'Enjoy your day off!'
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

    if game.get('free_for_all', True):
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

    # Inject notification system into game HTML
    notification_html = '''
    <!-- Chat Notification Container -->
    <div id="chatNotificationContainer"></div>
    <style>
    .chat-notification {
        position: fixed;
        top: 20px;
        right: 20px;
        background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        border: 5px solid #c19a6b;
        border-radius: 20px;
        padding: 1rem 1.5rem;
        min-width: 300px;
        max-width: 400px;
        box-shadow: 0 8px 0 #2C2C2C, 0 12px 30px rgba(193, 154, 107, 0.5);
        cursor: pointer;
        transition: all 0.3s ease;
        z-index: 999999;
        animation: slideInRight 0.4s ease-out;
    }
    .chat-notification:hover {
        transform: translateY(-3px) translateX(-5px);
        box-shadow: 0 12px 0 #2C2C2C, 0 16px 40px rgba(193, 154, 107, 0.6);
    }
    .chat-notification:active {
        transform: translateY(1px);
        box-shadow: 0 4px 0 #2C2C2C;
    }
    @keyframes slideInRight {
        from { transform: translateX(450px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOutRight {
        to { transform: translateX(450px); opacity: 0; }
    }
    .chat-notification.hiding {
        animation: slideOutRight 0.3s ease-in forwards;
    }
    .notification-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.5rem;
    }
    .notification-icon {
        width: 45px;
        height: 45px;
        border-radius: 50%;
        background: #c19a6b;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.3rem;
        border: 4px solid #2C2C2C;
        box-shadow: 0 3px 0 rgba(44, 44, 44, 0.5);
    }
    .notification-content { flex: 1; }
    .notification-title {
        font-weight: 900;
        font-size: 0.9rem;
        color: #c19a6b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .notification-user {
        font-weight: 700;
        font-size: 1.1rem;
        color: #ffffff;
        margin-top: 0.25rem;
    }
    .notification-action {
        font-size: 0.75rem;
        color: #888;
        margin-top: 0.25rem;
        font-weight: 600;
    }
    .notification-close {
        background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%);
        border: 3px solid #2C2C2C;
        color: white;
        width: 30px;
        height: 30px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
        cursor: pointer;
        transition: all 0.3s;
        box-shadow: 0 3px 0 #2C2C2C;
        font-weight: 900;
    }
    .notification-close:hover {
        transform: rotate(90deg) scale(1.1);
    }
    </style>
    <script>
    // Chat Notification System for Games
    let shownNotifications = new Set();
    let lastNotificationCheck = '';

    function checkChatNotifications() {
        fetch('/api/chat_notifications')
            .then(response => response.json())
            .then(data => {
                data.notifications.forEach(notif => {
                    const notifKey = notif.from + '-' + notif.timestamp;
                    if (!shownNotifications.has(notifKey) && notif.timestamp > lastNotificationCheck) {
                        showChatNotification(notif.from, notif.type || 'message', notif.chat_key);
                        shownNotifications.add(notifKey);
                    }
                });
                if (data.notifications.length > 0) {
                    lastNotificationCheck = data.notifications[0].timestamp;
                }
            })
            .catch(error => console.error('Error checking notifications:', error));
    }

    function checkGroupNotifications() {
        fetch('/api/group_notifications')
            .then(response => response.json())
            .then(data => {
                data.notifications.forEach(notif => {
                    const notifKey = 'group-' + notif.group_id + '-' + notif.timestamp;
                    if (!shownNotifications.has(notifKey) && notif.timestamp > lastNotificationCheck) {
                        showGroupNotification(notif.from, notif.group_name, notif.group_id, notif.message_type || 'message');
                        shownNotifications.add(notifKey);
                    }
                });
            })
            .catch(error => console.error('Error checking group notifications:', error));
    }

    function showChatNotification(fromUser, type = 'message', chatKey) {
        const container = document.getElementById('chatNotificationContainer');
        if (!container) return;

        const notification = document.createElement('div');
        notification.className = 'chat-notification';

        let title, icon, action;
        if (type === 'rps_invite') {
            title = 'RPS Challenge!';
            icon = '✂️';
            action = 'challenged you to Rock Paper Scissors';
        } else if (type === 'snap') {
            title = 'New Snap!';
            icon = '📸';
            action = 'sent you a snap';
        } else if (type === 'voice') {
            title = 'Voice Message';
            icon = '🎤';
            action = 'sent you a voice message';
        } else if (type === 'token_gift') {
            title = 'Token Gift!';
            icon = '🎁';
            action = 'sent you tokens';
        } else {
            title = 'New Message';
            icon = '💬';
            action = 'sent you a message';
        }

        notification.innerHTML = `
            <div class="notification-header">
                <div class="notification-icon">${icon}</div>
                <div class="notification-content">
                    <div class="notification-title">${title}</div>
                    <div class="notification-user">${fromUser}</div>
                    <div class="notification-action">${action}</div>
                </div>
                <button class="notification-close" onclick="event.stopPropagation(); closeNotification(this.parentElement)">✕</button>
            </div>
        `;

        notification.addEventListener('click', () => {
            window.location.href = '/chat/' + fromUser;
        });

        container.appendChild(notification);
        setTimeout(() => closeNotification(notification), 8000);
    }

    function showGroupNotification(fromUser, groupName, groupId, type = 'message') {
        const container = document.getElementById('chatNotificationContainer');
        if (!container) return;

        const notification = document.createElement('div');
        notification.className = 'chat-notification';

        let title, icon, action;
        if (type === 'snap') {
            title = 'Group Snap!';
            icon = '📸';
            action = `sent a snap in ${groupName}`;
        } else if (type === 'voice') {
            title = 'Group Voice';
            icon = '🎤';
            action = `sent a voice message in ${groupName}`;
        } else {
            title = 'Group Message';
            icon = '💬';
            action = `sent a message in ${groupName}`;
        }

        notification.innerHTML = `
            <div class="notification-header">
                <div class="notification-icon">${icon}</div>
                <div class="notification-content">
                    <div class="notification-title">${title}</div>
                    <div class="notification-user">${fromUser}</div>
                    <div class="notification-action">${action}</div>
                </div>
                <button class="notification-close" onclick="event.stopPropagation(); closeNotification(this.parentElement)">✕</button>
            </div>
        `;

        notification.addEventListener('click', () => {
            window.location.href = '/group/' + groupId;
        });

        container.appendChild(notification);
        setTimeout(() => closeNotification(notification), 8000);
    }

    function closeNotification(notification) {
        notification.classList.add('hiding');
        setTimeout(() => {
            notification.remove();
        }, 300);
    }

    setInterval(checkChatNotifications, 2000);
    setInterval(checkGroupNotifications, 2000);
    checkChatNotifications();
    checkGroupNotifications();
    </script>
    '''

    # Inject the notification HTML
    game_html = game['html_content']

    # Insert before closing </body> tag if it exists
    if '</body>' in game_html:
        game_html = game_html.replace('</body>', notification_html + '</body>')
    else:
        # Otherwise append to end
        game_html = game_html + notification_html

    return game_html

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
        'youtube': 120,
        'twitch': 170,
        'reddit': 150
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
            'message_count': message_count
        })
    groups_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    # Get pending reports count
    pending_reports = len([r for r in reported_messages if r['status'] == 'pending'])

    # Get pending paychecks count
    pending_paychecks = len(paychecks.get('pending', []))

    return render_template('admin.html',
        users=users,
        games=games_metadata,
        announcements=announcements,
        feedback=feedback,
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
        reported_messages=reported_messages
    )

@app.route('/api/get_game_html/<game_id>')
@admin_required
def get_game_html(game_id):
    if game_id not in games:
        return jsonify({'error': 'Game not found'}), 404
    return jsonify({
        'success': True,
        'html_content': games[game_id]['html_content']
    })

@app.route('/panel/edit_token/<username>/<int:amount>', methods=['GET', 'POST'])
@admin_required
def edit_token(username, amount):
    if username in users:
        users[username]['tokens'] = amount
        save_json(USERS_FILE, users)
    return redirect(url_for('admin_panel'))

@app.route('/panel/change_password/<username>', methods=['POST'])
@panel_access_required
def change_password(username):
    if username in users and username != 'admin':
        new_password = request.form.get('new_password')
        if new_password:
            users[username]['password'] = new_password
            save_json(USERS_FILE, users)
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

@app.route('/panel/create_user', methods=['POST'])
@panel_access_required
def create_user():
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
    return redirect(url_for('admin_panel'))

@app.route('/panel/promote_ambassador/<username>')
@admin_required
def promote_ambassador(username):
    if username in users and username != 'admin':
        users[username]['role'] = 'ambassador'
        save_json(USERS_FILE, users)
    return redirect(url_for('admin_panel'))

@app.route('/panel/demote_ambassador/<username>')
@admin_required
def demote_ambassador(username):
    if username in users and username != 'admin':
        users[username]['role'] = 'user'
        save_json(USERS_FILE, users)
    return redirect(url_for('admin_panel'))

@app.route('/panel/ban_user', methods=['POST'])
@panel_access_required
def ban_user():
    username = request.form.get('username')
    reason = request.form.get('reason', 'No reason provided')
    if username in users and username != 'admin':
        users[username]['banned'] = True
        users[username]['ban_reason'] = reason
        save_json(USERS_FILE, users)
    return redirect(url_for('admin_panel'))

@app.route('/panel/unban_user/<username>', methods=['GET', 'POST'])
@panel_access_required
def unban_user(username):
    if username in users:
        users[username]['banned'] = False
        users[username]['ban_reason'] = ''
        save_json(USERS_FILE, users)
    return redirect(url_for('admin_panel'))

@app.route('/panel/delete_user/<username>')
@admin_required
def delete_user(username):
    if username in users and username != 'admin':
        del users[username]
        save_json(USERS_FILE, users)
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
    if game_id in games:
        html_content = request.form.get('html_content')
        if html_content:
            games[game_id]['html_content'] = html_content
            save_json(GAMES_FILE, games)
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
    if announcement_text:
        announcements.append({
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

    # Pick random winner
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

    # Clear tickets
    lottery_tickets.clear()

    save_json(USERS_FILE, users)
    save_json(LOTTERY_FILE, lottery_state)
    save_json(LOTTERY_TICKETS_FILE, lottery_tickets)
    log_transaction('creation', prize, winner, 'lottery_win')

    # Post to lounge
    lounge_messages.append({
        'from': 'system',
        'text': f'🎰 LOTTERY WINNER: {winner} won {prize} tokens with {winner_tickets}/{total_tickets} tickets! 🎉',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
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

    # ===============================================================
# Advent Calendar API Routes
# ===============================================================

# Define advent calendar rewards configuration
ADVENT_REWARDS = {
    1: {'type': 'tokens', 'amount': 10, 'description': '10 Tokens'},
    2: {'type': 'free_game', 'description': 'Free Game of Your Choice'},
    3: {'type': 'tokens', 'amount': 12, 'description': '12 Tokens'},
    4: {'type': 'tokens', 'amount': 5, 'description': '5 Tokens'},
    5: {'type': 'youtube_access', 'description': 'YouTube Access'},
    # Doors 6-24 are placeholders for future implementation
    6: {'type': 'placeholder', 'description': 'Mystery Reward'},
    7: {'type': 'placeholder', 'description': 'Mystery Reward'},
    8: {'type': 'placeholder', 'description': 'Mystery Reward'},
    9: {'type': 'placeholder', 'description': 'Mystery Reward'},
    10: {'type': 'placeholder', 'description': 'Mystery Reward'},
    11: {'type': 'placeholder', 'description': 'Mystery Reward'},
    12: {'type': 'placeholder', 'description': 'Mystery Reward'},
    13: {'type': 'placeholder', 'description': 'Mystery Reward'},
    14: {'type': 'placeholder', 'description': 'Mystery Reward'},
    15: {'type': 'placeholder', 'description': 'Mystery Reward'},
    16: {'type': 'placeholder', 'description': 'Mystery Reward'},
    17: {'type': 'placeholder', 'description': 'Mystery Reward'},
    18: {'type': 'placeholder', 'description': 'Mystery Reward'},
    19: {'type': 'placeholder', 'description': 'Mystery Reward'},
    20: {'type': 'placeholder', 'description': 'Mystery Reward'},
    21: {'type': 'placeholder', 'description': 'Mystery Reward'},
    22: {'type': 'placeholder', 'description': 'Mystery Reward'},
    23: {'type': 'placeholder', 'description': 'Mystery Reward'},
    24: {'type': 'placeholder', 'description': 'Mystery Reward'},
}

@app.route('/api/advent/status')
@login_required
def get_advent_status():
    """Get user's advent calendar status"""
    username = session['username']
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)

    print(f"DEBUG: Current NY time: {now}")
    print(f"DEBUG: Current date: {now.date()}")

    # Initialize user's advent calendar if not exists
    if username not in advent_calendar:
        advent_calendar[username] = {}
        save_json(ADVENT_CALENDAR_FILE, advent_calendar)

    # Build door status for each day
    doors_status = {}
    for door_num in range(1, 25):
        door_key = f'door_{door_num}'
        door_date = datetime(2025, 12, door_num, tzinfo=ny_tz)  # December 2025

        # Check if door exists in user's data
        door_data = advent_calendar[username].get(door_key, {
            'opened': False,
            'claimed_reward': None,
            'opened_date': None,
            'game_selected': None
        })

        # Determine door state
        if now.date() < door_date.date():
            state = 'locked'  # Future door
        elif now.date() == door_date.date():
            state = 'available' if not door_data.get('opened') else 'opened'
        else:
            state = 'missed' if not door_data.get('opened') else 'opened'

        doors_status[door_num] = {
            'state': state,
            'opened': door_data.get('opened', False),
            'reward': door_data.get('claimed_reward'),
            'reward_type': ADVENT_REWARDS[door_num]['type'],
            'description': ADVENT_REWARDS[door_num]['description']
        }

        if door_num == 1:
            print(f"DEBUG Door 1: door_date={door_date.date()}, now.date={now.date()}, state={state}")

    print(f"DEBUG: Total doors in response: {len(doors_status)}")
    print(f"DEBUG: Sample doors_status: {list(doors_status.items())[:3]}")

    return jsonify({
        'success': True,
        'doors': doors_status,
        'current_date': now.strftime('%Y-%m-%d')
    })

@app.route('/api/advent/open/<int:door_number>', methods=['POST'])
@login_required
def open_advent_door(door_number):
    """Open an advent calendar door"""
    username = session['username']

    # Validate door number
    if door_number < 1 or door_number > 24:
        return jsonify({'error': 'Invalid door number'}), 400

    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    door_date = datetime(2025, 12, door_number, tzinfo=ny_tz)  # December 2025

    # Check if it's the correct date
    if now.date() != door_date.date():
        return jsonify({'error': 'This door can only be opened on its day!'}), 403

    # Initialize user's advent calendar if not exists
    if username not in advent_calendar:
        advent_calendar[username] = {}

    door_key = f'door_{door_number}'

    # Check if already opened
    if advent_calendar[username].get(door_key, {}).get('opened'):
        return jsonify({'error': 'Door already opened!'}), 400

    # Get reward configuration
    reward_config = ADVENT_REWARDS[door_number]

    # Handle different reward types
    if reward_config['type'] == 'tokens':
        # Award tokens immediately
        amount = reward_config['amount']
        users[username]['tokens'] = users[username].get('tokens', 0) + amount
        save_json(USERS_FILE, users)

        # Mark door as opened
        advent_calendar[username][door_key] = {
            'opened': True,
            'claimed_reward': f"{amount} Tokens",
            'opened_date': now.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_json(ADVENT_CALENDAR_FILE, advent_calendar)

        return jsonify({
            'success': True,
            'reward_type': 'tokens',
            'amount': amount,
            'new_balance': users[username]['tokens']
        })

    elif reward_config['type'] == 'free_game':
        # Get list of unpurchased games
        user_purchases = purchases.get(username, [])
        available_games = []

        for game_id, game in games.items():
            if game_id not in user_purchases and not game.get('free_for_all', True):
                available_games.append({
                    'id': game_id,
                    'name': game['name'],
                    'price': game.get('price', 0)
                })

        if not available_games:
            return jsonify({'error': 'No games available to claim!'}), 400

        # Mark door as opened but not fully claimed yet
        advent_calendar[username][door_key] = {
            'opened': True,
            'claimed_reward': None,  # Will be set when game is selected
            'opened_date': now.strftime('%Y-%m-%d %H:%M:%S'),
            'game_selected': None
        }
        save_json(ADVENT_CALENDAR_FILE, advent_calendar)

        return jsonify({
            'success': True,
            'reward_type': 'free_game',
            'available_games': available_games
        })

    elif reward_config['type'] == 'youtube_access':
        # Grant YouTube access
        if username not in site_access:
            site_access[username] = []

        if 'youtube' not in site_access[username]:
            site_access[username].append('youtube')
            save_json(SITE_ACCESS_FILE, site_access)
            reward_text = 'YouTube Access Granted!'
        else:
            reward_text = 'YouTube Access (Already Had)'

        # Mark door as opened
        advent_calendar[username][door_key] = {
            'opened': True,
            'claimed_reward': reward_text,
            'opened_date': now.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_json(ADVENT_CALENDAR_FILE, advent_calendar)

        return jsonify({
            'success': True,
            'reward_type': 'youtube_access',
            'message': reward_text
        })

    elif reward_config['type'] == 'placeholder':
        return jsonify({'error': 'This reward is not available yet!'}), 400

    return jsonify({'error': 'Unknown reward type'}), 500

@app.route('/api/advent/claim_game', methods=['POST'])
@login_required
def claim_advent_game():
    """Claim the free game from door 2"""
    username = session['username']
    data = request.json
    game_id = data.get('game_id')

    if not game_id:
        return jsonify({'error': 'No game selected'}), 400

    # Check if game exists
    if game_id not in games:
        return jsonify({'error': 'Game not found'}), 404

    # Check if door 2 was opened but game not yet claimed
    door_key = 'door_2'
    if username not in advent_calendar or door_key not in advent_calendar[username]:
        return jsonify({'error': 'Door 2 not opened'}), 400

    door_data = advent_calendar[username][door_key]
    if door_data.get('game_selected'):
        return jsonify({'error': 'Game already claimed'}), 400

    # Check if user already owns this game
    if username in purchases and game_id in purchases[username]:
        return jsonify({'error': 'You already own this game'}), 400

    # Grant the game
    if username not in purchases:
        purchases[username] = []

    purchases[username].append(game_id)
    save_json(PURCHASES_FILE, purchases)

    # Update advent calendar
    advent_calendar[username][door_key]['claimed_reward'] = f"Free Game: {games[game_id]['name']}"
    advent_calendar[username][door_key]['game_selected'] = game_id
    save_json(ADVENT_CALENDAR_FILE, advent_calendar)

    return jsonify({
        'success': True,
        'game_name': games[game_id]['name']
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
    unread_count = get_unread_count(username)
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
            'member_count': len(group_data.get('members', [])) + 1  # +1 for leader
        })

    # Sort by last message timestamp (most recent first)
    groups_data.sort(key=lambda x: x['last_message']['timestamp'] if x['last_message'] else '', reverse=True)

    # Check if user already has a group they lead
    user_has_group = any(g['leader'] == username for g in groups.values())

    return render_template('groups_list.html',
        groups=groups_data,
        user_has_group=user_has_group,
        unread_count=unread_count,
        lounge_unread_count=lounge_unread_count,
        user_role=users[username]['role'],
        user_tokens=users[username].get('tokens', 0),
        profiles=profiles,
        all_users=[u for u in users.keys() if u != username]
    )

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

    # Get reactions for this group
    reactions = group_reactions.get(group_id, {})

    return render_template('group_chat.html',
        group=group_data,
        group_id=group_id,
        messages=group_messages.get(group_id, []),
        reactions=reactions,
        current_user=username,
        is_leader=username == group_data['leader'],
        user_role=users[username]['role'],
        profiles=profiles,
        all_users=[u for u in users.keys() if u != username and u != group_data['leader'] and u not in group_data.get('members', [])]
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

    if len(members) > 5:
        return jsonify({'error': 'Maximum 5 members allowed (6 total including you)'}), 400

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
        'created_at': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    }

    # Initialize messages
    group_messages[group_id] = [{
        'from': 'system',
        'text': f'🎉 {username} created the group "{group_name}"',
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
            'text': f'🎊 {username} added you to the group "{group_name}"!',
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

    if group_id not in group_messages:
        group_messages[group_id] = []

    new_timestamp = get_ny_time().strftime('%Y-%m-%d %H:%M:%S')

    group_messages[group_id].append({
        'from': username,
        'text': message_text,
        'timestamp': new_timestamp
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

    return jsonify({
        'messages': group_messages.get(group_id, []),
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

    # Check member limit (5 members + 1 leader = 6 total)
    if len(group_data.get('members', [])) >= 5:
        return jsonify({'error': 'Group is full (maximum 6 members)'}), 400

    # Add member
    if 'members' not in groups[group_id]:
        groups[group_id]['members'] = []
    groups[group_id]['members'].append(member_username)

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []
    group_messages[group_id].append({
        'from': 'system',
        'text': f'👋 {member_username} was added to the group by {username}',
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
        'text': f'👢 {member_username} was removed from the group',
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
        'text': f'👋 {username} left the group',
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

@app.route('/api/groups/unread_count')
@login_required
def get_groups_unread_count():
    """Get total unread count for groups"""
    username = session['username']
    return jsonify({'count': get_total_group_unread_count(username)})

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
        'text': f'✏️ Group renamed from "{old_name}" to "{new_name}" by admin',
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
        'text': f'👢 {member} was removed from the group by admin',
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
        'text': f'👑 Leadership transferred from {old_leader} to {new_leader} by admin',
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

    if 'members' not in groups[group_id]:
        groups[group_id]['members'] = []
    groups[group_id]['members'].append(new_member)
    save_json(GROUPS_FILE, groups)

    # Add system message
    if group_id not in group_messages:
        group_messages[group_id] = []
    group_messages[group_id].append({
        'from': 'system',
        'text': f'➕ {new_member} was added to the group by admin',
        'timestamp': get_ny_time().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_json(GROUP_MESSAGES_FILE, group_messages)

    return jsonify({'success': True})

@app.route('/api/report_message', methods=['POST'])
@login_required
def report_message():
    """Report a message in private chat"""
    data = request.json
    chat_key = data.get('chat_key')
    message_index = data.get('message_index')
    reason = data.get('reason', '')

    if not chat_key or message_index is None:
        return jsonify({'error': 'Invalid request'}), 400

    # Get the message
    if chat_key not in messages or message_index >= len(messages[chat_key]):
        return jsonify({'error': 'Message not found'}), 404

    msg = messages[chat_key][message_index]
    reporter = session['username']

    # Can't report your own messages
    if msg.get('from') == reporter:
        return jsonify({'error': 'Cannot report your own message'}), 400

    # Check if already reported
    for report in reported_messages:
        if report['chat_key'] == chat_key and report['message_index'] == message_index:
            return jsonify({'error': 'Message already reported'}), 400

    report = {
        'id': len(reported_messages) + 1,
        'chat_key': chat_key,
        'message_index': message_index,
        'message_content': msg.get('text', '[Media Message]'),
        'message_type': msg.get('type', 'text'),
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
        response['my_pending'] = my_pending
        response['my_history'] = my_history
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
    for game_type in ['coinflip', 'tower']:
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

    # Check if role is already taken (for unique roles)
    unique_roles = ['president', 'economy_director', 'pr_director', 'master_moderator']
    if new_role in unique_roles:
        for u, udata in users.items():
            if udata.get('role') == new_role and u != username:
                return jsonify({'success': False, 'error': f'{new_role} role is already assigned to {u}'}), 400

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


if __name__ == '__main__':
    app.run(debug=True)