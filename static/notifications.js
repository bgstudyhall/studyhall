(function () {
  const POLL_INTERVAL = 2000;
  const BADGE_REFRESH_INTERVAL = 4000;
  const shown = new Set();
  let lastTimestamp = '';

  function ensureContainer() {
    let container = document.getElementById('chatNotificationContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'chatNotificationContainer';
      document.body.appendChild(container);
    }
    applyContainerStyles(container);
  }

  function applyContainerStyles(container) {
    const styleId = 'chatNotificationStyles';
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style');
      style.id = styleId;
      style.textContent = `
        #chatNotificationContainer {
          position: fixed;
          top: 16px;
          right: 16px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          z-index: 9999;
          max-width: 320px;
          width: calc(100vw - 32px);
        }
        .chat-notification {
          background: #fff;
          color: #111827;
          border-radius: 14px;
          box-shadow: 0 18px 50px rgba(17, 24, 39, 0.12);
          padding: 12px 14px;
          border: 1px solid #e5e7eb;
          cursor: pointer;
          transition: transform 0.1s ease, opacity 0.15s ease;
        }
        .chat-notification:hover { transform: translateY(-2px); }
        .chat-notification.hiding { opacity: 0; transform: translateY(-4px); }
        .notification-header { display: flex; gap: 10px; align-items: center; }
        .notification-icon {
          width: 36px; height: 36px; border-radius: 10px;
          background: #eef2ff;
          display: flex; align-items: center; justify-content: center;
          font-weight: 800; font-size: 1rem; color: #1f2937;
        }
        .notification-content { flex: 1; }
        .notification-title { font-weight: 700; font-size: 0.95rem; color: #111827; }
        .notification-user { font-size: 0.9rem; color: #4b5563; }
        .notification-action { font-size: 0.82rem; color: #6b7280; }
        .notification-close {
          background: transparent; color: #9ca3af; border: none;
          font-size: 1.1rem; cursor: pointer; padding: 4px;
        }
        .notification-close:hover { color: #f3f4f6; }
      `;
      document.head.appendChild(style);
    }
    return container;
  }

  function showNotification({ title, icon, user, action, onClick }) {
    ensureContainer();
    const container = document.getElementById('chatNotificationContainer');
    if (!container) return;

    const notification = document.createElement('div');
    notification.className = 'chat-notification';
    notification.innerHTML = `
      <div class="notification-header">
        <div class="notification-icon">${icon}</div>
        <div class="notification-content">
          <div class="notification-title">${title}</div>
          <div class="notification-user">${user}</div>
          <div class="notification-action">${action}</div>
        </div>
        <button class="notification-close" aria-label="Close">&times;</button>
      </div>
    `;
    notification.querySelector('.notification-close').addEventListener('click', (e) => {
      e.stopPropagation();
      hideNotification(notification);
    });
    notification.addEventListener('click', () => {
      if (onClick) onClick();
      hideNotification(notification);
    });

    container.appendChild(notification);
    setTimeout(() => hideNotification(notification), 8000);
  }

  function hideNotification(el) {
    el.classList.add('hiding');
    setTimeout(() => el.remove(), 250);
  }

  function pollChat() {
    fetch('/api/chat_notifications')
      .then((r) => r.json())
      .then((data) => {
        (data.notifications || []).forEach((notif) => {
          const key = `chat-${notif.from}-${notif.timestamp}`;
          if (shown.has(key) || notif.timestamp <= lastTimestamp) return;
          shown.add(key);
          lastTimestamp = notif.timestamp;
          const meta = mapType(notif.type || 'message');
          showNotification({
            title: meta.title,
            icon: meta.icon,
            user: notif.from,
            action: meta.action,
            onClick: () => (window.location.href = `/chat/${notif.from}`),
          });
        });
      })
      .catch(() => {});
  }

  function pollGroups() {
    fetch('/api/group_notifications')
      .then((r) => r.json())
      .then((data) => {
        (data.notifications || []).forEach((notif) => {
          const key = `group-${notif.group_id}-${notif.timestamp}`;
          if (shown.has(key) || notif.timestamp <= lastTimestamp) return;
          shown.add(key);
          lastTimestamp = notif.timestamp;
          const meta = mapGroupType(notif.message_type || 'message');
          showNotification({
            title: meta.title,
            icon: meta.icon,
            user: notif.group_name,
            action: `${meta.action} (${notif.from})`,
            onClick: () => (window.location.href = `/group/${notif.group_id}`),
          });
        });
      })
      .catch(() => {});
  }

  function pollLounge() {
    // Don't poll if we're currently in the lounge
    if (window.location.pathname === '/lounge') return;

    // Check if lounge notifications are enabled (default: true)
    const notificationsEnabled = localStorage.getItem('loungeNotificationsEnabled');
    if (notificationsEnabled === 'false') return;

    fetch('/api/lounge_notifications')
      .then((r) => r.json())
      .then((data) => {
        (data.notifications || []).forEach((notif) => {
          const key = `lounge-${notif.from}-${notif.timestamp}`;
          if (shown.has(key) || notif.timestamp <= lastTimestamp) return;
          shown.add(key);
          lastTimestamp = notif.timestamp;

          let icon = '💬';
          let title = 'New Lounge Message';
          if (notif.type === 'achievement') {
            icon = '🏆';
            title = 'Achievement Unlocked!';
          }

          showNotification({
            title: title,
            icon: icon,
            user: notif.from,
            action: notif.message.substring(0, 50),
            onClick: () => (window.location.href = '/lounge'),
          });
        });
      })
      .catch(() => {});
  }

  function mapType(type) {
    switch (type) {
      case 'rps_invite': return { title: 'RPS Challenge!', icon: '🎮', action: 'challenged you to Rock Paper Scissors' };
      case 'snap': return { title: 'New Snap!', icon: '📸', action: 'sent you a snap' };
      case 'voice': return { title: 'Voice Message', icon: '🎙️', action: 'sent you a voice message' };
      case 'token_gift': return { title: 'Token Gift!', icon: '🎁', action: 'sent you tokens' };
      default: return { title: 'New Message', icon: '💬', action: 'sent you a message' };
    }
  }

  function mapGroupType(type) {
    switch (type) {
      case 'snap': return { title: 'Group Snap!', icon: '📸', action: 'snap posted' };
      case 'voice': return { title: 'Group Voice', icon: '🎙️', action: 'voice message posted' };
      default: return { title: 'Group Message', icon: '👥', action: 'new message' };
    }
  }

  function refreshBadge() {
    const badge = document.getElementById('chatUnreadBadge');
    if (!badge) return;
    fetch('/api/chat/unread_count')
      .then((r) => r.json())
      .then((data) => {
        if (!data.success) return;
        const total = data.total || 0;
        if (total > 0) {
          badge.textContent = total;
          badge.style.display = 'inline-flex';
        } else {
          badge.style.display = 'none';
        }
      })
      .catch(() => {});
  }

  function start() {
    ensureContainer();
    pollChat();
    pollGroups();
    pollLounge();
    refreshBadge();
    setInterval(pollChat, POLL_INTERVAL);
    setInterval(pollGroups, POLL_INTERVAL);
    setInterval(pollLounge, POLL_INTERVAL);
    setInterval(refreshBadge, BADGE_REFRESH_INTERVAL);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
