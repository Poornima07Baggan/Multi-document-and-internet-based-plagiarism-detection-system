import os
import re
import time
import random
import string
import difflib
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup

import PyPDF2
import docx
import google.generativeai as genai

from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from utils import calculate_similarity
from database import init_db, get_db_connection, register_user

# 🚀 Configure Gemini (Paste your API key here!)
genai.configure(api_key="AIzaSyAoSqxPA9BxB-TN6YYrcugk7z65T-5nMjM")

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

init_db()

# 🚀 AUTOMATIC DB MIGRATION: Creates Tasks table and adds Total Marks safely!
conn = get_db_connection()
try:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            title TEXT,
            deadline TEXT,
            total_marks INTEGER DEFAULT 100,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    ''')
    conn.execute('ALTER TABLE assignments ADD COLUMN task_id INTEGER')
    conn.commit()
except:
    pass

try:
    conn.execute('ALTER TABLE tasks ADD COLUMN total_marks INTEGER DEFAULT 100')
    conn.commit()
except:
    pass
finally:
    conn.close()

# 🔐 LOGIN SETUP
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, email, role, username):
        self.id = id
        self.email = email
        self.role = role
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user: return User(id=user['id'], email=user['email'], role=user['role'], username=user['username'])
    return None

# 📄 FAST TEXT EXTRACTION
def extract_text(file):
    filename = file.filename.lower()
    text = ""
    try:
        if filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        elif filename.endswith('.docx'):
            doc = docx.Document(file)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif filename.endswith('.txt'):
            text = file.read().decode('utf-8', errors='ignore').strip()
        else:
            return "Unsupported file format. Please upload PDF, DOCX, or TXT."
    except Exception as e:
        print(f"\n❌ ERROR READING {filename}: {str(e)}\n")
        return ""
    
    text = text.strip()
    match = re.search(r'\n(?i)(References|Bibliography|Works Cited)\s*\n', text)
    if match: text = text[:match.start()] 
    return text.strip()

# 🌐 LIVE INTERNET PLAGIARISM SCANNER (Using Tavily API)
def check_internet_similarity(text):
    print("🔎 Checking internet plagiarism via Tavily API...")
    try:
        # 1. Clean the text by removing weird spacing and newlines
        clean_text = re.sub(r'\s+', ' ', text)
        
        # 2. Split into sentences and find a good, substantial one
        sentences = [s.strip() for s in re.split(r'[.!?]', clean_text) if len(s.strip()) > 60]
        
        if not sentences:
            return [] 
            
        # 3. 🧠 SMART QUERY: Take a solid chunk of words to give the AI context
        words = sentences[0].split()[:30]
        query = '"' + " ".join(words) + '"'
        
        print(f"👉 Searching Tavily for: {query}")
        
        # 4. Connect to the Tavily API
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": "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",
            "query": query,
            "search_depth": "basic",
            "max_results": 5
        }
        
        # 5. Fetch and parse the results
        res = requests.post(url, json=payload)
        
        # If the API key is wrong or rate-limited, this will catch the error
        res.raise_for_status() 
        
        data = res.json()
        
        links = []
        for result in data.get("results", []):
            link = result.get("url")
            if link and link not in links:
                links.append(link)

        print("Found URLs:", links)
        return links

    except Exception as e:
        print("Tavily API check error:", e)
        return []
    
      
      

# 🕵️‍♂️ AI PLAGIARISM INVESTIGATOR REPORT
def generate_ai_report(student_text, urls):
    if not urls: return "No significant internet matches found."
    prompt = f"Act as an expert academic plagiarism investigator. A student submitted text that directly matched these exact websites online: {', '.join(urls)}.\n\nStudent Text Snippet: {student_text[:1500]}\n\nWrite a short, professional 2-sentence report for the teacher stating that the text appears to be copied from the internet, and name the specific website URLs."
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "AI Report generation failed due to an API error."

# 🖍️ SIDE-BY-SIDE HIGHLIGHTER ENGINE
def get_highlighted_texts(text1, text2):
    sentences1 = [s for s in re.split(r'(?<=[.!?]) +|\n+', text1) if len(s.strip()) > 15]
    sentences2 = [s for s in re.split(r'(?<=[.!?]) +|\n+', text2) if len(s.strip()) > 15]
    h1, h2 = text1, text2
    for s1 in sentences1:
        for s2 in sentences2:
            if difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio() > 0.70:
                h1 = h1.replace(s1, f'<mark class="bg-danger text-white rounded px-1">{s1}</mark>')
                h2 = h2.replace(s2, f'<mark class="bg-danger text-white rounded px-1">{s2}</mark>')
    return h1, h2

# 🏠 ROUTES
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/student-login')
def student_login_page(): return render_template('student-login.html')

@app.route('/teacher-login')
def teacher_login_page(): return render_template('teacher-login.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username') 
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    success = register_user(username, email, password, role)
    template = 'student-login.html' if role == 'student' else 'teacher-login.html'
    if success: return render_template(template, success="Account created! You can now log in.")
    else: return render_template(template, error="Registration failed. Username or Email already taken.")

@app.route('/login', methods=['POST'])
def login():
    identifier = request.form.get('identifier') 
    password = request.form.get('password')
    role = request.form.get('role')
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ? OR username = ?', (identifier, identifier)).fetchone()
    conn.close()
    template = 'student-login.html' if role == 'student' else 'teacher-login.html'

    if user and check_password_hash(user['password'], password):
        if user['role'] != role: return render_template(template, error=f"Access denied. You are registered as a {user['role']}.")
        user_obj = User(id=user['id'], email=user['email'], role=user['role'], username=user['username'])
        login_user(user_obj)
        return redirect(url_for('student_portal')) if role == 'student' else redirect(url_for('teacher_portal'))
    return render_template(template, error="Invalid Username/Email or Password.")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/student-portal')
@login_required
def student_portal():
    if current_user.role != 'student': return redirect(url_for('index'))
    conn = get_db_connection()
    
    tasks = conn.execute('''
        SELECT t.*, c.name as course_name, u.username as teacher_name 
        FROM tasks t 
        JOIN courses c ON t.course_id = c.id 
        JOIN enrollments e ON c.id = e.course_id 
        JOIN users u ON c.teacher_id = u.id
        WHERE e.student_id = ? ORDER BY t.id DESC
    ''', (current_user.id,)).fetchall()
    
    assignments = conn.execute('''
        SELECT a.*, c.name as course_name, t.title as task_title, t.total_marks
        FROM assignments a 
        LEFT JOIN courses c ON a.course_id = c.id
        LEFT JOIN tasks t ON a.task_id = t.id
        WHERE a.student_id = ? ORDER BY a.id DESC
    ''', (current_user.id,)).fetchall()
    
    conn.close()
    return render_template('student-portal.html', assignments=assignments, tasks=tasks)

@app.route('/teacher-portal')
@login_required
def teacher_portal():
    if current_user.role != 'teacher': return redirect(url_for('index'))
    conn = get_db_connection()
    
    courses = conn.execute('SELECT * FROM courses WHERE teacher_id = ?', (current_user.id,)).fetchall()
    tasks = conn.execute('SELECT t.*, c.name as course_name FROM tasks t JOIN courses c ON t.course_id = c.id WHERE c.teacher_id = ?', (current_user.id,)).fetchall()
    
    assignments = conn.execute('''
        SELECT a.*, u.username as student_name, c.name as course_name, t.title as task_title, t.total_marks
        FROM assignments a 
        JOIN users u ON a.student_id = u.id 
        JOIN courses c ON a.course_id = c.id
        LEFT JOIN tasks t ON a.task_id = t.id
        WHERE c.teacher_id = ?
        ORDER BY a.id DESC
    ''', (current_user.id,)).fetchall()
    
    conn.close()
    return render_template('teacher-portal.html', assignments=assignments, courses=courses, tasks=tasks)

@app.route('/upload_assignment', methods=['POST'])
@login_required
def upload_assignment():
    if current_user.role != 'student': return redirect(url_for('index'))
    file = request.files.get('file')
    course_id = request.form.get('course_id') 
    task_id = request.form.get('task_id') 
    
    if course_id == 'none': course_id = None
    if task_id == 'none': task_id = None
        
    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = get_db_connection()
        conn.execute('INSERT INTO assignments (student_id, course_id, task_id, filename) VALUES (?, ?, ?, ?)', 
                     (current_user.id, course_id, task_id, filename))
        conn.commit()
        conn.close()
    return redirect(url_for('student_portal'))

@app.route('/delete_assignment/<int:assignment_id>', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    if current_user.role != 'student': return redirect(url_for('index'))
    conn = get_db_connection()
    assignment = conn.execute('SELECT * FROM assignments WHERE id = ? AND student_id = ?', (assignment_id, current_user.id)).fetchone()
    
    if assignment:
        if assignment['status'] == 'Graded':
            print(f"⚠️ Security Alert: User {current_user.username} attempted to delete a graded assignment.")
        else:
            conn.execute('DELETE FROM assignments WHERE id = ?', (assignment_id,))
            conn.commit()
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], assignment['filename'])
            if os.path.exists(file_path): 
                os.remove(file_path)
                
    conn.close()
    return redirect(url_for('student_portal'))

@app.route('/grade/<int:assignment_id>', methods=['POST'])
@login_required
def grade(assignment_id):
    if current_user.role != 'teacher': return redirect(url_for('index'))
    marks = request.form.get('marks')
    comments = request.form.get('comments')
    conn = get_db_connection()
    conn.execute('UPDATE assignments SET marks = ?, comments = ?, status = ? WHERE id = ?', (marks, comments, 'Graded', assignment_id))
    conn.commit()
    conn.close()
    return redirect(url_for('teacher_portal'))

@app.route('/download/<filename>')
@login_required
def download(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 🚀 THE MASTER ANALYSIS ROUTE
@app.route('/compare', methods=['POST'])
def compare():
    files = request.files.getlist("files")
    documents = []
    filenames = []
    
    for file in files:
        if file.filename == '': continue
        content = extract_text(file)
        if content.strip():
            documents.append(content)
            filenames.append(file.filename)

    template = 'teacher-portal.html' if current_user.is_authenticated and current_user.role == 'teacher' else 'index.html'
    
    assignments, courses, tasks = [], [], []
    if template == 'teacher-portal.html':
        conn = get_db_connection()
        assignments = conn.execute('''
            SELECT a.*, u.username as student_name, c.name as course_name, t.title as task_title, t.total_marks
            FROM assignments a 
            JOIN users u ON a.student_id = u.id 
            JOIN courses c ON a.course_id = c.id
            LEFT JOIN tasks t ON a.task_id = t.id
            WHERE c.teacher_id = ? ORDER BY a.id DESC
        ''', (current_user.id,)).fetchall()
        courses = conn.execute('SELECT * FROM courses WHERE teacher_id = ?', (current_user.id,)).fetchall()
        tasks = conn.execute('SELECT t.*, c.name as course_name FROM tasks t JOIN courses c ON t.course_id = c.id WHERE c.teacher_id = ?', (current_user.id,)).fetchall()
        conn.close()

    if len(documents) == 0:
        return render_template(template, error="⚠️ Could not read files.", assignments=assignments, courses=courses, tasks=tasks)

    # ---------------------------------------------------------
    # 🔀 SMART ROUTING: Internet vs. Peer-to-Peer
    # ---------------------------------------------------------
    internet_results = {}
    ai_report = None
    results = []
    detailed_comparisons = []

   # SCENARIO A: Single File Uploaded -> Check the Internet
    if len(documents) == 1:
        doc_text = documents[0]
        filename = filenames[0]
        words = doc_text.split()
        
        if len(words) > 20: # Make sure the text is long enough to query
            urls = check_internet_similarity(doc_text)
            if urls: 
                internet_results[filename] = urls
                ai_report = generate_ai_report(doc_text, urls)
            else:
                # 🆕 FIX: If no URLs are found, explicitly tell the dashboard it is safe!
                ai_report = f"✅ Excellent news! The scan is complete. No internet matches were found for '{filename}'. It appears to be 100% original."
        else:
            # 🆕 FIX: Handle documents that are too short to scan
            ai_report = f"⚠️ '{filename}' has fewer than 20 words. Please upload a longer document."

    # SCENARIO B: Multiple Files Uploaded -> Check Against Each Other
    elif len(documents) > 1:
        similarity_matrix = calculate_similarity(documents)
        for i in range(len(filenames)):
            for j in range(i + 1, len(filenames)):
                score = float(similarity_matrix[i][j] * 100) 
                results.append((filenames[i], filenames[j], round(score, 2)))
                if score > 1.0: 
                    h1, h2 = get_highlighted_texts(documents[i], documents[j])
                    detailed_comparisons.append({
                        'file1': filenames[i], 'file2': filenames[j],
                        'text1': h1, 'text2': h2, 'score': round(score, 2)
                    })
        results.sort(key=lambda x: x[2], reverse=True)
        detailed_comparisons.sort(key=lambda x: x['score'], reverse=True)

    # Return the results to the dashboard
    return render_template(template, results=results, assignments=assignments, courses=courses, tasks=tasks, detailed_comparisons=detailed_comparisons, internet_results=internet_results, ai_report=ai_report)

# 🏫 COURSE MANAGEMENT ROUTES
def generate_invite_code(length=6): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.route('/create_course', methods=['POST'])
@login_required
def create_course():
    if current_user.role != 'teacher': return redirect(url_for('index'))
    course_name = request.form.get('course_name')
    code = generate_invite_code()
    conn = get_db_connection()
    conn.execute('INSERT INTO courses (name, code, teacher_id) VALUES (?, ?, ?)', (course_name, code, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('teacher_portal'))

@app.route('/create_task', methods=['POST'])
@login_required
def create_task():
    if current_user.role != 'teacher': return redirect(url_for('index'))
    course_id = request.form.get('course_id')
    title = request.form.get('title')
    deadline = request.form.get('deadline')
    total_marks = request.form.get('total_marks', 100) 
    conn = get_db_connection()
    conn.execute('INSERT INTO tasks (course_id, title, deadline, total_marks) VALUES (?, ?, ?, ?)', (course_id, title, deadline, total_marks))
    conn.commit()
    conn.close()
    return redirect(url_for('teacher_portal'))

@app.route('/delete_task/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    if current_user.role != 'teacher': return redirect(url_for('index'))
    
    conn = get_db_connection()
    task = conn.execute('''
        SELECT t.id FROM tasks t
        JOIN courses c ON t.course_id = c.id
        WHERE t.id = ? AND c.teacher_id = ?
    ''', (task_id, current_user.id)).fetchone()
    
    if task:
        submissions = conn.execute('SELECT filename FROM assignments WHERE task_id = ?', (task_id,)).fetchall()
        for sub in submissions:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], sub['filename'])
            if os.path.exists(file_path): 
                os.remove(file_path)
        
        conn.execute('DELETE FROM assignments WHERE task_id = ?', (task_id,))
        conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        
    conn.close()
    return redirect(url_for('teacher_portal'))

@app.route('/join_course', methods=['POST'])
@login_required
def join_course():
    if current_user.role != 'student': return redirect(url_for('index'))
    code = request.form.get('invite_code').strip().upper()
    conn = get_db_connection()
    course = conn.execute('SELECT id FROM courses WHERE code = ?', (code,)).fetchone()
    if course:
        try:
            conn.execute('INSERT INTO enrollments (student_id, course_id) VALUES (?, ?)', (current_user.id, course['id']))
            conn.commit()
        except:
            pass # Already enrolled
    conn.close()
    return redirect(url_for('student_portal'))

if __name__ == '__main__':
    print("🚀 Server running...")
    app.run(debug=True)