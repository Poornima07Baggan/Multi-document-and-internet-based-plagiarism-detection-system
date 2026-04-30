import sqlite3

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # 1. Existing Users Table
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        role TEXT NOT NULL)''')
    
    # 2. 🆕 NEW Courses Table
    conn.execute('''CREATE TABLE IF NOT EXISTS courses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        code TEXT UNIQUE NOT NULL,
                        teacher_id INTEGER NOT NULL)''')
    
    # 3. 🆕 NEW Enrollments Table (Links Students to Courses)
    conn.execute('''CREATE TABLE IF NOT EXISTS enrollments (
                        student_id INTEGER,
                        course_id INTEGER,
                        PRIMARY KEY (student_id, course_id))''')
    
    # 4. Assignments Table with Course Link
    conn.execute('''CREATE TABLE IF NOT EXISTS assignments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        course_id INTEGER,  
                        filename TEXT NOT NULL,
                        status TEXT DEFAULT 'Pending',
                        marks INTEGER,
                        comments TEXT)''')
    
    # Safely try to add course_id to assignments if the table already exists from an old version
    try:
        conn.execute('ALTER TABLE assignments ADD COLUMN course_id INTEGER')
    except:
        pass 
        
    conn.commit()
    conn.close()

from werkzeug.security import generate_password_hash
def register_user(username, email, password, role):
    conn = get_db_connection()
    try:
        hashed_password = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)',
                     (username, email, hashed_password, role))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()