// Game Lazy Loader - Progressive loading for large games
(function() {
    'use strict';

    // Create loading overlay
    function createLoadingScreen() {
        const overlay = document.createElement('div');
        overlay.id = 'game-loading-overlay';
        overlay.innerHTML = `
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <h2 class="loading-title">Loading Game...</h2>
                <div class="loading-bar-container">
                    <div class="loading-bar" id="game-loading-bar"></div>
                </div>
                <p class="loading-percentage" id="game-loading-percentage">0%</p>
                <p class="loading-tip">Tip: Large games may take a moment to load on slower connections</p>
            </div>
        `;

        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            #game-loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 9999;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }

            .loading-container {
                text-align: center;
                color: white;
                max-width: 400px;
                padding: 40px;
            }

            .loading-spinner {
                width: 60px;
                height: 60px;
                border: 5px solid rgba(255, 255, 255, 0.3);
                border-top-color: white;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 30px;
            }

            @keyframes spin {
                to { transform: rotate(360deg); }
            }

            .loading-title {
                font-size: 28px;
                font-weight: bold;
                margin-bottom: 20px;
                letter-spacing: -0.5px;
            }

            .loading-bar-container {
                width: 100%;
                height: 8px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                overflow: hidden;
                margin: 20px 0;
            }

            .loading-bar {
                height: 100%;
                background: white;
                width: 0%;
                transition: width 0.3s ease;
                box-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
            }

            .loading-percentage {
                font-size: 24px;
                font-weight: bold;
                margin: 10px 0;
            }

            .loading-tip {
                font-size: 14px;
                opacity: 0.8;
                margin-top: 20px;
            }
        `;

        document.head.appendChild(style);
        document.body.appendChild(overlay);
        return overlay;
    }

    // Update loading progress
    function updateProgress(percentage) {
        const bar = document.getElementById('game-loading-bar');
        const text = document.getElementById('game-loading-percentage');
        if (bar) bar.style.width = percentage + '%';
        if (text) text.textContent = Math.round(percentage) + '%';
    }

    // Remove loading screen
    function removeLoadingScreen() {
        const overlay = document.getElementById('game-loading-overlay');
        if (overlay) {
            overlay.style.opacity = '0';
            overlay.style.transition = 'opacity 0.5s ease';
            setTimeout(() => overlay.remove(), 500);
        }
    }

    // Lazy load scripts with progress tracking
    function lazyLoadScripts(scripts, callback) {
        if (scripts.length === 0) {
            callback();
            return;
        }

        const totalScripts = scripts.length;
        let loadedScripts = 0;

        scripts.forEach((src, index) => {
            const script = document.createElement('script');
            script.src = src;
            script.async = false; // Maintain order

            script.onload = () => {
                loadedScripts++;
                updateProgress((loadedScripts / totalScripts) * 100);

                if (loadedScripts === totalScripts) {
                    setTimeout(() => {
                        removeLoadingScreen();
                        callback();
                    }, 300);
                }
            };

            script.onerror = () => {
                console.error('Failed to load script:', src);
                loadedScripts++;
                updateProgress((loadedScripts / totalScripts) * 100);

                if (loadedScripts === totalScripts) {
                    setTimeout(() => {
                        removeLoadingScreen();
                        callback();
                    }, 300);
                }
            };

            document.head.appendChild(script);
        });
    }

    // Auto-detect and lazy load scripts
    window.initGameLoader = function(options = {}) {
        const {
            scripts = [],
            onComplete = () => {},
            showLoader = true
        } = options;

        if (showLoader && scripts.length > 0) {
            createLoadingScreen();
            lazyLoadScripts(scripts, onComplete);
        } else if (scripts.length > 0) {
            lazyLoadScripts(scripts, onComplete);
        } else {
            onComplete();
        }
    };

    // Auto-initialize if page has heavy content
    window.addEventListener('DOMContentLoaded', () => {
        // Simulate initial load progress
        const overlay = document.getElementById('game-loading-overlay');
        if (overlay) {
            let progress = 0;
            const interval = setInterval(() => {
                progress += 5;
                updateProgress(progress);
                if (progress >= 100) {
                    clearInterval(interval);
                    removeLoadingScreen();
                }
            }, 50);
        }
    });
})();
