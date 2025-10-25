// Create Receipt functionality
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
        itemRow.className = 'item-row';
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
    
    // Validate form
    function validateForm() {
        let valid = true;
        const items = [];
        
        document.querySelectorAll('.item-row').forEach(row => {
            const name = row.querySelector('.item-name').value.trim();
            const quantity = parseFloat(row.querySelector('.item-quantity').value);
            const price = parseFloat(row.querySelector('.item-price').value);
            
            if (!name || isNaN(quantity) || quantity <= 0 || isNaN(price) || price < 0) {
                valid = false;
                // Highlight invalid fields
                if (!name) row.querySelector('.item-name').style.borderColor = 'red';
                if (isNaN(quantity) || quantity <= 0) row.querySelector('.item-quantity').style.borderColor = 'red';
                if (isNaN(price) || price < 0) row.querySelector('.item-price').style.borderColor = 'red';
            } else {
                // Reset border color if valid
                row.querySelector('.item-name').style.borderColor = '';
                row.querySelector('.item-quantity').style.borderColor = '';
                row.querySelector('.item-price').style.borderColor = '';
                
                items.push({
                    name: name,
                    quantity: quantity,
                    price: price
                });
            }
        });
        
        return { valid, items };
    }
    
    // Generate receipt
    async function generateReceipt() {
        const validation = validateForm();
        
        if (!validation.valid || validation.items.length === 0) {
            alert('Please fill in all item fields correctly. Product name, quantity (>0), and price (≥0) are required.');
            return;
        }
        
        const receiptData = {
            customer_name: document.getElementById('customerName').value || 'Walk-in Customer',
            customer_pin: document.getElementById('customerPIN').value,
            payment_method: document.getElementById('paymentMethod').value,
            items: validation.items
        };
        
        // Show loading state
        generateReceiptBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
        generateReceiptBtn.disabled = true;
        
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
        } finally {
            // Reset button state
            generateReceiptBtn.innerHTML = 'Generate ETR Receipt';
            generateReceiptBtn.disabled = false;
        }
    }
    
    // Show receipt in modal
    function showReceipt(result) {
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
                    <h2>${document.querySelector('.business-info h3').nextElementSibling.textContent.replace('Name: ', '')}</h2>
                    <p>${document.querySelector('.business-info p:nth-child(3)').textContent}</p>
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
                            <span>KSh ${result.subtotal.toLocaleString()}</span>
                        </div>
                        <div class="summary-row">
                            <span>VAT (16%):</span>
                            <span>KSh ${result.vat_amount.toLocaleString()}</span>
                        </div>
                        <div class="summary-row summary-total">
                            <span>Total:</span>
                            <span>KSh ${result.total_amount.toLocaleString()}</span>
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
        if (!confirm('Are you sure you want to clear the form? All entered data will be lost.')) {
            return;
        }
        
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
    });
    
    printReceiptBtn.addEventListener('click', function() {
        const receiptElement = receiptContent.querySelector('.receipt');
        if (receiptElement) {
            const printWindow = window.open('', '_blank');
            printWindow.document.write(`
                <html>
                    <head>
                        <title>Print Receipt</title>
                        <style>
                            body { font-family: 'Courier New', monospace; margin: 0; padding: 20px; }
                            .receipt { max-width: 400px; margin: 0 auto; border: 2px solid #000; padding: 20px; }
                            .receipt-header { text-align: center; margin-bottom: 1.5rem; border-bottom: 1px dashed #000; padding-bottom: 1rem; }
                            .receipt-items { width: 100%; border-collapse: collapse; margin-bottom: 1rem; }
                            .receipt-items th, .receipt-items td { padding: 0.25rem 0; border-bottom: 1px dashed #ccc; text-align: left; }
                            .receipt-totals { border-top: 1px dashed #000; padding-top: 1rem; }
                            .summary-row { display: flex; justify-content: space-between; margin-bottom: 0.5rem; }
                            .summary-total { font-weight: bold; font-size: 1.2rem; border-top: 1px solid #000; padding-top: 0.5rem; }
                            .qr-code { text-align: center; margin: 1rem 0; }
                            .receipt-footer { text-align: center; font-size: 0.8rem; color: #666; border-top: 1px dashed #000; padding-top: 1rem; }
                        </style>
                    </head>
                    <body>
                        ${receiptElement.outerHTML}
                    </body>
                </html>
            `);
            printWindow.document.close();
            printWindow.print();
        }
    });
    
    saveReceiptBtn.addEventListener('click', function() {
        const receiptId = this.dataset.receiptId;
        if (receiptId) {
            window.location.href = `/receipt/${receiptId}`;
        }
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
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Ctrl + Enter to generate receipt
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            generateReceipt();
        }
        
        // Ctrl + + to add new item
        if (e.ctrlKey && e.key === '+') {
            e.preventDefault();
            addItemRow();
        }
    });
});