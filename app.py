from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client
import re  # For phone number validation
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Your XAMPP MySQL password
app.config['MYSQL_DB'] = 'user_auth'

mysql = MySQL(app)

# Twilio Configuration

TWILIO_AUTH_TOKEN = '884a2957672ae60820ad62d3091ff5df'
TWILIO_PHONE_NUMBER = '+18124974316'

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# SocketIO Initialization
socketio = SocketIO(app)

# Helper function to execute database queries
def execute_query(query, params=None, fetch=False):
    cur = mysql.connection.cursor()
    try:
        cur.execute(query, params)
        if fetch:
            result = cur.fetchall()
        else:
            mysql.connection.commit()
            result = None
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        result = None
    finally:
        cur.close()
    return result

# Helper function to validate phone numbers
def validate_phone_number(phone_number):
    return re.match(r'^\+?[1-9]\d{1,14}$', phone_number) is not None

# Home Route
@app.route('/')
def home():
    return render_template('home.html')

# Login Page
@app.route('/index')
def index():
    return render_template('index.html')

# Signup Route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']
        hashed_password = generate_password_hash(password)

        query = "INSERT INTO users (name, email, password, user_type) VALUES (%s, %s, %s, %s)"
        params = (name, email, hashed_password, user_type)
        execute_query(query, params)
        flash("Signup successful! Please log in.", "success")
        return redirect(url_for('index'))
    return render_template('signup.html')

# Login Route
@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    user_type = request.form['user_type']

    query = "SELECT id, name, password, user_type FROM users WHERE email = %s AND user_type = %s"
    params = (email, user_type)
    user = execute_query(query, params, fetch=True)

    if user and check_password_hash(user[0][2], password):
        session['user_id'] = user[0][0]
        session['user_name'] = user[0][1]
        session['user_type'] = user[0][3]
        session['user_email'] = email  # Store the email in the session

        if user[0][3] == "Worker":
            return redirect(url_for('worker_dashboard'))
        
        elif user[0][3] == "Parent":
            query = "SELECT status FROM parent_requests WHERE email = %s"
            params = (email,)
            result = execute_query(query, params, fetch=True)

            if result and result[0][0] == 'approved':
                return redirect(url_for('dashboard'))  # Redirect to the dashboard if approved
            else:
                return render_template('parantsDet.html')
                
        else:
            return redirect(url_for('waiting'))
    else:
        flash('Invalid email, password, or user type.', "danger")
        return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))  # Redirect to home page if not logged in
    
    user_id = session['user_id']
    user_name = session['user_name']
    user_type = session['user_type']
    email = session['user_email']  # Retrieve the email from the session

    if user_type == "Parent":
        query = "SELECT status FROM parent_requests WHERE email = %s"
        params = (email,)
        result = execute_query(query, params, fetch=True)

        if result and result[0][0] == 'approved':
            return render_template('dashboard.html', user_name=user_name)
        else:
            return render_template('waiting.html', message="Your request is still under review.")
    
    elif user_type == "Worker":
        return render_template('worker_dashboard.html', user_name=user_name)

    return redirect(url_for('index'))

