// static/js/offline.js
// Offline functionality for when internet is unavailable
class OfflineManager {
    constructor() {
        this.isOnline = navigator.onLine;
        this.pendingReceipts = JSON.parse(localStorage.getItem('pendingReceipts') || '[]');
        this.init();
    }

    init() {
        window.addEventListener('online', () => this.handleOnline());
        window.addEventListener('offline', () => this.handleOffline());
        
        // Check if there are pending receipts to sync
        if (this.pendingReceipts.length > 0 && this.isOnline) {
            this.syncPendingReceipts();
        }
    }

    handleOnline() {
        this.isOnline = true;
        this.syncPendingReceipts();
        document.body.classList.remove('offline');
    }

    handleOffline() {
        this.isOnline = false;
        document.body.classList.add('offline');
        this.showOfflineNotification();
    }

    async syncPendingReceipts() {
        for (const receipt of this.pendingReceipts) {
            try {
                const response = await fetch('/create-receipt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(receipt)
                });
                
                if (response.ok) {
                    // Remove successfully synced receipt
                    this.pendingReceipts = this.pendingReceipts.filter(r => r !== receipt);
                    localStorage.setItem('pendingReceipts', JSON.stringify(this.pendingReceipts));
                }
            } catch (error) {
                console.error('Failed to sync receipt:', error);
            }
        }
    }

    storeReceiptOffline(receiptData) {
        this.pendingReceipts.push(receiptData);
        localStorage.setItem('pendingReceipts', JSON.stringify(this.pendingReceipts));
        this.showOfflineNotification();
    }

    showOfflineNotification() {
        // Show offline indicator
        const offlineIndicator = document.createElement('div');
        offlineIndicator.className = 'offline-indicator';
        offlineIndicator.innerHTML = `
            <i class="fas fa-wifi"></i>
            <span>Working offline. Receipts will sync when connection is restored.</span>
        `;
        document.body.appendChild(offlineIndicator);
    }
}

// Initialize offline manager
const offlineManager = new OfflineManager();