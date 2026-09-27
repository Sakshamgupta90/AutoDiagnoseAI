import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = 'vehicle_history.db'

def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database(db_path=DB_PATH):
    """Initializes the SQLite database with the exact schema from Section 5.3."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            vin TEXT,
            make TEXT,
            model TEXT,
            dtc_codes TEXT,
            symptom_text TEXT,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            ranked_causes TEXT, -- JSON
            confidence REAL,
            sources TEXT, -- JSON
            escalation_flag BOOLEAN,
            model_id TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            technician_id TEXT,
            decision TEXT,
            notes TEXT,
            decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            confirmed_cause TEXT,
            confirmed_fix TEXT,
            part_cost REAL,
            labour_hours REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("SQLite database initialized successfully.")

def get_service_history(vin: str, db_path=DB_PATH) -> List[Dict[str, Any]]:
    """Retrieves past service history and confirmed feedback for a VIN."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT j.id as job_id, j.created_at, j.symptom_text, 
               f.confirmed_cause, f.confirmed_fix 
        FROM jobs j
        JOIN feedback f ON j.id = f.job_id
        WHERE j.vin = ?
        ORDER BY j.created_at DESC
        LIMIT 5
    ''', (vin,))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return results

if __name__ == '__main__':
    initialize_database()
