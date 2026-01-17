from flask import Blueprint, request, jsonify, session, render_template, url_for,flash, request, session, redirect, abort
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User, RoleEnum, Department
from app.utils.db import db 
from flask_login import login_user, logout_user, login_required, current_user
from app import bcrypt 
from functools import wraps
import re
from app.utils.notification import send_welcome_and_password_notification_async,  run_async_in_background
from app.services.users.user_service import get_user_by_email

# A basic regex for email validation
EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

auth_bp = Blueprint('auth', __name__)

def role_required(allowed_roles):
    """Generic role-based decorator"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)  # Unauthorized
            if current_user.role not in allowed_roles:
                abort(403)  # Forbidden
            return func(*args, **kwargs)
        return wrapper
    return decorator

# === Named Role-Based Decorators ===

def directors_only(func):
    return role_required(['DIRECTOR'])(func)

def directors_and_admins(func):
    return role_required(['DIRECTOR', 'ADMIN'])(func)

def supervisors_admins_directors(func):
    return role_required([
        'DIRECTOR',
        'ADMIN',
        'SUPERVISOR'
    ])(func)

def all_except_interns(func):
    return role_required([
        'DIRECTOR',
        'ADMIN',
        'SUPERVISOR',
       'OFFICER'
    ])(func)

@auth_bp.route("/register", methods=['GET', 'POST'])
@login_required
@directors_and_admins
def register():
    
    # We define these outside the POST block so they are always available
    departments = Department.query.all()
    roles = RoleEnum
    
    if request.method == 'POST':
        # --- 1. Get Data ---
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password') # <-- FIX #2
        role = request.form.get('role')
        department_id = request.form.get('department_id')
        phone_number = request.form.get('phone_number')

        # --- 2. Validation & Sanitization ---
        
        # FIX #3: Added confirm_password
        if not all([first_name, last_name, email, password, confirm_password, role, department_id, phone_number]):
            flash('Please fill out all required fields.', 'danger')
            return render_template('register.html', departments=departments, roles=roles)

        email = email.lower() 

        email_exists = User.query.filter_by(email=email).first()
        if email_exists:
            flash('Email address is already registered.', 'danger')
            return render_template('register.html', departments=departments, roles=roles)

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('register.html', departments=departments, roles=roles)
        
        # FIX #2: Added password match check
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html', departments=departments, roles=roles)
            
        # FIX #1: This will now work (assuming re and EMAIL_REGEX are imported/defined)
        if not re.match(EMAIL_REGEX, email):
            flash('Invalid email address format.', 'danger')
            return render_template('register.html', departments=departments, roles=roles)
        
        # --- 3. Process Data ---
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        try:
            new_user = User(
                first_name=first_name, middle_name=middle_name, last_name=last_name,
                email=email, password_hash=hashed_password, role=RoleEnum[role].value.upper(),
                department_id=department_id, phone_number=phone_number
            )
            db.session.add(new_user)
            db.session.commit()
            
            # FIXED: Use run_async_in_background instead of .delay
            from app.utils.notification import run_async_in_background, send_welcome_and_password_notification_async
            run_async_in_background(send_welcome_and_password_notification_async, new_user.id, password)
            
            flash('User account created successfully.', 'success')
            return redirect(url_for('main.dashboard'))
        except KeyError:
            flash('Invalid role selected.', 'danger')

    # This is the GET request handler
    return render_template('register.html', departments=departments, roles=roles)


@auth_bp.route("/login", methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        # Use .get() to avoid errors if fields are missing
        email = request.form.get('email')
        password = request.form.get('password')

        # --- 1. Validation ---
        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('login.html')

        # --- 2. Sanitization (CRITICAL) ---
        email = email.lower() 

        # --- 3. More Validation ---
        if not re.match(EMAIL_REGEX, email):
            flash('Invalid email address format.', 'danger')
            return render_template('login.html')
            
        # --- 4. Authentication ---
        user = get_user_by_email(email)

        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            flash(f'Login successful for {user.first_name}!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
            
    return render_template('login.html')


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    logout_user()   # This logs out the current user properly
    return redirect(url_for('main.home'))

@auth_bp.route("/interviwee/apply", methods=['GET', 'POST'])
def register_for_interviewe():

    if request.method == 'POST':
        
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        department_id = request.form.get('department_id')
        phone_number = request.form.get('phone_number')

        if not all([first_name, middle_name, last_name, email, password, confirm_password, phone_number]):
            flash('Please fill out all required fields.', 'danger')
            return render_template('/interviewee/register.html')

        email = email.lower()

        if User.query.filter_by(email=email).first():
            flash('Email address is already registered.', 'danger')
            return render_template('/interviewee/register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('/interviewee/register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('/interviewee/register.html')

        if not re.match(EMAIL_REGEX, email):
            flash('Invalid email address format.', 'danger')
            return render_template('/interviewee/register.html')

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        try:
            new_user = User(
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                email=email,
                password_hash=hashed_password,
                role='APPLICANT',
                phone_number=phone_number
            )

            db.session.add(new_user)
            db.session.commit()
            
            flash('User account created successfully.', 'success')
            return redirect(url_for('/interviewee/register.html'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account: {str(e)}', 'danger')

    return render_template('/interviewee/register.html')

