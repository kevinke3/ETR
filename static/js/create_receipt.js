document.addEventListener('DOMContentLoaded', function() {
    let items = [];
    
    const itemsContainer = document.getElementById('itemsContainer');
    const addItemBtn = document.getElementById('addItemBtn');
    const subtotalElement = document.getElementById('subtotal');
    const vatAmountElement = document.getElementById('vatAmount');
    const totalAmountElement = document.getElementById('totalAmount');
    const generateReceiptBtn = document.getElementById('generateReceiptBtn');
    const clearFormBtn = document.getElementById('clearFormBtn');
    const receiptModal = document.getElementById('receiptModal');
    const receiptContent = document.getElementById('receiptContent');
    const closeReceiptBtn = document.getElementById('closeReceiptBtn');
    const printReceiptBtn = document.getElementById('printReceiptBtn');
    const saveReceiptBtn = document.getElementById('saveReceiptBtn');
    
    // Add new item row
    function addItemRow() {
        const itemRow = document.createElement('div');
        itemRow.className = 'item-row form-row';
        itemRow.innerHTML = `
            <div class="form-group">
                <input type="text" class="item-name" placeholder="Product Name" required>
            </div>
            <div class="form-group">
                <input type="number" class="item-quantity" placeholder="Qty" value="1" min="1" required>
            </div>
            <div class="form-group">
                <input type="number" class="item-price" placeholder="Price" step="0.01" min="0" required>
            </div>
            <div class="form-group">
                <span class="item-total">KSh 0.00</span>
            </div>
            <div class="form-group">
                <button type="button" class="btn btn-outline remove-item-btn" style="padding: 0.5rem;">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        itemsContainer.appendChild(itemRow);
        
        // Add event listeners to new inputs
        const inputs = itemRow.querySelectorAll('input');
        inputs.forEach(input => {
            input.addEventListener('input', updateItemTotal);
            input.addEventListener('input', updateTotals);
        });
        
        // Add event listener to remove button
        itemRow.querySelector('.remove-item-btn').addEventListener('click', function() {
            if (itemsContainer.children.length > 1) {
                itemRow.remove();
                updateTotals();
            }
        });
    }
    
    // Update individual item total
    function updateItemTotal() {
        const row = this.closest('.item-row');
        const quantity = parseFloat(row.querySelector('.item-quantity').value) || 0;
        const price = parseFloat(row.querySelector('.item-price').value) || 0;
        const total = quantity * price;
        
        row.querySelector('.item-total').textContent = `KSh ${total.toLocaleString()}`;
    }
    
    // Update all totals
    function updateTotals() {
        let subtotal = 0;
        
        document.querySelectorAll('.item-row').forEach(row => {
            const quantity = parseFloat(row.querySelector('.item-quantity').value) || 0;
            const price = parseFloat(row.querySelector('.item-price').value) || 0;
            subtotal += quantity * price;
        });
        
        const vatAmount = subtotal * 0.16;
        const totalAmount = subtotal + vatAmount;
        
        subtotalElement.textContent = `KSh ${subtotal.toLocaleString()}`;
        vatAmountElement.textContent = `KSh ${vatAmount.toLocaleString()}`;
        totalAmountElement.textContent = `KSh ${totalAmount.toLocaleString()}`;
    }
    
    // Generate receipt
    async function generateReceipt() {
        // Validate form
        let valid = true;
        const items = [];
        
        document.querySelectorAll('.item-row').forEach(row => {
            const name = row.querySelector('.item-name').value.trim();
            const quantity = parseFloat(row.querySelector('.item-quantity').value);
            const price = parseFloat(row.querySelector('.item-price').value);
            
            if (!name || isNaN(quantity) || quantity <= 0 || isNaN(price) || price < 0) {
                valid = false;
                return;
            }
            
            items.push({
                name: name,
                quantity: quantity,
                price: price
            });
        });
        
        if (!valid || items.length === 0) {
            alert('Please fill in all item fields correctly.');
            return;
        }
        
        const receiptData = {
            customer_name: document.getElementById('customerName').value || 'Walk-in Customer',
            customer_pin: document.getElementById('customerPIN').value,
            payment_method: document.getElementById('paymentMethod').value,
            items: items
        };
        
        try {
            const response = await fetch('/create-receipt', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(receiptData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                showReceipt(result);
            } else {
                alert('Error generating receipt: ' + result.error);
            }
        } catch (error) {
            alert('Error generating receipt: ' + error.message);
        }
    }
    
    // Show receipt in modal
    function showReceipt(result) {
        const subtotal = result.items.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        const vatAmount = subtotal * 0.16;
        const totalAmount = subtotal + vatAmount;
        
        let itemsHTML = '';
        result.items.forEach(item => {
            const itemTotal = item.price * item.quantity;
            itemsHTML += `
                <tr>
                    <td>${item.name}</td>
                    <td>${item.quantity}</td>
                    <td>KSh ${item.price.toLocaleString()}</td>
                    <td>KSh ${itemTotal.toLocaleString()}</td>
                </tr>
            `;
        });
        
        receiptContent.innerHTML = `
            <div class="receipt">
                <div class="receipt-header">
                    <h2>Tech Solutions Ltd</h2>
                    <p>KRA PIN: P051234567M</p>
                    <p>Electronic Tax Receipt</p>
                </div>
                <div class="receipt-body">
                    <p><strong>Receipt No:</strong> ${result.receipt_number}</p>
                    <p><strong>Date & Time:</strong> ${new Date().toLocaleString()}</p>
                    <p><strong>Customer:</strong> ${result.customer_name}</p>
                    <p><strong>Payment Method:</strong> ${result.payment_method}</p>
                    
                    <table class="receipt-items">
                        <thead>
                            <tr>
                                <th>Item</th>
                                <th>Qty</th>
                                <th>Price</th>
                                <th>Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${itemsHTML}
                        </tbody>
                    </table>
                    
                    <div class="receipt-totals">
                        <div class="summary-row">
                            <span>Subtotal:</span>
                            <span>KSh ${subtotal.toLocaleString()}</span>
                        </div>
                        <div class="summary-row">
                            <span>VAT (16%):</span>
                            <span>KSh ${vatAmount.toLocaleString()}</span>
                        </div>
                        <div class="summary-row summary-total">
                            <span>Total:</span>
                            <span>KSh ${totalAmount.toLocaleString()}</span>
                        </div>
                    </div>
                </div>
                <div class="qr-code">
                    <img src="data:image/png;base64,${result.qr_code}" alt="QR Code" style="width: 120px; height: 120px;">
                </div>
                <div class="receipt-footer">
                    <p>Thank you for your business!</p>
                    <p>This is an electronically generated receipt</p>
                    <p>For verification, scan QR code</p>
                </div>
            </div>
        `;
        
        receiptModal.style.display = 'flex';
        
        // Store receipt ID for saving
        saveReceiptBtn.dataset.receiptId = result.receipt_id;
    }
    
    // Clear form
    function clearForm() {
        document.getElementById('customerName').value = '';
        document.getElementById('customerPIN').value = '';
        document.getElementById('paymentMethod').value = 'Cash';
        
        // Keep only one item row and clear it
        while (itemsContainer.children.length > 1) {
            itemsContainer.lastChild.remove();
        }
        
        const firstRow = itemsContainer.firstElementChild;
        firstRow.querySelector('.item-name').value = '';
        firstRow.querySelector('.item-quantity').value = '1';
        firstRow.querySelector('.item-price').value = '';
        firstRow.querySelector('.item-total').textContent = 'KSh 0.00';
        
        updateTotals();
    }
    
    // Event listeners
    addItemBtn.addEventListener('click', addItemRow);
    generateReceiptBtn.addEventListener('click', generateReceipt);
    clearFormBtn.addEventListener('click', clearForm);
    closeReceiptBtn.addEventListener('click', function() {
        receiptModal.style.display = 'none';
        clearForm();
    });
    
    printReceiptBtn.addEventListener('click', function() {
        window.print();
    });
    
    saveReceiptBtn.addEventListener('click', function() {
        window.location.href = `/receipt/${this.dataset.receiptId}`;
    });
    
    // Initialize event listeners for first row
    document.querySelectorAll('.item-row input').forEach(input => {
        input.addEventListener('input', updateItemTotal);
        input.addEventListener('input', updateTotals);
    });
    
    document.querySelector('.remove-item-btn').addEventListener('click', function() {
        // Don't remove the first row if it's the only one
        if (itemsContainer.children.length > 1) {
            this.closest('.item-row').remove();
            updateTotals();
        }
    });
    
    // Initialize totals
    updateTotals();
});