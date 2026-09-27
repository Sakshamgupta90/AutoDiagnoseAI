import sqlite3
import datetime
import os

DB_PATH = 'vehicle_history.db'

def get_connection(db_path=DB_PATH):
    return sqlite3.connect(db_path)

def initialize_database(db_path=DB_PATH):
    "\""Initializes the SQLite database with the required schema."\""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Create jobs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vin TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create diagnoses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    ''')

    # Create approvals table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    ''')

    # Create feedback table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            comments TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    ''')

    conn.commit()
    conn.close()

def insert_new_job(vin, status="PENDING", db_path=DB_PATH):
    "\""Inserts a new job and returns the job ID."\""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO jobs (vin, status)
        VALUES (?, ?)
    ''', (vin, status))
    
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return job_id

def update_job_status(job_id, new_status, db_path=DB_PATH):
    "\""Updates the status of an existing job."\""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE jobs
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (new_status, job_id))
    
    conn.commit()
    conn.close()

def retrieve_service_history(vin, db_path=DB_PATH):
    "\""Retrieves service history for a specific VIN."\""
    conn = get_connection(db_path)
    # Use Row factory to get dict-like objects
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM jobs WHERE vin = ? ORDER BY created_at DESC
    ''', (vin,))
    
    jobs = cursor.fetchall()
    
    history = []
    for job in jobs:
        job_dict = dict(job)
        job_id = job['id']
        
        # Get diagnoses
        cursor.execute('SELECT * FROM diagnoses WHERE job_id = ?', (job_id,))
        job_dict['diagnoses'] = [dict(row) for row in cursor.fetchall()]
        
        # Get approvals
        cursor.execute('SELECT * FROM approvals WHERE job_id = ?', (job_id,))
        job_dict['approvals'] = [dict(row) for row in cursor.fetchall()]
        
        # Get feedback
        cursor.execute('SELECT * FROM feedback WHERE job_id = ?', (job_id,))
        job_dict['feedback'] = [dict(row) for row in cursor.fetchall()]
        
        history.append(job_dict)
        
    conn.close()
    
    return history

if __name__ == '__main__':
    initialize_database()
    print('Database initialized.')
