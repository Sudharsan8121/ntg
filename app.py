from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re
import os
import hashlib
from werkzeug.utils import secure_filename
from datetime import datetime
import PyPDF2
import docx
from pptx import Presentation
from PIL import Image
from fpdf import FPDF
import os
import pythoncom
import comtypes.client

def convert_pptx_with_powerpoint(input_path, output_path):

    pythoncom.CoInitialize()
    
    # Convert to absolute path
    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)

    # Log paths for debugging
    print("📂 Input Path:", input_path)
    print("📄 Output Path:", output_path)

    # Ensure the input file exists
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input PPTX file not found: {input_path}")

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    powerpoint = comtypes.client.CreateObject("Powerpoint.Application")
    powerpoint.Visible = 1

    try:
        presentation = powerpoint.Presentations.Open(input_path, WithWindow=False)
        presentation.SaveAs(output_path, 32)  # 32 = PDF
        presentation.Close()
        
    finally:
        powerpoint.Quit()
        pythoncom.CoUninitialize()
def convert_word_with_office(input_path, output_path):
    pythoncom.CoInitialize()  # Ensure COM is initialized in Flask context

    word = comtypes.client.CreateObject('Word.Application')
    word.Visible = False

    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)

    try:
        doc = word.Documents.Open(input_path)
        doc.SaveAs(output_path, FileFormat=17)  # 17 = PDF
        doc.Close()
    finally:
        word.Quit()
        pythoncom.CoUninitialize()
import pytesseract
from gtts import gTTS
import io
import tempfile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# Secret key for session management
app.secret_key = 'your-secret-key-here'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '8055'
app.config['MYSQL_DB'] = 'converter_db'

mysql = MySQL(app)

# Upload folder configuration
UPLOAD_FOLDER = 'uploads'
CONVERTED_FOLDER = 'converted'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'ppt', 'pptx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CONVERTED_FOLDER'] = CONVERTED_FOLDER

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/')
def home():
    return render_template('index.html')
# Route to view all users
@app.route('/admin/users')
def view_users():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, name, email, created_at FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    cur.close()
    return render_template('admin_users.html', users=users)

# Route to view user activity
@app.route('/admin/user-activity')
def user_activity():
    cur = mysql.connection.cursor()
    query = """
        SELECT u.name, u.email, 'PDF to Text' AS module, p.filename, p.created_at
        FROM users u JOIN pdf_to_text p ON u.id = p.user_id
        UNION
        SELECT u.name, u.email, 'PDF to MP3', p.filename, p.created_at
        FROM users u JOIN pdf_to_mp3 p ON u.id = p.user_id
        UNION
        SELECT u.name, u.email, 'Word to PDF', p.filename, p.created_at
        FROM users u JOIN word_to_pdf p ON u.id = p.user_id
        UNION
        SELECT u.name, u.email, 'Image to Text', p.filename, p.created_at
        FROM users u JOIN image_to_text p ON u.id = p.user_id
        UNION
        SELECT u.name, u.email, 'Image to PDF', p.filename, p.created_at
        FROM users u JOIN image_to_pdf p ON u.id = p.user_id
        UNION
        SELECT u.name, u.email, 'PPT to PDF', p.filename, p.created_at
        FROM users u JOIN ppt_to_pdf p ON u.id = p.user_id
        ORDER BY created_at DESC
    """
    cur.execute(query)
    logs = cur.fetchall()
    cur.close()
    return render_template('admin_user_activity.html', logs=logs)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('register.html')
        
        # Check if email already exists
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account:
            flash('Email already exists!', 'error')
        else:
            hashed_password = hash_password(password)
            cursor.execute('INSERT INTO users (name, email, password, created_at) VALUES (%s, %s, %s, %s)', 
                         (name, email, hashed_password, datetime.now()))
            mysql.connection.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        
        cursor.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hash_password(password)
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s AND password = %s', (email, hashed_password))
        account = cursor.fetchone()
        cursor.close()
        
        if account:
            session['loggedin'] = True
            session['id'] = account['id']
            session['name'] = account['name']
            session['email'] = account['email']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('name', None)
    session.pop('email', None)
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'loggedin' in session:
        return render_template('dashboard.html', name=session['name'])
    return redirect(url_for('login'))

