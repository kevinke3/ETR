from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime, timedelta
import qrcode
import io
import base64
import json
import os
import re
import secrets
import csv
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'etr-system-secret-key-2024'
app.config['DATABASE'] = 'instance/etr_database.db'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, role='user'):
        self.id = id
        self.username = username
        self.role = role

# Store login attempts for rate limiting
login_attempts = {}

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if user:
        return User(user['id'], user['username'], user['role'])
    return None

def get_db():
    """Get database connection"""
    db = sqlite3.connect(
        app.config['DATABASE'],
        detect_types=sqlite3.PARSE_DECLTYPES
    )
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize database tables"""
    with app.app_context():
        db = get_db()
        
        # Create users table
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT NOT NULL,
                kra_pin TEXT NOT NULL UNIQUE,
                phone_number TEXT NOT NULL,
                person_in_charge TEXT NOT NULL,
                town_city TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                is_active BOOLEAN DEFAULT 1,
                api_key TEXT,
                receipt_prefix TEXT DEFAULT 'RCP',
                vat_rate REAL DEFAULT 16.0,
                include_address BOOLEAN DEFAULT 1,
                auto_print BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create receipts table
        db.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_number TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                subtotal REAL NOT NULL,
                vat_amount REAL NOT NULL,
                total_amount REAL NOT NULL,
                customer_name TEXT DEFAULT 'Walk-in Customer',
                customer_pin TEXT DEFAULT '',
                payment_method TEXT DEFAULT 'Cash',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Create receipt items table
        db.execute('''
            CREATE TABLE IF NOT EXISTS receipt_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                FOREIGN KEY (receipt_id) REFERENCES receipts (id) ON DELETE CASCADE
            )
        ''')
        
        # Create imported receipts table
        db.execute('''
            CREATE TABLE IF NOT EXISTS imported_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                original_data TEXT NOT NULL,
                total_amount REAL NOT NULL,
                vat_amount REAL NOT NULL,
                receipt_number TEXT NOT NULL,
                qr_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Audit logs table
        db.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Create default admin user if not exists
        admin_exists = db.execute('SELECT id FROM users WHERE username = ?', ('admin',)).fetchone()
        if not admin_exists:
            db.execute('''
                INSERT INTO users (business_name, kra_pin, phone_number, person_in_charge, town_city, username, password_hash, role, api_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'Tech Solutions Ltd', 'P051234567M', '+254712345678', 
                'System Administrator', 'Nairobi', 'admin', 
                generate_password_hash('password'), 'admin', secrets.token_urlsafe(32)
            ))
        
        db.commit()

def get_user_data(user_id):
    """Get user data from database"""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if user:
        return dict(user)
    return None

def log_activity(user_id, action, details=None):
    """Log user activities for audit trail"""
    try:
        db = get_db()
        db.execute('''
            INSERT INTO audit_logs (user_id, action, details, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action, json.dumps(details) if details else None, 
              request.remote_addr, request.headers.get('User-Agent')))
        db.commit()
    except Exception as e:
        print(f"Failed to log activity: {e}")

def validate_kra_pin(pin):
    """Validate KRA PIN format"""
    if not pin:
        return False
    pattern = r'^[A-Z]\d{9}[A-Z]$'
    return bool(re.match(pattern, pin))

def validate_receipt_data(data):
    """Validate receipt data"""
    if 'items' not in data or not isinstance(data['items'], list):
        return False, "Invalid or missing items"
    
    if len(data['items']) == 0:
        return False, "At least one item is required"
    
    for i, item in enumerate(data['items']):
        if not all(k in item for k in ['name', 'quantity', 'price']):
            return False, f"Invalid item data at position {i+1}"
        
        if not item['name'] or not item['name'].strip():
            return False, f"Item name is required at position {i+1}"
        
        if item['quantity'] <= 0:
            return False, f"Quantity must be positive at position {i+1}"
        
        if item['price'] < 0:
            return False, f"Price cannot be negative at position {i+1}"
    
    # Validate customer PIN if provided
    if data.get('customer_pin') and not validate_kra_pin(data['customer_pin']):
        return False, "Invalid customer KRA PIN format"
    
    return True, "Valid"

def api_key_required(f):
    """Decorator for API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE api_key = ? AND is_active = 1', (api_key,)).fetchone()
        
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        
        # Set current user for the request
        request.user_data = dict(user)
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator for admin-only routes"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Administrator access required.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    user_data = get_user_data(current_user.id)
    
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
    
    # Log dashboard access
    log_activity(current_user.id, 'DASHBOARD_ACCESS')
    
    return render_template('dashboard.html', 
                         stats=today_receipts,
                         recent_receipts=recent_receipts,
                         user_data=user_data)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            business_name = request.form.get('business_name')
            kra_pin = request.form.get('kra_pin')
            phone_number = request.form.get('phone_number')
            person_in_charge = request.form.get('person_in_charge')
            town_city = request.form.get('town_city')
            username = request.form.get('username')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            # Validate inputs
            if not all([business_name, kra_pin, phone_number, person_in_charge, town_city, username, password]):
                flash('All fields are required.')
                return render_template('register.html')
            
            if password != confirm_password:
                flash('Passwords do not match.')
                return render_template('register.html')
            
            if not validate_kra_pin(kra_pin):
                flash('Invalid KRA PIN format. Format: A123456789X')
                return render_template('register.html')
            
            if len(password) < 6:
                flash('Password must be at least 6 characters long.')
                return render_template('register.html')
            
            db = get_db()
            
            # Check if username or KRA PIN already exists
            existing_user = db.execute(
                'SELECT id FROM users WHERE username = ? OR kra_pin = ?', 
                (username, kra_pin)
            ).fetchone()
            
            if existing_user:
                flash('Username or KRA PIN already exists.')
                return render_template('register.html')
            
            # Create new user
            password_hash = generate_password_hash(password)
            api_key = secrets.token_urlsafe(32)
            
            db.execute('''
                INSERT INTO users (business_name, kra_pin, phone_number, person_in_charge, 
                                 town_city, username, password_hash, api_key, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (business_name, kra_pin, phone_number, person_in_charge, 
                 town_city, username, password_hash, api_key, 'admin'))
            
            db.commit()
            
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash(f'Registration failed: {str(e)}')
    
    return render_template('register.html')

@app.route('/create-receipt', methods=['GET', 'POST'])
@login_required
def create_receipt():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validate receipt data
            is_valid, message = validate_receipt_data(data)
            if not is_valid:
                return jsonify({'success': False, 'error': message}), 400
            
            db = get_db()
            user_data = get_user_data(current_user.id)
            
            # Generate receipt number
            receipt_count = db.execute(
                'SELECT COUNT(*) FROM receipts WHERE user_id = ?', 
                (current_user.id,)
            ).fetchone()[0]
            receipt_prefix = user_data.get('receipt_prefix', 'RCP')
            receipt_number = f"{receipt_prefix}-{current_user.id:03d}-{(receipt_count + 1):06d}"
            
            # Calculate totals with configurable VAT rate
            vat_rate = user_data.get('vat_rate', 16.0) / 100
            subtotal = sum(item['price'] * item['quantity'] for item in data['items'])
            vat_amount = subtotal * vat_rate
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
                'business_pin': user_data['kra_pin'],
                'total_amount': total_amount,
                'vat_amount': vat_amount,
                'vat_rate': user_data.get('vat_rate', 16.0),
                'timestamp': datetime.now().isoformat()
            }
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            buffered = io.BytesIO()
            qr_img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            # Log receipt creation
            log_activity(current_user.id, 'RECEIPT_CREATED', {
                'receipt_number': receipt_number,
                'total_amount': total_amount,
                'item_count': len(data['items'])
            })
            
            return jsonify({
                'success': True,
                'receipt_id': receipt_id,
                'receipt_number': receipt_number,
                'customer_name': data.get('customer_name', 'Walk-in Customer'),
                'payment_method': data.get('payment_method', 'Cash'),
                'items': data['items'],
                'subtotal': subtotal,
                'vat_amount': vat_amount,
                'total_amount': total_amount,
                'qr_code': qr_base64
            })
            
        except Exception as e:
            # Log error
            log_activity(current_user.id, 'RECEIPT_CREATION_ERROR', {'error': str(e)})
            return jsonify({'success': False, 'error': str(e)}), 500
    
    user_data = get_user_data(current_user.id)
    return render_template('create_receipt.html', user_data=user_data)

@app.route('/import-receipt', methods=['GET', 'POST'])
@login_required
def import_receipt():
    if request.method == 'POST':
        try:
            if 'file' not in request.files:
                flash('No file selected.')
                return redirect(request.url)
            
            file = request.files['file']
            if file.filename == '':
                flash('No file selected.')
                return redirect(request.url)
            
            if file and file.filename.endswith('.json'):
                data = json.load(file)
            elif file and file.filename.endswith('.csv'):
                # Convert CSV to JSON
                csv_data = file.stream.read().decode('utf-8')
                data = parse_csv_receipt(csv_data)
            else:
                flash('Unsupported file format. Please upload JSON or CSV.')
                return redirect(request.url)
            
            # Extract total amount from imported data
            total_amount = extract_total_amount(data)
            if total_amount is None:
                flash('Could not extract total amount from the receipt data.')
                return redirect(request.url)
            
            # Calculate VAT (assuming 16%)
            vat_rate = 0.16
            subtotal = total_amount / (1 + vat_rate)
            vat_amount = total_amount - subtotal
            
            db = get_db()
            user_data = get_user_data(current_user.id)
            
            # Generate receipt number for imported receipt
            receipt_count = db.execute(
                'SELECT COUNT(*) FROM imported_receipts WHERE user_id = ?', 
                (current_user.id,)
            ).fetchone()[0]
            receipt_prefix = user_data.get('receipt_prefix', 'RCP')
            receipt_number = f"IMP-{receipt_prefix}-{current_user.id:03d}-{(receipt_count + 1):06d}"
            
            # Generate QR code
            qr_data = {
                'receipt_number': receipt_number,
                'business_pin': user_data['kra_pin'],
                'total_amount': total_amount,
                'vat_amount': vat_amount,
                'vat_rate': vat_rate * 100,
                'timestamp': datetime.now().isoformat(),
                'imported': True
            }
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            buffered = io.BytesIO()
            qr_img.save(buffered, format="PNG")
            qr_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            # Save imported receipt
            db.execute('''
                INSERT INTO imported_receipts (user_id, original_data, total_amount, vat_amount, receipt_number, qr_code)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (current_user.id, json.dumps(data), total_amount, vat_amount, receipt_number, qr_base64))
            
            db.commit()
            
            # Log import
            log_activity(current_user.id, 'RECEIPT_IMPORTED', {
                'receipt_number': receipt_number,
                'total_amount': total_amount,
                'source_file': file.filename
            })
            
            flash(f'Receipt imported successfully! Total: KSh {total_amount:,.2f}')
            return redirect(url_for('view_imported_receipts'))
            
        except Exception as e:
            flash(f'Error importing receipt: {str(e)}')
    
    return render_template('import_receipt.html')

