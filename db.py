import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def _connect(user, password):
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=user,
        password=password,
        database='recircuit_db',
    )

def get_db():
    return _connect(os.getenv('DB_USER'), os.getenv('DB_PASSWORD'))

def get_demo_db():
    # read-only account used by the DBMS Demonstration page
    return _connect(os.getenv('DEMO_DB_USER'), os.getenv('DEMO_DB_PASSWORD'))

def fetch_all(sql, params=None):
    conn = get_db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        return cur.fetchall()
    finally:
        conn.close()

def fetch_one(sql, params=None):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None

def execute(sql, params=None):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()