import sqlite3
import os
from flask import g

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            'instance/etr_database.db',
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    with app.app_context():
        db = get_db()
        
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                FOREIGN KEY (receipt_id) REFERENCES receipts (id)
            )
        ''')
        
        db.commit()