def extract_total_amount(data):
    """Extract total amount from various receipt formats"""
    if isinstance(data, dict):
        # Try common total amount fields
        for field in ['total', 'total_amount', 'amount', 'grand_total', 'final_amount']:
            if field in data and isinstance(data[field], (int, float)):
                return float(data[field])
        
        # Check nested structures
        if 'summary' in data and isinstance(data['summary'], dict):
            for field in ['total', 'total_amount', 'amount']:
                if field in data['summary'] and isinstance(data['summary'][field], (int, float)):
                    return float(data['summary'][field])
    
    elif isinstance(data, list):
        # If it's a list, check the last item or look for totals
        for item in data:
            if isinstance(item, dict) and 'total' in item:
                return float(item['total'])
    
    return None

def parse_csv_receipt(csv_data):
    """Parse CSV receipt data"""
    reader = csv.DictReader(csv_data.splitlines())
    items = []
    total = 0
    
    for row in reader:
        if 'total' in row.lower() or 'amount' in row.lower():
            # This might be a total row
            for key, value in row.items():
                if value and any(word in key.lower() for word in ['total', 'amount', 'sum']):
                    try:
                        total = float(value)
                        break
                    except ValueError:
                        continue
        else:
            # This is an item row
            items.append(row)
    
    return {'items': items, 'total': total}

