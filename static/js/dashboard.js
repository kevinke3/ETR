// Dashboard functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('ETR Dashboard loaded successfully');
    
    // Any dashboard-specific functionality can be added here
    // For example, real-time updates or charts
    // Update dashboard.js
class LiveDashboard {
    constructor() {
        this.statsInterval = null;
        this.activityInterval = null;
        this.init();
    }

    init() {
        this.startLiveUpdates();
        this.setupWebSocket();
    }

    startLiveUpdates() {
        // Refresh stats every 30 seconds
        this.statsInterval = setInterval(() => this.refreshStats(), 30000);
        
        // Check for new activity every 10 seconds
        this.activityInterval = setInterval(() => this.checkNewActivity(), 10000);
    }

    async refreshStats() {
        try {
            const response = await fetch('/api/live-stats');
            const data = await response.json();
            this.updateStatsDisplay(data);
        } catch (error) {
            console.error('Error refreshing stats:', error);
        }
    }

    updateStatsDisplay(data) {
        // Update the stats cards with new data
        document.querySelectorAll('.stat-card').forEach(card => {
            const statType = card.querySelector('h3').textContent.toLowerCase();
            const valueElement = card.querySelector('.stat-value');
            
            if (statType.includes('sales')) {
                valueElement.textContent = `KSh ${data.total_sales.toLocaleString()}`;
            } else if (statType.includes('vat')) {
                valueElement.textContent = `KSh ${data.total_vat.toLocaleString()}`;
            } else if (statType.includes('issued')) {
                valueElement.textContent = data.receipt_count;
            } else if (statType.includes('average')) {
                valueElement.textContent = `KSh ${data.avg_receipt.toLocaleString()}`;
            }
        });
    }

    setupWebSocket() {
        // WebSocket for real-time updates
        if (typeof io !== 'undefined') {
            const socket = io();
            socket.on('new_receipt', (data) => {
                this.addLiveActivity(data);
            });
        }
    }

    addLiveActivity(receipt) {
        const activityContainer = document.getElementById('liveActivity');
        const activityItem = document.createElement('div');
        activityItem.className = 'activity-item';
        activityItem.innerHTML = `
            <span class="activity-time">${new Date().toLocaleTimeString()}</span>
            <span class="activity-desc">New receipt ${receipt.receipt_number} - KSh ${receipt.total_amount.toLocaleString()}</span>
        `;
        activityContainer.insertBefore(activityItem, activityContainer.firstChild);
        
        // Limit to 10 items
        if (activityContainer.children.length > 10) {
            activityContainer.removeChild(activityContainer.lastChild);
        }
    }
}

new LiveDashboard();
    // Example: Auto-refresh dashboard every 30 seconds
    setInterval(() => {
        // In a real application, this would fetch updated stats
        console.log('Dashboard auto-refresh');
    }, 30000);
});