# Idle Dice Achievement → StudyHall Token System

## Overview
This system automatically awards StudyHall tokens when players achieve the "Millionaire" achievement in Idle Dice (reaching 1M points).

## Features
✅ **One-time claim per account** - Each user can only claim tokens once, even if they reset their game
✅ **Automatic detection** - The system monitors the game and automatically claims when achievement is reached
✅ **Beautiful notification** - Players see an animated popup when tokens are awarded
✅ **Transaction logging** - All token awards are logged in the system

## How It Works

### 1. **Backend (Flask)**
- **Data Files**:
  - `data/idle_dice_achievements.json` - Defines available achievements and token rewards
  - `data/idle_dice_claims.json` - Tracks which users have claimed which achievements

- **API Endpoint**: `/api/claim_idle_dice_achievement`
  - Method: POST
  - Requires login
  - Validates achievement hasn't been claimed before
  - Awards tokens and logs transaction

### 2. **Frontend (JavaScript)**
- **File**: `static/idle_dice_achievement_hook.js`
- **Function**:
  - Monitors localStorage every 3 seconds for game save data
  - Detects when player reaches 1M points
  - Automatically calls the API to claim tokens
  - Shows animated notification

### 3. **Game Integration**
- The hook script is automatically injected into the Idle Dice game
- Detection happens in `flask_app.py` line ~2809
- Works by checking if game HTML contains "idle-dice" or game name contains "idle dice"

## Current Configuration

| Achievement | Requirement | Token Reward |
|-------------|-------------|--------------|
| Millionaire (`points1m`) | Reach 1,000,000 points | 10 tokens |

## Testing

1. **Play the Idle Dice game**
2. **Reach 1 Million points** (or modify your save data in localStorage)
3. **Watch for the notification** - Should appear automatically
4. **Check your token balance** - Should increase by 10 tokens

## Adding More Achievements

To add more achievements, edit `flask_app.py` around line 511:

```python
idle_dice_achievements = load_json(IDLE_DICE_ACHIEVEMENTS_FILE, {
    'points1m': {'name': 'Millionaire', 'description': 'Reach a total of 1M points', 'tokens': 10},
    'points1b': {'name': 'Billionaire', 'description': 'Reach a total of 1B points', 'tokens': 25},
    # Add more here...
})
```

Then update the JavaScript hook in `static/idle_dice_achievement_hook.js` to detect the new achievements.

## Files Modified

1. ✅ `flask_app.py` - Added achievement system backend
2. ✅ `static/idle_dice_achievement_hook.js` - Created frontend detection script

## Security Features

- ✅ Server-side validation - Can't fake achievements
- ✅ Login required - Must be authenticated
- ✅ One-time claim - Stored per username
- ✅ Transaction logging - All awards are logged

## Notes

- The hook checks localStorage keys that contain "idle", "dice", or "save"
- Multiple possible data structures are checked for compatibility
- The system looks for either the achievement flag or raw point count ≥ 1M
- Claim attempts are tracked to prevent spam

## Future Enhancements

Possible improvements:
- Add more achievements (Billionaire, Trillionaire, etc.)
- Create an achievements page showing progress
- Add achievement icons/badges to user profiles
- Implement achievement leaderboards
