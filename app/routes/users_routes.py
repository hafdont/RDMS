from flask import Blueprint, request, jsonify, session, render_template, url_for,flash, request, session, redirect, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import *
from app.utils.db import db 
from flask_login import login_user, logout_user, login_required, current_user
from app import bcrypt 
from collections import Counter
from sqlalchemy import or_
import math
from sqlalchemy import func
from dateutil.relativedelta import relativedelta
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from PIL import Image
import os, secrets
from sqlalchemy.orm import joinedload, subqueryload
from .auth_routes import supervisors_admins_directors
from app.utils.notification import send_password_reset_email_async, run_async_in_background
from app.utils.storage_service import storage_service
from app.services.users.user_service import get_users_with_stats, group_users_by_department

users_bp = Blueprint('user', __name__)

PER_PAGE = 5

def save_picture(form_picture):
    """Saves uploaded profile picture to DigitalOcean Spaces, resizes it..."""
    
    # 1. Keep track of the original extension
    original_filename = form_picture.filename 

    # 2. Resize the image
    output_size = (150, 150)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    
    from io import BytesIO
    img_byte_arr = BytesIO()
    # Note: If you want to keep the original format (JPEG/PNG), 
    # you can use i.format instead of hardcoding 'PNG'
    i.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    try:
        # 3. Pass the filename explicitly here
        upload_result = storage_service.upload_file(
            img_byte_arr, 
            folder='profile_pictures',
            filename=original_filename # Pass this here!
        )
        return upload_result['key']
    
    except Exception as e:
        print(f"❌ Error uploading profile picture: {e}")
        raise

@users_bp.route("/users", methods=["GET"])
@login_required
@supervisors_admins_directors
def get_users():
    # Collect filters from query string
    filters = {
        "q": request.args.get("q"),
        "department_id": request.args.get("department_id", type=int),
        "role": request.args.get("role"),
        "client_id": request.args.get("client_id", type=int),
        "service_id": request.args.get("service_id", type=int),
    }

    # Fetch users with precomputed stats
    users_data = get_users_with_stats(filters)

    # Group users by department
    users_grouped = group_users_by_department(users_data)

    # Fetch departments, services, clients for filters
    departments = Department.query.all()
    services = Service.query.all()
    clients = Client.query.all()

    return render_template(
        "user/user_list.html",
        users_grouped=users_grouped,
        departments=departments,
        services=services,
        clients=clients,
        RoleEnum=RoleEnum,
    )

@users_bp.route("/user/<int:user_id>", methods=['GET'])
@login_required
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    image_file = url_for('static', filename='profile_pics/' + user.profile_image_file)

    assigned_tasks = user.assigned_tasks
    completed_tasks = [t for t in assigned_tasks if t.status.name == "COMPLETED"]
    rejected_tasks = [t for t in assigned_tasks if t.status.name == "REJECTED"]
    review_tasks = [t for t in assigned_tasks if t.status.name == "REVIEW"]

    total_minutes = sum(t.estimated_minutes or 0 for t in assigned_tasks)

    logs = TaskLog.query.filter_by(user_id=user.id).order_by(TaskLog.start_time.desc()).limit(5).all()
    approvals = TaskApproval.query.filter_by(approved_by_id=user.id).all()

    # Group tasks by client
    client_tasks = {}
    for task in assigned_tasks:
        if task.client_id:
            client_name = task.client.name if task.client else "Unknown Client"
            client_tasks.setdefault(client_name, []).append(task)

    return render_template(
        '/user/user_detail.html',
        user=user,
        assigned_tasks=assigned_tasks,
        completed_tasks=completed_tasks,
        rejected_tasks=rejected_tasks,
        review_tasks=review_tasks,
        total_minutes=total_minutes,
        logs=logs,
        approvals=approvals,
        image_file=image_file
    )

# --- Helper function to convert Enum to string ---
def get_enum_value(enum_or_string):
    """Safely gets the value of an Enum or returns the string itself."""
    if isinstance(enum_or_string, Enum):
        return enum_or_string.value
    return str(enum_or_string) # Ensure it's always a string