@app.route('/pdf-to-text', methods=['GET', 'POST'])
def pdf_to_text():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected!', 'error')
            return redirect(request.url)
        
        if file and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Extract text from PDF
            text = ""
            try:
                with open(filepath, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                
                # Save to database
                cursor = mysql.connection.cursor()
                cursor.execute('INSERT INTO pdf_to_text (user_id, filename, extracted_text, created_at) VALUES (%s, %s, %s, %s)',
                             (session['id'], filename, text, datetime.now()))
                mysql.connection.commit()
                cursor.close()
                
                # Clean up uploaded file
                os.remove(filepath)
                
                return render_template('pdf_to_text.html', text=text, success=True)
            
            except Exception as e:
                flash(f'Error processing PDF: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Please upload a valid PDF file!', 'error')
    
    return render_template('pdf_to_text.html')

@app.route('/pdf-to-mp3', methods=['GET', 'POST'])
def pdf_to_mp3():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # Extract text from PDF
                text = ""
                with open(filepath, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                
                # Convert text to speech
                tts = gTTS(text=text, lang='en')
                mp3_filename = f"{filename.rsplit('.', 1)[0]}.mp3"
                mp3_filepath = os.path.join(app.config['CONVERTED_FOLDER'], mp3_filename)
                tts.save(mp3_filepath)
                
                # Save to database
                cursor = mysql.connection.cursor()
                cursor.execute('INSERT INTO pdf_to_mp3 (user_id, filename, mp3_filename, created_at) VALUES (%s, %s, %s, %s)',
                             (session['id'], filename, mp3_filename, datetime.now()))
                mysql.connection.commit()
                cursor.close()
                
                # Clean up uploaded file
                os.remove(filepath)
                
                return send_file(mp3_filepath, as_attachment=True)
            
            except Exception as e:
                flash(f'Error processing PDF: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Please upload a valid PDF file!', 'error')
    
    return render_template('pdf_to_mp3.html')

@app.route('/word-to-pdf', methods=['GET', 'POST'])
def word_to_pdf():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'error')
            return redirect(request.url)

        file = request.files['file']
        if file and (file.filename.lower().endswith('.docx') or file.filename.lower().endswith('.doc')):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                # Convert Word to PDF using Office Automation
                pdf_filename = f"{filename.rsplit('.', 1)[0]}.pdf"
                pdf_filepath = os.path.join(app.config['CONVERTED_FOLDER'], pdf_filename)

                convert_word_with_office(filepath, pdf_filepath)

                # Save to database
                cursor = mysql.connection.cursor()
                cursor.execute(
                    'INSERT INTO word_to_pdf (user_id, filename, pdf_filename, created_at) VALUES (%s, %s, %s, %s)',
                    (session['id'], filename, pdf_filename, datetime.now())
                )
                mysql.connection.commit()
                cursor.close()

                # Clean up uploaded file
                os.remove(filepath)

                return send_file(pdf_filepath, as_attachment=True)

            except Exception as e:
                flash(f'Error processing Word document: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Please upload a valid Word document!', 'error')

    return render_template('word_to_pdf.html')


@app.route('/image-to-text', methods=['GET', 'POST'])
def image_to_text():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file and file.filename.lower().split('.')[-1] in ['jpg', 'jpeg', 'png', 'gif']:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # Extract text from image using OCR
                image = Image.open(filepath)
                text = pytesseract.image_to_string(image)
                
                # Save to database
                cursor = mysql.connection.cursor()
                cursor.execute('INSERT INTO image_to_text (user_id, filename, extracted_text, created_at) VALUES (%s, %s, %s, %s)',
                             (session['id'], filename, text, datetime.now()))
                mysql.connection.commit()
                cursor.close()
                
                # Clean up uploaded file
                os.remove(filepath)
                
                return render_template('image_to_text.html', text=text, success=True)
            
            except Exception as e:
                flash(f'Error processing image: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Please upload a valid image file!', 'error')
    
    return render_template('image_to_text.html')

@app.route('/image-to-pdf', methods=['GET', 'POST'])
def image_to_pdf():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected!', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file and file.filename.lower().split('.')[-1] in ['jpg', 'jpeg', 'png', 'gif']:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # Convert image to PDF
                image = Image.open(filepath)
                pdf_filename = f"{filename.rsplit('.', 1)[0]}.pdf"
                pdf_filepath = os.path.join(app.config['CONVERTED_FOLDER'], pdf_filename)
                
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                image.save(pdf_filepath, 'PDF')
                
                # Save to database
                cursor = mysql.connection.cursor()
                cursor.execute('INSERT INTO image_to_pdf (user_id, filename, pdf_filename, created_at) VALUES (%s, %s, %s, %s)',
                             (session['id'], filename, pdf_filename, datetime.now()))
                mysql.connection.commit()
                cursor.close()
                
                # Clean up uploaded file
                os.remove(filepath)
                
                return send_file(pdf_filepath, as_attachment=True)
            
            except Exception as e:
                flash(f'Error processing image: {str(e)}', 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Please upload a valid image file!', 'error')
    
    return render_template('image_to_pdf.html')
@app.route('/ppt-to-pdf', methods=['GET', 'POST'])
def ppt_to_pdf():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected!', 'error')
            return redirect(request.url)

        if not file.filename.lower().endswith(('.ppt', '.pptx')):
            flash('Please upload a valid PowerPoint file (PPT/PPTX)!', 'error')
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Convert PPTX to PDF using real PowerPoint
            pdf_filename = f"{os.path.splitext(filename)[0]}.pdf"
            pdf_filepath = os.path.join(app.config['CONVERTED_FOLDER'], pdf_filename)

            convert_pptx_with_powerpoint(filepath, pdf_filepath)

            # Save to DB
            cursor = mysql.connection.cursor()
            cursor.execute(
                'INSERT INTO ppt_to_pdf (user_id, filename, pdf_filename, created_at) VALUES (%s, %s, %s, %s)',
                (session['id'], filename, pdf_filename, datetime.now())
            )
            mysql.connection.commit()
            cursor.close()

            # Clean up original upload
            os.remove(filepath)

            return send_file(pdf_filepath, as_attachment=True)

        except Exception as e:
            flash(f'Error processing PowerPoint: {str(e)}', 'error')
            if os.path.exists(filepath):
                os.remove(filepath)

    return render_template('ppt_to_pdf.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        subject = request.form['subject']
        message = request.form['message']
        
        # Save to database
        cursor = mysql.connection.cursor()
        cursor.execute('INSERT INTO contact_messages (name, email, subject, message, created_at) VALUES (%s, %s, %s, %s, %s)',
                     (name, email, subject, message, datetime.now()))
        mysql.connection.commit()
        cursor.close()
        
        flash('Message sent successfully! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

@app.route('/history')
def history():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get conversion history for the user
    conversions = []
    
    # PDF to Text
    cursor.execute('SELECT "PDF to Text" as type, filename, created_at FROM pdf_to_text WHERE user_id = %s', (session['id'],))
    conversions.extend(cursor.fetchall())
    
    # PDF to MP3
    cursor.execute('SELECT "PDF to MP3" as type, filename, created_at FROM pdf_to_mp3 WHERE user_id = %s', (session['id'],))
    conversions.extend(cursor.fetchall())
    
    # Word to PDF
    cursor.execute('SELECT "Word to PDF" as type, filename, created_at FROM word_to_pdf WHERE user_id = %s', (session['id'],))
    conversions.extend(cursor.fetchall())
    
    # Image to Text
    cursor.execute('SELECT "Image to Text" as type, filename, created_at FROM image_to_text WHERE user_id = %s', (session['id'],))
    conversions.extend(cursor.fetchall())
    
    # Image to PDF
    cursor.execute('SELECT "Image to PDF" as type, filename, created_at FROM image_to_pdf WHERE user_id = %s', (session['id'],))
    conversions.extend(cursor.fetchall())
    
    # PPT to PDF
    cursor.execute('SELECT "PPT to PDF" as type, filename, created_at FROM ppt_to_pdf WHERE user_id = %s', (session['id'],))
    conversions.extend(cursor.fetchall())
    
    cursor.close()
    
    # Sort by date
    conversions.sort(key=lambda x: x['created_at'], reverse=True)
    
    return render_template('history.html', conversions=conversions)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
<<<<<<< HEAD
    app.run(host='0.0.0.0', port=port)
=======
    app.run(host='0.0.0.0', port=port)
>>>>>>> bb67c62 (Fix Flask deployment config for Render)