@app.route('/imported-receipts')
@login_required
def view_imported_receipts():
    db = get_db()
    imported_receipts = db.execute('''
        SELECT * FROM imported_receipts 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (current_user.id,)).fetchall()
    
    return render_template('imported_receipts.html', receipts=imported_receipts)

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
    
    # Log receipts view
    log_activity(current_user.id, 'RECEIPTS_VIEWED', {
        'filters': {'date_from': date_from, 'date_to': date_to, 'search': receipt_search}
    })
    
    user_data = get_user_data(current_user.id)
    return render_template('receipts.html', 
                         receipts=receipts_data,
                         page=page,
                         per_page=per_page,
                         total_count=total_count,
                         date_from=date_from,
                         date_to=date_to,
                         search=receipt_search,
                         user_data=user_data)

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
    user_data = get_user_data(current_user.id)
    qr_data = {
        'receipt_number': receipt['receipt_number'],
        'business_pin': user_data['kra_pin'],
        'total_amount': receipt['total_amount'],
        'vat_amount': receipt['vat_amount'],
        'vat_rate': user_data.get('vat_rate', 16.0),
        'timestamp': receipt['created_at']
    }
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(json.dumps(qr_data))
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    
    # Log receipt view
    log_activity(current_user.id, 'RECEIPT_VIEWED', {'receipt_id': receipt_id})
    
    return render_template('receipt_detail.html', 
                         receipt=receipt, 
                         items=items, 
                         qr_code=qr_base64,
                         user_data=user_data)

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
    
    # Log report generation
    log_activity(current_user.id, 'REPORT_GENERATED', {
        'date_from': date_from,
        'date_to': date_to
    })
    
    user_data = get_user_data(current_user.id)
    return render_template('reports.html',
                         summary=summary,
                         daily_sales=daily_sales,
                         date_from=date_from,
                         date_to=date_to,
                         user_data=user_data)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    db = get_db()
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Update user settings
            update_fields = []
            update_values = []
            
            business_fields = ['business_name', 'kra_pin', 'phone_number', 'person_in_charge', 'town_city']
            receipt_fields = ['receipt_prefix', 'vat_rate', 'include_address', 'auto_print']
            
            for field in business_fields + receipt_fields:
                if field in data:
                    update_fields.append(f"{field} = ?")
                    update_values.append(data[field])
            
            if update_fields:
                update_values.append(current_user.id)
                db.execute(f'''
                    UPDATE users SET {', '.join(update_fields)} 
                    WHERE id = ?
                ''', update_values)
                db.commit()
            
            # Log settings update
            log_activity(current_user.id, 'SETTINGS_UPDATED', {
                'updated_fields': list(data.keys())
            })
            
            return jsonify({'success': True, 'message': 'Settings updated successfully'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    user_data = get_user_data(current_user.id)
    return render_template('settings.html', user_data=user_data)

@app.route('/settings/users')
@login_required
@admin_required
def manage_users():
    db = get_db()
    users = db.execute('SELECT id, username, role, is_active, created_at FROM users WHERE id != ?', (current_user.id,)).fetchall()
    user_data = get_user_data(current_user.id)
    return render_template('manage_users.html', users=users, user_data=user_data)

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    try:
        data = request.get_json()
        
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'user')
        
        if not all([username, password]):
            return jsonify({'success': False, 'error': 'Username and password are required'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        db = get_db()
        
        # Check if username exists
        existing_user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        
        # Create new user
        password_hash = generate_password_hash(password)
        api_key = secrets.token_urlsafe(32)
        
        db.execute('''
            INSERT INTO users (business_name, kra_pin, phone_number, person_in_charge, 
                             town_city, username, password_hash, api_key, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            'New Business', 'P000000000A', '+254700000000', 
            'User', 'Nairobi', username, password_hash, api_key, role
        ))
        
        db.commit()
        
        log_activity(current_user.id, 'USER_CREATED', {'username': username, 'role': role})
        
        return jsonify({'success': True, 'message': 'User created successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['PUT', 'DELETE'])
@login_required
@admin_required
def manage_user(user_id):
    try:
        db = get_db()
        
        if request.method == 'PUT':
            data = request.get_json()
            
            updates = []
            values = []
            
            if 'role' in data:
                updates.append('role = ?')
                values.append(data['role'])
            
            if 'is_active' in data:
                updates.append('is_active = ?')
                values.append(data['is_active'])
            
            if updates:
                values.append(user_id)
                db.execute(f'UPDATE users SET {", ".join(updates)} WHERE id = ?', values)
                db.commit()
            
            log_activity(current_user.id, 'USER_UPDATED', {'user_id': user_id, 'updates': data})
            return jsonify({'success': True, 'message': 'User updated successfully'})
        
        elif request.method == 'DELETE':
            db.execute('DELETE FROM users WHERE id = ?', (user_id,))
            db.commit()
            
            log_activity(current_user.id, 'USER_DELETED', {'user_id': user_id})
            return jsonify({'success': True, 'message': 'User deleted successfully'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backup')
@login_required
def create_backup():
    """Create database backup"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)
        
        backup_file = f"{backup_dir}/etr_backup_{timestamp}.db"
        
        # Copy database file
        import shutil
        shutil.copy2(app.config['DATABASE'], backup_file)
        
        # Log backup creation
        log_activity(current_user.id, 'BACKUP_CREATED', {'backup_file': backup_file})
        
        return jsonify({'success': True, 'backup_file': backup_file, 'timestamp': timestamp})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/kra-report')
@login_required
def generate_kra_report():
    """Generate KRA-compliant report"""
    db = get_db()
    
    date_from = request.args.get('date_from', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    
    # Get receipts for period
    receipts = db.execute('''
        SELECT * FROM receipts 
        WHERE user_id = ? AND DATE(created_at) BETWEEN ? AND ?
        ORDER BY created_at
    ''', (current_user.id, date_from, date_to)).fetchall()
    
    user_data = get_user_data(current_user.id)
    
    # Format for KRA submission
    kra_data = {
        'business_pin': user_data['kra_pin'],
        'business_name': user_data['business_name'],
        'period': f"{date_from} to {date_to}",
        'report_generated': datetime.now().isoformat(),
        'total_receipts': len(receipts),
        'total_sales': sum(receipt['total_amount'] for receipt in receipts),
        'total_vat': sum(receipt['vat_amount'] for receipt in receipts),
        'receipts': []
    }
    
    for receipt in receipts:
        items = db.execute('SELECT * FROM receipt_items WHERE receipt_id = ?', (receipt['id'],)).fetchall()
        
        kra_data['receipts'].append({
            'receipt_number': receipt['receipt_number'],
            'date_time': receipt['created_at'],
            'customer_name': receipt['customer_name'],
            'customer_pin': receipt['customer_pin'],
            'subtotal': receipt['subtotal'],
            'vat_amount': receipt['vat_amount'],
            'total_amount': receipt['total_amount'],
            'items_count': len(items),
            'payment_method': receipt['payment_method']
        })
    
    # Log KRA report generation
    log_activity(current_user.id, 'KRA_REPORT_GENERATED', {
        'date_from': date_from,
        'date_to': date_to,
        'receipt_count': len(receipts)
    })
    
    return jsonify(kra_data)

@app.route('/api/v1/receipts', methods=['POST'])
@api_key_required
def api_create_receipt():
    """API endpoint for POS system integration"""
    try:
        data = request.get_json()
        user_data = request.user_data
        
        # Validate receipt data
        is_valid, message = validate_receipt_data(data)
        if not is_valid:
            return jsonify({'success': False, 'error': message}), 400
        
        db = get_db()
        
        # Generate receipt number
        receipt_count = db.execute(
            'SELECT COUNT(*) FROM receipts WHERE user_id = ?', 
            (user_data['id'],)
        ).fetchone()[0]
        receipt_number = f"{user_data['receipt_prefix']}-{user_data['id']:03d}-{(receipt_count + 1):06d}"
        
        # Calculate totals
        vat_rate = user_data.get('vat_rate', 16.0) / 100
        subtotal = sum(item['price'] * item['quantity'] for item in data['items'])
        vat_amount = subtotal * vat_rate
        total_amount = subtotal + vat_amount
        
        # Create receipt
        cursor = db.execute('''
            INSERT INTO receipts (receipt_number, user_id, subtotal, vat_amount, total_amount, 
                                customer_name, customer_pin, payment_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (receipt_number, user_data['id'], subtotal, vat_amount, total_amount,
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
            'business_pin': user_data['kra_pin'],
            'total_amount': total_amount,
            'vat_amount': vat_amount,
            'vat_rate': user_data.get('vat_rate', 16.0),
            'timestamp': datetime.now().isoformat()
        }
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(json.dumps(qr_data))
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        qr_img.save(buffered, format="PNG")
        qr_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        # Log API receipt creation
        log_activity(user_data['id'], 'API_RECEIPT_CREATED', {
            'receipt_number': receipt_number,
            'total_amount': total_amount,
            'source': 'API'
        })
        
        return jsonify({
            'success': True,
            'receipt_id': receipt_id,
            'receipt_number': receipt_number,
            'customer_name': data.get('customer_name', 'Walk-in Customer'),
            'payment_method': data.get('payment_method', 'Cash'),
            'subtotal': subtotal,
            'vat_amount': vat_amount,
            'total_amount': total_amount,
            'qr_code': qr_base64,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/receipts/<int:receipt_id>')
@login_required
def api_receipt_detail(receipt_id):
    """API endpoint to get receipt details"""
    db = get_db()
    
    receipt = db.execute('''
        SELECT * FROM receipts 
        WHERE id = ? AND user_id = ?
    ''', (receipt_id, current_user.id)).fetchone()
    
    if not receipt:
        return jsonify({'error': 'Receipt not found'}), 404
    
    items = db.execute('''
        SELECT * FROM receipt_items 
        WHERE receipt_id = ?
    ''', (receipt_id,)).fetchall()
    
    return jsonify({
        'receipt': dict(receipt),
        'items': [dict(item) for item in items]
    })

@app.route('/analytics')
@login_required
def analytics():
    """Advanced analytics dashboard"""
    # Implementation for analytics data
    return render_template('analytics.html')

@app.route('/api/analytics-data')
@login_required
def analytics_data():
    """API endpoint for analytics data"""
    # Return analytics data in JSON format
    pass

@app.route('/mobile-receipt/<int:receipt_id>')
@login_required
def mobile_receipt(receipt_id):
    """Mobile-optimized receipt view"""
    # Similar to receipt_detail but mobile-optimized
    pass

@app.route('/advanced-reports')
@login_required
def advanced_reports():
    """Advanced reporting interface"""
    return render_template('advanced_reports.html')

@app.route('/inventory')
@login_required
def inventory():
    """Inventory management"""
    return render_template('inventory.html')

@app.route('/api/live-stats')
@login_required
def live_stats():
    """Real-time statistics for dashboard"""
    # Return current stats for live updates
    pass

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Rate limiting
    ip_address = request.remote_addr
    now = datetime.now()
    
    if ip_address in login_attempts:
        attempts = login_attempts[ip_address]
        # Clear old attempts
        attempts = [attempt for attempt in attempts if now - attempt < timedelta(minutes=5)]
        if len(attempts) >= 5:
            flash('Too many login attempts. Please try again in 5 minutes.')
            return render_template('login.html')
        login_attempts[ip_address] = attempts
    else:
        login_attempts[ip_address] = []
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        db = get_db()
        user_data = db.execute('SELECT * FROM users WHERE username = ? AND is_active = 1', (username,)).fetchone()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data['id'], user_data['username'], user_data['role'])
            login_user(user)
            
            # Log successful login
            log_activity(user_data['id'], 'LOGIN_SUCCESS', {'ip_address': ip_address})
            
            # Clear login attempts for this IP
            if ip_address in login_attempts:
                del login_attempts[ip_address]
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            # Log failed login attempt
            if ip_address not in login_attempts:
                login_attempts[ip_address] = []
            login_attempts[ip_address].append(now)
            
            log_activity(None, 'LOGIN_FAILED', {
                'username': username,
                'ip_address': ip_address
            })
            
            flash('Invalid credentials. Please try again.')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    # Log logout
    log_activity(current_user.id, 'LOGOUT')
    logout_user()
    return redirect(url_for('login'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('instance', exist_ok=True)
    os.makedirs('backups', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5000)