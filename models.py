from database import get_db
from datetime import datetime

class Receipt:
    @staticmethod
    def create(receipt_data):
        db = get_db()
        # Implementation here
        
    @staticmethod
    def get_by_id(receipt_id):
        db = get_db()
        return db.execute(
            'SELECT * FROM receipts WHERE id = ?', (receipt_id,)
        ).fetchone()

class ReceiptItem:
    @staticmethod
    def get_by_receipt(receipt_id):
        db = get_db()
        return db.execute(
            'SELECT * FROM receipt_items WHERE receipt_id = ?', (receipt_id,)
        ).fetchall()