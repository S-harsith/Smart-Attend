import cv2
import face_recognition
import mysql.connector
import numpy as np
import json
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURATION ---
# IMPORTANT: Replace with your actual MySQL root password
db_password = "**************"

# IMPORTANT: Email Credentials
SENDER_EMAIL = "**************"
SENDER_PASSWORD = "************"

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password=db_password,
        database="*************"
    )

def send_absent_email(student_name, guardian_email, date_str):
    """Sends an automated email to the guardian."""
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = guardian_email
        msg['Subject'] = f"Attendance Alert: {student_name} is Absent"

        body = f"Dear Guardian,\n\nThis is an automated alert from the Campus Attendance System. {student_name} was marked ABSENT for their session on {date_str}.\n\nPlease ensure everything is okay.\n\nThank you."
        msg.attach(MIMEText(body, 'plain'))

        # Connect to Gmail's server and send
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Email Error: {e}")

# 1. Load the "Brain" - Fetch all registered faces and emails from MySQL
known_face_encodings = []
known_face_names = []
known_face_regnos = []
student_contact_info = {} # Store emails to use later if absent

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    # We now fetch the email as well!
    cursor.execute("SELECT regno, name, email, face_encodings FROM students")
    
    for (regno, name, email, encodings_json) in cursor.fetchall():
        student_contact_info[regno] = {'name': name, 'email': email}
        encodings_list = json.loads(encodings_json)
        
        for enc in encodings_list:
            known_face_encodings.append(np.array(enc))
            known_face_names.append(name)
            known_face_regnos.append(regno)
            
    cursor.close()
    conn.close()
except Exception as e:
    exit()

already_marked_this_session = set()
now = datetime.now()
current_date = now.strftime("%Y-%m-%d")

def log_attendance(regno, name, status="Present"):
    """Saves the student to the ledger."""
    if regno in already_marked_this_session and status == "Present":
        return 

    current_time = datetime.now().strftime("%H:%M:%S")
    
    try:
        db = get_db_connection()
        cursor = db.cursor()
        sql = "INSERT INTO attendance_logs (regno, name, date, time, status) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(sql, (regno, name, current_date, current_time, status))
        db.commit()
        print(f"SUCCESS: {name} ({regno}) marked {status} at {current_time}")
        if status == "Present":
            already_marked_this_session.add(regno)
    except mysql.connector.IntegrityError:
        if status == "Present":
            already_marked_this_session.add(regno) 
    except Exception as e:
        print(f"Database Error: {e}")
    finally:
        if db.is_connected():
            cursor.close()
            db.close()

# 2. Open the "Eyes" and start the 15-second timer
video_capture = cv2.VideoCapture(0)
start_time = time.time()

while True:
    # Check if 15 seconds have passed
    if time.time() - start_time > 15:
        break

    ret, frame = video_capture.read()
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
    
    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.5)
        name = "Unknown"
        regno = "Unknown"

        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
        if len(face_distances) > 0:
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = known_face_names[best_match_index]
                regno = known_face_regnos[best_match_index]
                
                log_attendance(regno, name, status="Present")

        top *= 4
        right *= 4
        bottom *= 4
        left *= 4

        color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
        cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)

    # Calculate remaining time and display it on the camera feed
    time_left = int(15 - (time.time() - start_time))
    cv2.putText(frame, f"Time left: {time_left}s", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    
    cv2.imshow('Campus Live Attendance Scanner', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

video_capture.release()
cv2.destroyAllWindows()

# 3. The Absentee Processing Phase

for regno, info in student_contact_info.items():
    if regno not in already_marked_this_session:
        name = info['name']
        email = info['email']
        
        # Log them as absent in MySQL
        log_attendance(regno, name, status="Absent")
        
        # Send the automatic email
        send_absent_email(name, email, current_date)
