/**
 * Idle Dice Achievement Hook for StudyHall Token Integration
 * This script monitors localStorage for achievement unlocks and claims tokens
 */

(function() {
    'use strict';

    // Configuration
    const ACHIEVEMENT_CHECK_INTERVAL = 3000; // Check every 3 seconds
    const ACHIEVEMENT_ID = 'points1m'; // Millionaire achievement
    const POINTS_THRESHOLD = 1000000; // 1 Million points

    // Track if we've already tried to claim
    let claimAttempted = false;

    /**
     * Check localStorage for game save data
     */
    function checkAchievement() {
        try {
            // Idle Dice stores data with keys like "Idle dice_totalScore"
            // Check for total score directly
            const totalScoreKey = Object.keys(localStorage).find(key =>
                key.includes('totalScore') && key.includes('Idle')
            );

            if (totalScoreKey) {
                const totalScore = parseFloat(localStorage.getItem(totalScoreKey)) || 0;

                console.log('[StudyHall] Current points:', totalScore);

                if (totalScore >= POINTS_THRESHOLD && !claimAttempted) {
                    console.log('[StudyHall] Millionaire achievement detected! Points:', totalScore);
                    claimAchievement();
                    claimAttempted = true;
                    return;
                }
            }

            // Also check if achievement is already unlocked in the game
            const achievementKey = Object.keys(localStorage).find(key =>
                key.includes('a_value_points1m') && key.includes('Idle')
            );

            if (achievementKey) {
                const achievementValue = parseFloat(localStorage.getItem(achievementKey)) || 0;
                if (achievementValue > 0 && !claimAttempted) {
                    console.log('[StudyHall] Millionaire achievement flag detected!');
                    claimAchievement();
                    claimAttempted = true;
                }
            }
        } catch (error) {
            console.error('[StudyHall] Error checking achievement:', error);
        }
    }

    /**
     * Claim the achievement tokens from the server
     */
    function claimAchievement() {
        fetch('/api/claim_idle_dice_achievement', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                achievement_id: ACHIEVEMENT_ID
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAchievementNotification(data);
            } else if (data.error === 'Achievement already claimed') {
                console.log('[StudyHall] Achievement already claimed previously');
            } else {
                console.error('[StudyHall] Error claiming achievement:', data.error);
            }
        })
        .catch(error => {
            console.error('[StudyHall] Network error claiming achievement:', error);
        });
    }

    /**
     * Show a notification when tokens are awarded
     */
    function showAchievementNotification(data) {
        // Create notification element
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 30px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            z-index: 999999;
            font-family: 'Arial', sans-serif;
            font-size: 16px;
            font-weight: bold;
            animation: slideIn 0.5s ease-out;
        `;

        notification.innerHTML = `
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="font-size: 40px;">🎉</div>
                <div>
                    <div style="font-size: 18px; margin-bottom: 5px;">Achievement Unlocked!</div>
                    <div style="font-size: 14px; opacity: 0.9;">${data.achievement_name}</div>
                    <div style="font-size: 16px; margin-top: 8px; color: #ffd700;">
                        +${data.tokens_awarded} Tokens! 💰
                    </div>
                    <div style="font-size: 12px; opacity: 0.8; margin-top: 5px;">
                        New Balance: ${data.new_balance} tokens
                    </div>
                </div>
            </div>
        `;

        // Add animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from {
                    transform: translateX(400px);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            @keyframes slideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(400px);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
        document.body.appendChild(notification);

        // Remove after 5 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.5s ease-in';
            setTimeout(() => {
                notification.remove();
            }, 500);
        }, 5000);

        console.log('[StudyHall] Achievement claimed successfully!', data);
    }

    // Start monitoring
    console.log('[StudyHall] Achievement hook initialized for Idle Dice');

    // Check immediately on load
    setTimeout(checkAchievement, 2000);

    // Then check periodically
    setInterval(checkAchievement, ACHIEVEMENT_CHECK_INTERVAL);

    // Also monitor localStorage changes
    window.addEventListener('storage', function(e) {
        if (e.key && (e.key.includes('idle') || e.key.includes('dice'))) {
            checkAchievement();
        }
    });

})();