@app.route('/parent/details', methods=['GET', 'POST'])
def parent_details():
    if 'user_id' not in session or session.get('user_type') != "Parent":
        flash("Unauthorized access!", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        student_name = request.form['student_name']
        blood_group = request.form['blood_group']
        relation = request.form['relation']
        parent_name = request.form['parent_name']
        parent_mobile = request.form['parent_mobile']
        secondary_mobile = request.form.get('secondary_mobile', '')
        email = session.get('user_email')

        if not validate_phone_number(parent_mobile):
            flash("Invalid parent mobile number. Please enter a valid phone number.", "danger")
            return render_template('parantsDet.html')

        query = """
            INSERT INTO parent_requests (email, student_name, blood_group, relation, parent_name, parent_mobile, secondary_mobile, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
        """
        params = (email, student_name, blood_group, relation, parent_name, parent_mobile, secondary_mobile)
        execute_query(query, params)
        flash("Details submitted successfully! Waiting for admin approval.", "success")
        return redirect(url_for('waiting_page'))

    return render_template('parantsDet.html')

@app.route('/waiting')
def waiting_page():
    if 'user_id' not in session or session.get('user_type') != "Parent":
        flash("Unauthorized access!", "danger")
        return redirect(url_for('index'))
    return render_template('waiting.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('admin_login'))

    query = "SELECT * FROM parent_requests WHERE status = 'pending'"
    pending_requests = execute_query(query, fetch=True)
    return render_template('admindashboard.html', requests=pending_requests)

@app.route('/admin/parent-requests')
def admin_parent_requests():
    if 'admin_id' not in session:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('admin_login'))

    query = "SELECT id, email, student_name, blood_group, relation, parent_name, parent_mobile, secondary_mobile, status FROM parent_requests WHERE status = 'pending'"
    rows = execute_query(query, fetch=True)

    requests = []
    for row in rows:
        requests.append({
            "id": row[0],
            "email": row[1],
            "student_name": row[2],
            "blood_group": row[3],
            "relation": row[4],
            "parent_name": row[5],
            "parent_mobile": row[6],
            "secondary_mobile": row[7],
            "status": row[8]
        })

    return render_template('admin_parent_requests.html', requests=requests)

@app.route('/admin/approve/<int:parent_id>', methods=['POST'])
def approve_parent(parent_id):
    if 'admin_id' not in session:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('admin_login'))

    query = "UPDATE parent_requests SET status = 'approved' WHERE id = %s"
    execute_query(query, (parent_id,))

    query = "SELECT email, parent_name, parent_mobile FROM parent_requests WHERE id = %s"
    parent = execute_query(query, (parent_id,), fetch=True)

    if parent:
        parent_email = parent[0][0]
        parent_name = parent[0][1]
        parent_mobile = parent[0][2]

        if not validate_phone_number(parent_mobile):
            flash(f"Invalid parent mobile number: {parent_mobile}. SMS not sent.", "danger")
        else:
            try:
                message = client.messages.create(
                    body=f"Hi {parent_name}, your request has been approved! You now have access to the dashboard.",
                    from_=TWILIO_PHONE_NUMBER,
                    to=parent_mobile
                )
                flash("SMS notification sent successfully.", "success")
            except Exception as e:
                flash(f"Failed to send SMS: {str(e)}", "danger")

        query = "SELECT id, name, email FROM users WHERE email = %s"
        user = execute_query(query, (parent_email,), fetch=True)

        if user:
            session['user_id'] = user[0][0]
            session['user_name'] = user[0][1]
            session['user_email'] = user[0][2]
            session['user_type'] = 'Parent'

            flash("Request approved. Parent logged in and redirected to dashboard.", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Parent not found in users database.", "danger")
            return redirect(url_for('admin_dashboard'))
    else:
        flash("Parent not found.", "danger")
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:parent_id>', methods=['POST'])
def reject_parent(parent_id):
    if 'admin_id' not in session:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('admin_login'))

    query = "UPDATE parent_requests SET status = 'rejected' WHERE id = %s"
    execute_query(query, (parent_id,))
    flash("Request rejected.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    default_username = 'admin'
    default_password = 'admin123'

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == default_username and password == default_password:
            session['admin_id'] = 1
            flash("Admin logged in successfully.", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid username or password.", "danger")
            return redirect(url_for('admin_login'))
    return render_template('adminlogin.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('index'))

@app.route('/track_location', methods=['POST'])
def track_location():
    user_id = session.get('user_id')
    if not user_id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for('index'))

    latitude = request.json.get('latitude')
    longitude = request.json.get('longitude')

    # Insert location data into user_locations table
    query = "INSERT INTO user_locations (user_id, latitude, longitude) VALUES (%s, %s, %s)"
    execute_query(query, (user_id, latitude, longitude))

    emit('location_update', {'latitude': latitude, 'longitude': longitude}, broadcast=True)

    return {'status': 'success'}

if __name__ == '__main__':
    socketio.run(app, debug=True)
