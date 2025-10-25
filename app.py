from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import init_db, get_db
from models import Receipt, ReceiptItem
import json
from datetime import datetime
import qrcode
import io
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['DATABASE'] = 'instance/etr_database.db'

# Initialize database
init_db(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

# Simple user database (in production, use proper database)
users = {
    'admin': {'password': 'password', 'id': 1, 'kra_pin': 'P051234567M', 'business_name': 'Tech Solutions Ltd'}
}

@login_manager.user_loader
def load_user(user_id):
    for username, user_data in users.items():
        if user_data['id'] == int(user_id):
            return User(user_data['id'], username)
    return None

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    
    # Get today's stats
    today = datetime.now().strftime('%Y-%m-%d')
    
    today_receipts = db.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total_sales, 
               COALESCE(SUM(vat_amount), 0) as total_vat 
        FROM receipts 
        WHERE DATE(created_at) = ? AND user_id = ?
    ''', (today, current_user.id)).fetchone()
    
    # Get recent receipts
    recent_receipts = db.execute('''
        SELECT * FROM receipts 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 5
    ''', (current_user.id,)).fetchall()
    
    return render_template('dashboard.html', 
                         stats=today_receipts,
                         recent_receipts=recent_receipts)

@app.route('/create-receipt', methods=['GET', 'POST'])
@login_required
def create_receipt():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            db = get_db()
            
            # Generate receipt number
            receipt_count = db.execute(
                'SELECT COUNT(*) FROM receipts WHERE user_id = ?', 
                (current_user.id,)
            ).fetchone()[0]
            receipt_number = f"RCP-{current_user.id:03d}-{(receipt_count + 1):06d}"
            
            # Calculate totals
            subtotal = sum(item['price'] * item['quantity'] for item in data['items'])
            vat_amount = subtotal * 0.16  # 16% VAT
            total_amount = subtotal + vat_amount
            
            # Create receipt
            cursor = db.execute('''
                INSERT INTO receipts (receipt_number, user_id, subtotal, vat_amount, total_amount, 
                                    customer_name, customer_pin, payment_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (receipt_number, current_user.id, subtotal, vat_amount, total_amount,
                 data.get('customer_name', 'Walk-in Customer'), 
                 data.get('customer_pin', ''), 
                 data.get('payment_method', 'Cash')))
            
            receipt_id = cursor.lastrowid
            
            # Add receipt items
            for item in data['items']:
                db.execute('''
                    INSERT INTO receipt_items (receipt_id, product_name, quantity, unit_price, total_price)
                    VALUES (?, ?, ?, ?, ?)
                ''', (receipt_id, item['name'], item['quantity'], item['price'], item['price'] * item['quantity']))
            
            db.commit()
            
            # Generate QR code
            qr_data = {
                'receipt_number': receipt_number,
                'business_pin': users[current_user.username]['kra_pin'],
                'total_amount': total_amount,
                'vat_amount': vat_amount,
                'timestamp': datetime.now().isoformat()
            }
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            buffered = io.BytesIO()
            qr_img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            return jsonify({
                'success': True,
                'receipt_id': receipt_id,
                'receipt_number': receipt_number,
                'qr_code': qr_base64
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    return render_template('create_receipt.html')

@app.route('/receipts')
@login_required
def receipts():
    db = get_db()
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    # Get filter parameters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    receipt_search = request.args.get('search', '')
    
    query = 'SELECT * FROM receipts WHERE user_id = ?'
    params = [current_user.id]
    
    if date_from:
        query += ' AND DATE(created_at) >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND DATE(created_at) <= ?'
        params.append(date_to)
    if receipt_search:
        query += ' AND receipt_number LIKE ?'
        params.append(f'%{receipt_search}%')
    
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    receipts_data = db.execute(query, params).fetchall()
    
    # Get total count for pagination
    count_query = 'SELECT COUNT(*) FROM receipts WHERE user_id = ?'
    count_params = [current_user.id]
    
    if date_from:
        count_query += ' AND DATE(created_at) >= ?'
        count_params.append(date_from)
    if date_to:
        count_query += ' AND DATE(created_at) <= ?'
        count_params.append(date_to)
    if receipt_search:
        count_query += ' AND receipt_number LIKE ?'
        count_params.append(f'%{receipt_search}%')
    
    total_count = db.execute(count_query, count_params).fetchone()[0]
    
    return render_template('receipts.html', 
                         receipts=receipts_data,
                         page=page,
                         per_page=per_page,
                         total_count=total_count,
                         date_from=date_from,
                         date_to=date_to,
                         search=receipt_search)

@app.route('/receipt/<int:receipt_id>')
@login_required
def receipt_detail(receipt_id):
    db = get_db()
    
    receipt = db.execute('''
        SELECT * FROM receipts 
        WHERE id = ? AND user_id = ?
    ''', (receipt_id, current_user.id)).fetchone()
    
    if not receipt:
        flash('Receipt not found')
        return redirect(url_for('receipts'))
    
    items = db.execute('''
        SELECT * FROM receipt_items 
        WHERE receipt_id = ?
    ''', (receipt_id,)).fetchall()
    
    # Generate QR code for this receipt
    qr_data = {
        'receipt_number': receipt['receipt_number'],
        'business_pin': users[current_user.username]['kra_pin'],
        'total_amount': receipt['total_amount'],
        'vat_amount': receipt['vat_amount'],
        'timestamp': receipt['created_at']
    }
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(json.dumps(qr_data))
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    
    return render_template('receipt_detail.html', 
                         receipt=receipt, 
                         items=items, 
                         qr_code=qr_base64,
                         business_name=users[current_user.username]['business_name'],
                         kra_pin=users[current_user.username]['kra_pin'])

@app.route('/reports')
@login_required
def reports():
    db = get_db()
    
    # Get date range from request or default to current month
    date_from = request.args.get('date_from', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    
    # Get sales summary
    summary = db.execute('''
        SELECT 
            COUNT(*) as receipt_count,
            COALESCE(SUM(total_amount), 0) as total_sales,
            COALESCE(SUM(vat_amount), 0) as total_vat,
            COALESCE(AVG(total_amount), 0) as avg_receipt
        FROM receipts 
        WHERE user_id = ? AND DATE(created_at) BETWEEN ? AND ?
    ''', (current_user.id, date_from, date_to)).fetchone()
    
    # Get daily sales for chart
    daily_sales = db.execute('''
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as receipt_count,
            COALESCE(SUM(total_amount), 0) as daily_sales,
            COALESCE(SUM(vat_amount), 0) as daily_vat
        FROM receipts 
        WHERE user_id = ? AND DATE(created_at) BETWEEN ? AND ?
        GROUP BY DATE(created_at)
        ORDER BY date
    ''', (current_user.id, date_from, date_to)).fetchall()
    
    return render_template('reports.html',
                         summary=summary,
                         daily_sales=daily_sales,
                         date_from=date_from,
                         date_to=date_to)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data = users.get(username)
        if user_data and user_data['password'] == password:
            user = User(user_data['id'], username)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)