import os
import sqlite3
from app.config import settings

def get_db_path() -> str:
    return settings.DATABASE_URL.replace("sqlite:///", "")

def init_db():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT NOT NULL,
            vendor_name TEXT NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT,
            file_location TEXT,
            status TEXT DEFAULT 'RECORDED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_db_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn