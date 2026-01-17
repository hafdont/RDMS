from flask import Blueprint, request, jsonify, session, render_template, url_for, flash, redirect, current_app, abort
from app.models import *
from app.utils.notification import send_department_reviewer_notification_async, run_async_in_background
from flask_login import login_required, current_user
from app.utils.db import db
from sqlalchemy.orm import joinedload
from collections import defaultdict
from sqlalchemy.orm import joinedload
from .auth_routes import directors_and_admins, directors_only, supervisors_admins_directors, all_except_interns


department_bp = Blueprint('department', __name__, url_prefix='/departments')

# Route to list all departments
@department_bp.route('/')
@login_required
@supervisors_admins_directors
def list_departments():
    departments = Department.query.options(joinedload(Department.reviewers)).all()
    return render_template('departments/list_departments.html', departments=departments)

# Route to create a new department
@department_bp.route('/create', methods=['GET', 'POST'])
@login_required
@directors_and_admins
def create_department():
    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Department name is required.', 'danger')
        else:
            existing_dept = Department.query.filter_by(name=name).first()
            if existing_dept:
                flash('A department with this name already exists.', 'warning')
            else:
                new_dept = Department(name=name)
                db.session.add(new_dept)
                db.session.commit()
                flash(f'Department "{name}" created successfully!', 'success')
                return redirect(url_for('department.list_departments'))
    return render_template('departments/create_department.html')


# Route to view and update a department (including reviewers)
@department_bp.route('/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
@directors_and_admins
def department_reviewer(dept_id):
    department = Department.query.get_or_404(dept_id)
    
    # Get all users who can potentially be reviewers (e.g., Supervisors and Directors)
    potential_reviewers = User.query.filter(
        User.role.in_(['SUPERVISOR', 'DIRECTOR', 'ADMIN'])
    ).order_by(User.first_name).all()

    if request.method == 'POST':
        previous_reviewer_ids = {r.id for r in department.reviewers}

        # Update department name
        new_name = request.form.get('name')
        if new_name and new_name != department.name:
            department.name = new_name
            flash('Department name updated.', 'success')

        # Update reviewers
        reviewer_ids = request.form.getlist('reviewer_ids') # Get list of selected user IDs
        selected_reviewers = User.query.filter(User.id.in_(reviewer_ids)).all()
        
        department.reviewers = selected_reviewers # Magically updates the association table
        
        db.session.commit()
        # Get the list of reviewer IDs *after* the update
        current_reviewer_ids = {r.id for r in department.reviewers}
        # Find the IDs of the newly appointed reviewers
        newly_appointed_ids = current_reviewer_ids - previous_reviewer_ids

        # Loop through the newly appointed reviewers and send a notification for each
        for appointee_id in newly_appointed_ids:
            appointee = User.query.get(appointee_id)
            if appointee:
                # CORRECTED: Use positional arguments with IDs
                run_async_in_background(
                    send_department_reviewer_notification_async, 
                    current_user.id,   # appointer_id
                    appointee.id,      # appointee_id
                    department.id      # department_id
                )
               
        flash('Department reviewers updated successfully!', 'success')
        return redirect(url_for('department.list_departments'))

    return render_template(
        'departments/edit_department.html',
        department=department,
        potential_reviewers=potential_reviewers
    )




@department_bp.route('/<int:dept_id>', methods=['GET'])
@login_required
@supervisors_admins_directors
def get_department_details(dept_id):
    department = Department.query.get_or_404(dept_id)
    
    department_members = User.query.filter_by(department_id=dept_id).order_by(User.role).all()
    
    members_by_role = defaultdict(list)
    for member in department_members:
        members_by_role[member.role.value].append({
            'id': member.id,
            'first_name': member.first_name,
            'last_name': member.last_name,
            'email': member.email,
            'profile_image_file': member.profile_image_file # Make sure to add this attribute to your User model's data
        })

    tasks = Task.query.join(User, Task.assigned_to_id == User.id)\
                      .filter(User.department_id == dept_id)\
                      .options(joinedload(Task.client))\
                      .all()

    client_tasks_summary = defaultdict(lambda: {'active': [], 'under_review': [], 'completed': []})
    for task in tasks:
        if task.client:
            client_name = task.client.name
            task_info = {
                'task_id': task.id,
                'title': task.title,
                'status': task.status.value,
                'assigned_to_full_name': task.assignee.full_name,
                'deadline': task.deadline.isoformat() if task.deadline else None
            }
            
            if task.status.value in ['Assigned', 'In Progress', 'Paused', 'Re assigned']:
                client_tasks_summary[client_name]['active'].append(task_info)
            elif task.status.value in ['submited', 'Under Review', 'Manager Review', 'Partner Review']:
                client_tasks_summary[client_name]['under_review'].append(task_info)
            elif task.status.value == 'Completed':
                client_tasks_summary[client_name]['completed'].append(task_info)

    return render_template('/departments/get_department.html', 
                           department_name=department.name,
                           members_by_role=members_by_role,
                           client_tasks_summary=client_tasks_summary)


@department_bp.route('/<int:department_id>/delete', methods=['POST'])
@login_required
@directors_and_admins
def delete_department(department_id):
    department = Department.query.get_or_404(department_id)

    # Soft delete
    department.deleted_at = datetime.utcnow()
    department.deleted_by = current_user  # requires flask-login
    db.session.commit()

    flash(f'Department "{department.name}" has been deleted.', 'success')
    return redirect(url_for('department.list_departments'))