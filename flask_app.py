from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
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

FORTUNES = [
    "Harpo should play football - Keegan"
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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        user_role = users[session['username']]['role']
        if user_role not in ['admin', 'ambassador']:
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
    '2025-11-03': {'food': 'Chicken Patty on Bun w/ Buttered Noodles', 'fact': 'Chicken patties became popular in school lunches in the 1980s as a quick, protein-rich option that students actually enjoyed eating!'},
    '2025-11-04': {'food': 'Hot Dog on Bun', 'fact': 'The hot dog got its name from a cartoonist who couldn\'t spell "dachshund" - the sausage\'s shape reminded him of the long German dog breed!'},
    '2025-11-05': {'food': 'BBQ Chicken Sandwich', 'fact': 'BBQ sauce recipes vary wildly by region in the U.S. - some are vinegar-based, others tomato-based, and some are even mustard-based in South Carolina!'},
    '2025-11-06': {'food': 'Loaded NY Nachos, Taco Meat (NY ground beef)', 'fact': 'New York-style nachos use a special seasoning blend that\'s different from traditional Tex-Mex - it\'s become a unique regional variation!'},
    '2025-11-07': {'food': 'Assorted Pizza', 'fact': 'Pizza Hut was the first pizza chain to deliver to the White House in 1969, setting the trend for presidential pizza orders!'},
    '2025-11-10': {'food': 'Popcorn Chicken and French Fries', 'fact': 'Popcorn chicken was invented in the 1990s as a finger-food alternative to traditional fried chicken - perfect for eating without utensils!'},
    '2025-11-11': {'food': 'Veterans Day - Thank you to all veterans for your service! 🇺🇸', 'fact': 'Veterans Day was originally called Armistice Day and began in 1919 to honor WWI veterans. In 1954, it was renamed to honor all American veterans.'},
    '2025-11-12': {'food': 'Cheeseburger', 'fact': 'The cheeseburger was invented accidentally in 1924 when a chef named Lionel Sternberger placed a slice of American cheese on a burger as an experiment!'},
    '2025-11-13': {'food': 'Italian Sub Melt', 'fact': 'The Italian sub originated in Italian-American communities in the early 1900s and was originally called a "hoagie" or "grinder" depending on the region!'},
    '2025-11-14': {'food': 'Pepperoni or Cheese Roll w/ Marinara Sauce', 'fact': 'Pizza rolls and similar baked dough snacks became hugely popular in school lunches because they could be easily mass-produced and reheated!'},
    '2025-11-17': {'food': 'Grilled Cheese', 'fact': 'The grilled cheese sandwich became widely popular during the Great Depression because bread and cheese were inexpensive and filling staples!'},
    '2025-11-18': {'food': 'Tacos w/ Meat & Cheese', 'fact': 'Taco Tuesday became a cultural phenomenon in the 1980s thanks to a restaurant chain\'s marketing campaign - now it\'s a weekly tradition for many!'},
    '2025-11-19': {'food': 'Hot Meatball Sub', 'fact': 'Meatball subs became popular in Italian-American restaurants in the 1930s and quickly became a lunchtime favorite across America!'},
    '2025-11-20': {'food': 'Turkey w/ Gravy & Mashed Potatoes', 'fact': 'This Thanksgiving preview meal helps prepare your taste buds! Turkey contains tryptophan, but it\'s the large meal that actually makes you sleepy, not the turkey itself!'},
    '2025-11-21': {'food': 'Assorted Pizza', 'fact': 'Americans eat approximately 350 slices of pizza per second - that\'s about 100 acres of pizza consumed every single day!'},
    '2025-11-24': {'food': 'Chicken Tenders and French Fries', 'fact': 'Chicken tenders are actually a specific muscle from the chicken breast called the "tenderloin" - they\'re naturally tender, hence the name!'},
    '2025-11-25': {'food': 'Pizza Crunchers', 'fact': 'Handheld pizza variations like pizza crunchers were designed specifically for school lunches to reduce mess and make eating faster between classes!'},
    '2025-11-26': {'food': 'No School - Thanksgiving Recess', 'fact': 'Happy Thanksgiving! 🦃 The first Thanksgiving feast in 1621 lasted three days and featured foods very different from today\'s traditional meal!'},
    '2025-11-27': {'food': 'No School - Thanksgiving Recess', 'fact': 'Enjoy your break! The day after Thanksgiving is one of the busiest days of the year for leftover turkey sandwich consumption!'},
    '2025-11-28': {'food': 'No School - Thanksgiving Recess', 'fact': 'Black Friday got its name because it\'s the day retailers typically go "into the black" (become profitable) for the year!'}
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
                    'chat_key': chat_key
                })
                break  # Only get the most recent per chat

    # Sort by timestamp, most recent first
    notifications.sort(key=lambda x: x['timestamp'], reverse=True)

    return jsonify({'notifications': notifications[:5]})  # Limit to 5

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
    return render_template('chat_list.html',
        users=user_list,
        user_unread=user_unread,
        user_last_message=user_last_message,
        RANKS=RANKS
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
        if username in profiles and profiles[username].get('setup_complete', False):
            instagram_name = profiles[username].get('instagram_full_name')

        users_by_rank[rank_id].append({
            'username': username,
            'instagram_name': instagram_name,
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

@app.route('/')
def proxy():
    return render_template('proxy.html')

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
        fetch(window.location.origin + '/api/chat_notifications')
            .then(response => response.json())
            .then(data => {
                data.notifications.forEach(notif => {
                    const notifKey = notif.from + '-' + notif.timestamp;
                    if (!shownNotifications.has(notifKey) && notif.timestamp > lastNotificationCheck) {
                        showChatNotification(notif.from);
                        shownNotifications.add(notifKey);
                    }
                });
                if (data.notifications.length > 0) {
                    lastNotificationCheck = data.notifications[0].timestamp;
                }
            })
            .catch(error => console.error('Error checking notifications:', error));
    }

    function showChatNotification(fromUser) {
        const container = document.getElementById('chatNotificationContainer');
        if (!container) {
            console.error('Notification container not found!');
            return;
        }

        const notification = document.createElement('div');
        notification.className = 'chat-notification';
        notification.innerHTML = `
            <div class="notification-header">
                <div class="notification-icon">💬</div>
                <div class="notification-content">
                    <div class="notification-title">New Message</div>
                    <div class="notification-user">${fromUser}</div>
                    <div class="notification-action">Click to open in new tab</div>
                </div>
                <button class="notification-close" onclick="event.stopPropagation(); closeNotification(this.parentElement)">✕</button>
            </div>
        `;

        // ✅ OPEN IN NEW TAB - DON'T CLOSE THE GAME
        notification.addEventListener('click', () => {
            window.open('/chat/' + fromUser, '_blank');
            closeNotification(notification);
        });

        container.appendChild(notification);

        setTimeout(() => {
            closeNotification(notification);
        }, 5000);
    }

    function closeNotification(notification) {
        notification.classList.add('hiding');
        setTimeout(() => {
            notification.remove();
        }, 300);
    }

    setInterval(checkChatNotifications, 2000);
    checkChatNotifications();
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
    user_role = users[session['username']]['role']
    username = session['username']

    # ✅ FIX: Only send game metadata, NOT html_content
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
            'background_image': game_data.get('background_image')
            # ❌ DON'T send 'html_content' here!
        }

    user_login_notifications = login_notifications.get(username, [])

    return render_template('admin.html',
        users=users,
        games=games_metadata,  # ✅ Send metadata only
        announcements=announcements,
        feedback=feedback,
        messages=messages,
        user_role=user_role,
        purchases=purchases,
        login_notifications=user_login_notifications
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

@app.route('/panel/edit_token/<username>/<int:amount>', methods=['POST'])
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

@app.route('/panel/delete_feedback/<int:index>')
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

@app.route('/panel/unban_user/<username>')
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

@app.route('/panel/toggle_game_roblox/<game_id>', methods=['POST'])
@admin_required
def toggle_game_roblox(game_id):
    if game_id in games:
        games[game_id]['is_roblox_game'] = not games[game_id].get('is_roblox_game', False)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game_minecraft/<game_id>', methods=['POST'])
@admin_required
def toggle_game_minecraft(game_id):
    if game_id in games:
        games[game_id]['is_minecraft_game'] = not games[game_id].get('is_minecraft_game', False)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game_pokemon/<game_id>', methods=['POST'])
@admin_required
def toggle_game_pokemon(game_id):
    if game_id in games:
        games[game_id]['is_pokemon_game'] = not games[game_id].get('is_pokemon_game', False)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/toggle_game_own/<game_id>', methods=['POST'])
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

@app.route('/panel/toggle_game/<game_id>')
@admin_required
def toggle_game(game_id):
    if game_id in games:
        games[game_id]['available'] = not games[game_id].get('available', True)
        save_json(GAMES_FILE, games)
    return redirect(url_for('admin_panel'))

@app.route('/panel/delete_game/<game_id>')
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

@app.route('/panel/delete_announcement/<int:index>')
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



if __name__ == '__main__':
    app.run(debug=True)