# --- User Profile Endpoint ---
@users_bp.route('/profile/<int:user_id>', methods=['GET', 'POST'])
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    image_file = url_for('static', filename='profile_pics/' + user.profile_image_file)

    allowed_roles = ['SUPERVISOR', 'DIRECTOR', 'ADMIN']

    # Check if user is not themselves and current_user does NOT have any allowed role
    if user.id != current_user.id and not any(current_user.has_role(role) for role in allowed_roles):
        flash("You do not have permission to view this profile.", "danger")
        return redirect(url_for('main.dashboard'))

    all_assigned_tasks = Task.query.filter_by(assigned_to_id=user.id).all()
    for task in all_assigned_tasks:
        task.display_status = get_enum_value(task.status)
        task.display_priority = get_enum_value(task.priority)

    all_in_progress_tasks = [t for t in all_assigned_tasks if t.status == TaskStatusEnum.IN_PROGRESS]
    not_started_tasks = [t for t in all_assigned_tasks if t.status == TaskStatusEnum.ASSIGNED]
    all_paused_tasks = [t for t in all_assigned_tasks if t.status == TaskStatusEnum.PAUSED]
    all_under_review_tasks = [t for t in all_assigned_tasks if t.status == TaskStatusEnum.REVIEW]
    all_completed_tasks = [t for t in all_assigned_tasks if t.status == TaskStatusEnum.COMPLETED]

    redo_task_ids = {
        approval.task_id for approval in TaskApproval.query
        .filter(TaskApproval.decision == DecisionEnum.REDO)
        .filter(TaskApproval.task.has(Task.assigned_to_id == user.id))
        .all()
    }

    redo_tasks = [task for task in all_assigned_tasks if task.id in redo_task_ids]

    all_created_tasks = Task.query.filter_by(created_by_id=user.id).all()
    for task in all_created_tasks:
        task.display_status = get_enum_value(task.status)
        task.display_priority = get_enum_value(task.priority)

    def get_paginated_list(full_list, page_param_name):
        page = request.args.get(page_param_name, 1, type=int)
        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        paginated_items = full_list[start:end]
        total_pages = math.ceil(len(full_list) / PER_PAGE)
        return paginated_items, page, total_pages, len(full_list)

    paginated_assigned_tasks, current_page_assigned, total_pages_assigned, total_assigned_count = get_paginated_list(all_assigned_tasks, 'page_assigned')
    paginated_in_progress_tasks, current_page_in_progress, total_pages_in_progress, total_in_progress_count = get_paginated_list(all_in_progress_tasks, 'page_in_progress')
    paginated_paused_tasks, current_page_paused, total_pages_paused, total_paused_count = get_paginated_list(all_paused_tasks, 'page_paused')
    paginated_under_review_tasks, current_page_under_review, total_pages_under_review, total_under_review_count = get_paginated_list(all_under_review_tasks, 'page_under_review')
    paginated_completed_tasks, current_page_completed, total_pages_completed, total_completed_count = get_paginated_list(all_completed_tasks, 'page_completed')
    paginated_created_tasks, current_page_created, total_pages_created, total_created_count = get_paginated_list(all_created_tasks, 'page_created')
    paginated_redo_tasks, current_page_redo, total_pages_redo, total_redo_count = get_paginated_list(redo_tasks, 'page_redo')
    paginated_not_started_tasks, current_page_not_started, total_pages_not_started, total_not_started_count = get_paginated_list(not_started_tasks, 'page_not_started')

    months = request.args.get('months', 6, type=int)
    service_id = request.args.get('service_id', None, type=int)
    start_date = datetime.utcnow() - relativedelta(months=months)

    filtered_task_logs = TaskLog.query.join(Task).filter(
        TaskLog.user_id == user.id,
        TaskLog.status == LogStatusEnum.COMPLETED,
        TaskLog.end_time.isnot(None),
        TaskLog.start_time >= start_date,
    )

    if service_id:
        filtered_task_logs = filtered_task_logs.filter(Task.task_template_id == TaskTemplate.id, TaskTemplate.service_id == service_id)

    filtered_task_logs = filtered_task_logs.all()

    # ✅ FIX: initialize before use
    graph_data = []
    graph_total_completion_seconds = 0
    graph_completed_task_count = 0

    for log in filtered_task_logs:
        active_duration = timedelta()

        if log.status == LogStatusEnum.COMPLETED and log.start_time and log.end_time:
            active_duration += (log.end_time - log.start_time)

        if active_duration.total_seconds() > 0:
            graph_total_completion_seconds += active_duration.total_seconds()
            graph_completed_task_count += 1

            duration_minutes = (log.end_time - log.start_time).total_seconds() / 60
            graph_data.append({
                'task_title': log.task.title,
                'end_time': log.end_time.strftime("%Y-%m-%d"),
                'duration_minutes': round(duration_minutes, 2)
            })

    # --- Average completion time calculation (separate logic) ---
    total_completion_seconds = 0
    completed_task_count = 0

    user_completed_task_logs = TaskLog.query.filter(
        TaskLog.user_id == user.id,
        TaskLog.status == LogStatusEnum.COMPLETED,
        TaskLog.end_time.isnot(None)
    ).all()

    for log in user_completed_task_logs:
        if log.start_time and log.end_time:
            duration = log.end_time - log.start_time
            total_completion_seconds += duration.total_seconds()
            completed_task_count += 1

    avg_completion_time = None
    if completed_task_count > 0:
        avg_completion_seconds = total_completion_seconds / completed_task_count
        hours, remainder = divmod(avg_completion_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        avg_completion_time = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

    clients_worked_for = {}
    for task in all_completed_tasks:
        if task.client:
            if task.client.name not in clients_worked_for:
                clients_worked_for[task.client.name] = []
            clients_worked_for[task.client.name].append(task)

    task_titles = [task.title for task in all_assigned_tasks]
    service_names = [
        task.template.service.name
        for task in all_assigned_tasks
        if task.template and task.template.service
    ]
    template_titles = [
        task.template.title
        for task in all_assigned_tasks
        if task.template
    ]

    most_frequent_tasks = Counter(task_titles).most_common(5)
    most_frequent_services = Counter(service_names).most_common(5)
    most_frequent_templates = Counter(template_titles).most_common(5)

    return render_template(
        '/user/user_detail.html',
        user=user,

        assigned_tasks=paginated_assigned_tasks,
        current_page_assigned=current_page_assigned,
        total_pages_assigned=total_pages_assigned,
        total_assigned_count=total_assigned_count,

        in_progress_tasks=paginated_in_progress_tasks,
        current_page_in_progress=current_page_in_progress,
        total_pages_in_progress=total_pages_in_progress,
        total_in_progress_count=total_in_progress_count,

        paused_tasks=paginated_paused_tasks,
        current_page_paused=current_page_paused,
        total_pages_paused=total_pages_paused,
        total_paused_count=total_paused_count,

        under_review_tasks=paginated_under_review_tasks,
        current_page_under_review=current_page_under_review,
        total_pages_under_review=total_pages_under_review,
        total_under_review_count=total_under_review_count,

        completed_tasks=paginated_completed_tasks,
        current_page_completed=current_page_completed,
        total_pages_completed=total_pages_completed,
        total_completed_count=total_completed_count,

        created_tasks=paginated_created_tasks,
        current_page_created=current_page_created,
        total_pages_created=total_pages_created,
        total_created_count=total_created_count,

        redo_tasks=paginated_redo_tasks,
        current_page_redo=current_page_redo,
        total_pages_redo=total_pages_redo,
        total_redo_count=total_redo_count,

        not_started_tasks=paginated_not_started_tasks,
        current_page_not_started=current_page_not_started,
        total_pages_not_started=total_pages_not_started,
        total_not_started_count=total_not_started_count,

        avg_completion_time=avg_completion_time,
        clients_worked_for=clients_worked_for,
        most_frequent_tasks=most_frequent_tasks,
        most_frequent_services=most_frequent_services,
        most_frequent_templates=most_frequent_templates,

        graph_data=graph_data,
        services=Service.query.all(),
        selected_service_id=service_id,
        selected_months=months,
        image_file=image_file
    )

@users_bp.route("/profile/<int:user_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    allowed_roles = ['ADMIN', 'DIRECTOR', 'SUPERVISOR']

    # Only allow access if current user is the owner or an ADMIN
    if current_user.id != user.id and current_user.role not in allowed_roles:
        flash("You are not authorized to edit this profile.", "danger")
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        password = request.form.get('password')
        role = request.form.get('role')
        department_id = request.form.get('department_id')

        # --- ADJUSTED IMAGE HANDLING ---
        # 1. Check if the 'picture' key exists in the uploaded files
        if 'picture' in request.files:
            picture_file = request.files['picture']
            
            # 2. Check if a file was actually selected (filename is not empty)
            if picture_file and picture_file.filename != '':
                try:
                    # 3. Store the OLD key so we can delete it after a successful new upload
                    old_picture_key = user.profile_image_file
                    
                    # 4. Upload the new picture
                    picture_key = save_picture(picture_file)
                    user.profile_image_file = picture_key
                    print(f"[edit_user] Profile picture updated: {picture_key}")
                    
                    # 5. Clean up the old image from DigitalOcean Spaces
                    if old_picture_key:
                        storage_service.delete_file(old_picture_key)
                        
                except Exception as e:
                    print(f"❌ Error during profile picture update: {e}")
                    flash("Failed to upload new profile picture.", "warning")

        # Update fields
        user.first_name = first_name
        user.middle_name = middle_name
        user.last_name = last_name
        user.email = email
        user.phone_number = phone_number
        user.department_id = department_id

        if role:
            user.role = role.upper()

        if password:
            user.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

        db.session.commit()
        print("[edit_user] Profile updated and committed to DB")
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('user.edit_user', user_id=user.id))

    departments = Department.query.all()
    
    # Handle the image URL for the template
    image_url = None
    if user.profile_image_file:
        image_url = storage_service.get_file_url(user.profile_image_file)
        
    return render_template('user/user_edit.html', user=user, departments=departments, roles=RoleEnum, image_url=image_url)

@users_bp.route('/profileDetail/<int:user_id>')
@login_required
def profile_detail(user_id):
    # Fetch user + department members + supervisor + assigned tasks + logs in ONE query
    user = (
        User.query
        .options(
            joinedload(User.assigned_tasks)
            .joinedload(Task.logs),
            joinedload(User.assigned_tasks)
            .joinedload(Task.task_template),
            joinedload(User.assigned_tasks)
            .joinedload(Task.client),  # <-- load clients here
            joinedload(User.department)
        )
        .get_or_404(user_id)
    )

    # Department members (excluding the user)
    department_members = [u for u in user.department.users if u.id != user.id] if user.department else []

    # Supervisor of the department
    supervisor = next((u for u in user.department.users if u.role == 'SUPERVISOR'), None) if user.department else None

    # Preprocess tasks
    tasks = user.assigned_tasks
    total_tasks = len(tasks)
    in_progress = [t for t in tasks if t.status == TaskStatusEnum.IN_PROGRESS]
    not_started = [t for t in tasks if t.status == TaskStatusEnum.ASSIGNED]
    overdue_unstarted = [t for t in not_started if t.deadline and t.deadline < datetime.utcnow()]
    completed_tasks = [t for t in tasks if t.status == TaskStatusEnum.COMPLETED]

    # Logs grouped by task
    logs_by_task = defaultdict(list)
    for task in tasks:
        for log in task.logs:
            logs_by_task[task.id].append(log)

    total_completion_seconds = 0
    completed_task_count = 0
    graph_data = []
    task_duration_counter = Counter()

    for task_id, logs in logs_by_task.items():
        active_duration = timedelta()
        end_time = None
        task_title = None

        for log in logs:
            if log.status == LogStatusEnum.COMPLETED and log.start_time and log.end_time:
                active_duration += (log.end_time - log.start_time)
                end_time = log.end_time
                task_title = log.task.title

        if active_duration.total_seconds() > 0 and end_time:
            completed_task_count += 1
            total_completion_seconds += active_duration.total_seconds()
            minutes = round(active_duration.total_seconds() / 60, 2)
            graph_data.append({
                'task_title': task_title,
                'end_time': end_time.strftime("%Y-%m-%d"),
                'duration_minutes': minutes
            })
            task_duration_counter[task_title] += 1

    avg_completion_time = None
    if completed_task_count > 0:
        avg_secs = total_completion_seconds / completed_task_count
        h, rem = divmod(avg_secs, 3600)
        m, s = divmod(rem, 60)
        avg_completion_time = f"{int(h)}h {int(m)}m {int(s)}s"

    top_5_tasks = sorted(graph_data, key=lambda x: x['duration_minutes'], reverse=True)[:5]
    most_common_task = task_duration_counter.most_common(1)[0][0] if task_duration_counter else None
    most_common_trend = [t for t in graph_data if t['task_title'] == most_common_task]

    # Top services
    service_counter = Counter(
        service.name
        for t in tasks if t.task_template and t.task_template.service
        for service in [t.task_template.service]
    )
    top_services = service_counter.most_common(3)

    # Task events
    task_events = [
        {'title': t.title, 'start': t.deadline.strftime('%Y-%m-%d'), 'url': url_for('task.get_task', task_id=t.id)}
        for t in tasks if t.deadline
    ]

    # Frequent analysis
    task_titles = [t.title for t in tasks]
    service_names = [t.task_template.service.name for t in tasks if t.task_template and t.task_template.service]
    template_titles = [t.task_template.title for t in tasks if t.task_template]
    clients_worked_for = defaultdict(list)
    for task in tasks:
        if task.client:  # make sure task has a client
            clients_worked_for[task.client.name].append(task)
        most_frequent_tasks = Counter(task_titles).most_common(5)
        most_frequent_services = Counter(service_names).most_common(5)
        most_frequent_templates = Counter(template_titles).most_common(5)

    image_file = url_for('static', filename='profile_pics/' + user.profile_image_file)

    return render_template(
        "user/profile.html",
        user=user,
        department_members=department_members,
        supervisor=supervisor,
        total_tasks=total_tasks,
        overdue_unstarted=overdue_unstarted,
        in_progress=in_progress,
        completed_tasks=completed_tasks,
        avg_completion_time=avg_completion_time,
        top_5_tasks=top_5_tasks,
        most_common_task=most_common_task,
        most_common_trend=most_common_trend,
        top_services=top_services,
        graph_data=graph_data,
        most_frequent_tasks=most_frequent_tasks,
        most_frequent_services=most_frequent_services,
        most_frequent_templates=most_frequent_templates,
        task_events=task_events,
        image_file=image_file,
        clients_worked_for=clients_worked_for 
    )

@users_bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        identifier = request.form['identifier']  # This can be either username or email

        # Find the user by either username or email
        user = User.query.filter_by(email=identifier).first()

        if user:
            print(f"Password reset requested for: {user.email}")
            # Generate a bcrypt token for the reset link
            reset_token = user.generate_reset_token()  # Token generation logic here
            reset_link = url_for('user.reset_password', token=reset_token, _external=True)
            
            # Set the reset token and expiration in the user record
            user.reset_token = reset_token
            user.reset_token_expiry = datetime.now() + timedelta(minutes=30)  # 30-minute expiry
            db.session.commit()

            try:
                # FIXED: Use run_async_in_background and pass correct arguments
                from app.utils.notification import run_async_in_background, send_password_reset_email_async
                run_async_in_background(send_password_reset_email_async, user.id, reset_link)

                flash("Password reset link sent! Check your email.", "info")
                return redirect(url_for('auth.login')) # Assuming login route is auth.login
            except Exception as e:
                # Error is already printed in the notification function
                flash("There was an error sending the password reset email. Please try again.", "danger")
                return redirect(url_for('user.reset_password_request'))
            
        flash("No user found with that username or email.", "danger")
        return redirect(url_for('user.reset_password_request'))
            
    return render_template('user/reset_password_request.html') # Assuming template path

@users_bp.route('/reset_password/<path:token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    print(f"Attempting password reset with token: {token}")

    # Check if the user exists, and the token is valid (i.e., not expired)
    if user and user.reset_token_expiry > datetime.now():
        if request.method == 'POST':
            new_password = request.form['password']

            # Hash the new password using bcrypt
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            
            # Update the user's password
            user.password_hash = hashed_password # Make sure this matches your model (e.g., password_hash)
            user.reset_token = None  # Clear the token after successful reset
            user.reset_token_expiry = None  # Clear the expiry timestamp
            db.session.commit()

            flash("Your password has been reset. Please log in.", "success")
            return redirect(url_for('auth.login')) # Assuming login route is auth.login

        return render_template('user/reset_password.html', token=token) # Assuming template path

    flash("The reset link is either invalid or expired.", "danger")
    return redirect(url_for('user.reset_password_request'))

@users_bp.route("/user/<int:user_id>/delete", methods=['POST'])
@login_required
@supervisors_admins_directors # Use your admin-only decorator
def delete_user(user_id):
    """
    Performs a soft-delete on a user.
    This anonymizes their personal data but preserves their ID and relationships
    for historical reporting.
    """
    user_to_delete = User.query.get_or_404(user_id)
    
    # --- Safety Checks ---
    if user_to_delete.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('user.get_users'))
        
    # Example: Protect a primary admin account (e.g., ID 1)
    if user_to_delete.id == 1: 
        flash('The primary admin account cannot be deleted.', 'danger')
        return redirect(url_for('user.get_users'))

    # --- Perform the Soft Delete ---
    
    # 1. Mark as deleted
    user_to_delete.deleted_at = datetime.utcnow()
    user_to_delete.deleted_by_id = current_user.id
    
    db.session.commit()
    
    flash(f'User has been successfully deleted and anonymized.', 'success')
    return redirect(url_for('user.get_users'))