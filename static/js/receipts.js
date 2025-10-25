// Receipts functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('Receipts page loaded');
    
    // Set default date values to today if not set
    const dateFrom = document.getElementById('date_from');
    const dateTo = document.getElementById('date_to');
    
    if (dateFrom && !dateFrom.value) {
        dateFrom.value = new Date().toISOString().split('T')[0];
    }
    
    if (dateTo && !dateTo.value) {
        dateTo.value = new Date().toISOString().split('T')[0];
    }
    
    // Add confirmation for filter reset
    const filterForm = document.querySelector('form');
    if (filterForm) {
        const clearButton = document.createElement('button');
        clearButton.type = 'button';
        clearButton.className = 'btn btn-outline';
        clearButton.textContent = 'Clear Filters';
        clearButton.style.marginLeft = '1rem';
        
        clearButton.addEventListener('click', function() {
            window.location.href = window.location.pathname;
        });
        
        const submitButton = filterForm.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.parentNode.appendChild(clearButton);
        }
    }
});