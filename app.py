from flask import Flask, render_template, request, session, redirect, url_for
import mysql.connector
import subprocess
import base64
import numpy as np
import cv2
import face_recognition
import json
import sys
from datetime import date

app = Flask(__name__)
app.secret_key = "super_secure_campus_key_123"

# IMPORTANT: Replace with your actual MySQL root password
db_password = "*********"

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password=db_password,
            database="*************"
        )
        return connection
    except Exception as e:
        return None

# Route 1: The main entry point - send directly to Login
@app.route('/')
def index():
    return redirect(url_for('login'))

# Route 2: Register a New Student (Text Data Only)
# Route: Register a New Student (Text Data + Manual Photos)
@app.route('/register', methods=['GET', 'POST'])
def register():
    # --- SECURITY LOCK ---
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Grab all the text data typed into the form
        regno = request.form.get('regno')
        name = request.form.get('name')
        department = request.form.get('department')
        gender = request.form.get('gender')
        email = request.form.get('email')
        guardian = request.form.get('guardian')
        
        encodings = []
        
        # Grab the 5 photos, decode them, and extract facial measurements
        for i in range(1, 6):
            image_data = request.form.get(f'image{i}')
            if image_data:
                try:
                    # Strip the HTML prefix to get the raw image code
                    encoded_data = image_data.split(',')[1]
                    nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    faces = face_recognition.face_encodings(rgb_img)
                    
                   # If the AI actually sees a face, save the mathematical encoding
                    if len(faces) > 0:
                        encodings.append(faces[0].tolist())
                except Exception as e:
                    print(f"Image Processing Error: {e}")

        # Security Check: Did we get a clear face in the photos?
        if len(encodings) == 0:
            return "Error: No clear face detected in the photos. Please go back and try again."
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Securely insert the text data AND the face encodings into MySQL
            cursor.execute(
                "INSERT INTO students (regno, name, department, gender, email, guardian_name, face_encodings) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
                (regno, name, department, gender, email, guardian, json.dumps(encodings))
            )
            conn.commit()
            
            cursor.close()
            conn.close()
            
            # Success! Redirect back to the management table
            return redirect(url_for('manage'))
            
        except Exception as e:
            return f"Database Error: {e}"
            
    # If they just clicked the button, show them the blank form and camera
    return render_template('register.html')
# Route 3: The Live Attendance Dashboard
@app.route('/dashboard')
def dashboard():
    # --- THE NEW SECURITY LOCK ---
    # If the admin is NOT logged in, instantly send them back to the login page
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    # -----------------------------

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get today's date to filter the database
        today = date.today().strftime("%Y-%m-%d")
        
        # Fetch all records for today
        cursor.execute("SELECT regno, name, time, status FROM attendance_logs WHERE date = %s ORDER BY time DESC", (today,))
        logs = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Send the data to a new HTML page
        return render_template('dashboard.html', logs=logs, today_date=today)
    except Exception as e:
        return f"Database Error: {e}"
    
# Route 4: The Admin Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if the username and password match our database
            cursor.execute("SELECT * FROM admins WHERE username = %s AND password = %s", (username, password))
            admin = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if admin:
                # Grant the VIP pass
                session['admin_logged_in'] = True
                # Send them securely to the dashboard
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error_message="Invalid username or password.")
                
        except Exception as e:
            return render_template('login.html', error_message=f"Database Error: {e}")
            
    # If they just navigated to the page, show them the login form
    return render_template('login.html')

# Route 5: Logout to destroy the session
@app.route('/logout')
def logout():
    # This securely shreds the VIP pass
    session.pop('admin_logged_in', None)
    return redirect(url_for('login'))
# Route 6: The Manage Students Page (Host Portal)
@app.route('/manage')
def manage():
    # --- SECURITY LOCK ---
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Fetch all registered students from the database
        cursor.execute("SELECT regno, name, department, gender, email, guardian_name FROM students")
        students = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('manage.html', students=students)
    
    except Exception as e:
        return f"Database Error: {e}"
# Route 7: Delete a student record
@app.route('/delete/<regno>')
def delete_student(regno):
    # --- SECURITY LOCK ---
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Permanently erase the student using their unique registration number
        cursor.execute("DELETE FROM students WHERE regno = %s", (regno,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # Send them right back to the management table
        return redirect(url_for('manage'))
    
    except Exception as e:
        return f"Database Error: {e}"
    
# Route: Edit an existing student's details and/or update their face photos
@app.route('/edit/<regno>', methods=['GET', 'POST'])
def edit_student(regno):
    # --- SECURITY LOCK ---
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        department = request.form.get('department')
        gender = request.form.get('gender')
        email = request.form.get('email')
        guardian = request.form.get('guardian')
        
        # Check if the admin decided to take new photos
        encodings = []
        has_new_photos = False
        
        for i in range(1, 6):
            image_data = request.form.get(f'image{i}')
            if image_data:
                has_new_photos = True
                try:
                    encoded_data = image_data.split(',')[1]
                    nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    faces = face_recognition.face_encodings(rgb_img)
                    
                    if len(faces) > 0:
                        encodings.append(faces[0].tolist())
                except Exception as e:
                    print(f"Error processing image {i}: {e}")
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if has_new_photos:
                # Security Check for the new photos
                if len(encodings) == 0:
                    return "Error: No clear face detected in the new photos. Please go back and try again."
                
                # Update BOTH text details and the face encodings
                cursor.execute(
                    "UPDATE students SET name = %s, department = %s, gender = %s, email = %s, guardian_name = %s, face_encodings = %s WHERE regno = %s", 
                    (name, department, gender, email, guardian, json.dumps(encodings), regno)
                )
            else:
                # Update ONLY the text details (leave the old faces untouched)
                cursor.execute(
                    "UPDATE students SET name = %s, department = %s, gender = %s, email = %s, guardian_name = %s WHERE regno = %s", 
                    (name, department, gender, email, guardian, regno)
                )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return redirect(url_for('manage'))
            
        except Exception as e:
            return f"Database Error: {e}"
            
    # GET: Fetch the student's current details to pre-fill the form
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT regno, name, department, gender, email, guardian_name FROM students WHERE regno = %s", (regno,))
        student = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if student:
            return render_template('edit.html', student=student)
        else:
            return "Student not found.", 404
            
    except Exception as e:
        return f"Database Error: {e}"
    
# Route: Trigger the live face scanner
@app.route('/start_scanner')
def start_scanner():
    # --- SECURITY LOCK ---
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    
    try:
        # Use sys.executable to force it to use the virtual environment
        subprocess.run([sys.executable, 'scanner.py'])
        
        # Once the 15-second scanner finishes and closes, refresh the dashboard
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        return f"Error running scanner: {e}"

# THESE TWO LINES MUST BE AT THE VERY BOTTOM OF THE FILE
if __name__ == '__main__':
    app.run(debug=True)
