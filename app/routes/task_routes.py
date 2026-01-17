from flask import Blueprint, request, jsonify, session, render_template, url_for, flash, redirect, current_app, send_from_directory, abort
from app.models import *
from flask_login import login_required, current_user
from app.utils.db import db
import pytz
from pytz import timezone
from app.utils.notification import send_task_notification_async, run_async_in_background, send_task_review_decision_notification_async, send_task_submitted_notification_async
from app.utils.notifications import create_and_emit_notification
import os
from werkzeug.utils import secure_filename
from sqlalchemy import func, desc, case, distinct
from sqlalchemy.orm import aliased
from app.utils.helpers import can_assign_task, get_employee_ids, can_delete_task, get_next_reviewer_info
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from calendar import month_abbr
from itertools import groupby
from sqlalchemy.orm import joinedload, subqueryload
from botocore.exceptions import ClientError
from app.utils.storage_service import storage_service
from app.services.tasks.task_factory import (
    get_task_form_data,
    make_task_from_data,
    add_service_to_job,
    create_vat_form
    
)

from app.services.users.user_service import get_users_for_assignment

from app.services.clients.client_query_service  import search_clients_by_name

task_bp= Blueprint('task', __name__)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def get_date_range(period):
    """Calculate date range based on period filter"""
    now = datetime.utcnow()
    
    if period == 'today':
        start_date = datetime.combine(now.date(), datetime.min.time())
    elif period == 'week':
        start_date = now - timedelta(days=now.weekday())  # Start of week (Monday)
        start_date = datetime.combine(start_date.date(), datetime.min.time())
    elif period == 'month':
        start_date = now.replace(day=1)  # First day of current month
        start_date = datetime.combine(start_date.date(), datetime.min.time())
    elif period == '6months':
        start_date = now - timedelta(days=30*6)  # Approximately 6 months back
    else:
        start_date = None  # No date filter
    
    return start_date

@task_bp.context_processor
def inject_task_helpers():
    """Injects helper functions into the template context."""
    
    # Return a dictionary of functions to make available in templates
    return dict(get_next_reviewer_info=get_next_reviewer_info, TaskStatusEnum=TaskStatusEnum)

def _handle_task_completion(task, db_session):
    """
    Handles post-completion logic for a task, including recurrence and VAT form creation.
    Returns a dynamic success message for flashing to the user.
    """
    # Default message if the task is not recurring
    success_message = "Task has been marked as completed!"

    if not task.recurrence or task.recurrence == RecurrenceEnum.NONE or not task.deadline:
        return success_message

    try:
        next_deadline = None
        if task.recurrence == RecurrenceEnum.DAILY:
            next_deadline = task.deadline + relativedelta(days=1)
        elif task.recurrence == RecurrenceEnum.WEEKLY:
            next_deadline = task.deadline + relativedelta(weeks=1)
        elif task.recurrence == RecurrenceEnum.MONTHLY:
            next_deadline = task.deadline + relativedelta(months=1)
        elif task.recurrence == RecurrenceEnum.YEARLY:
            next_deadline = task.deadline + relativedelta(years=1)

        if next_deadline:
            # Check if the next task already exists to prevent duplicates
            next_task_exists = Task.query.filter(
                Task.job_id == task.job_id,
                Task.task_template_id == task.task_template_id,
                Task.deadline == next_deadline
            ).first()

            if not next_task_exists:
                # Create the new recurring task
                new_task = Task(
                    title=task.title,
                    description=task.description,
                    assigned_to_id=task.assigned_to_id,
                    created_by_id=task.created_by_id,
                    client_id=task.client_id,
                    task_template_id=task.task_template_id,
                    job_id=task.job_id,
                    deadline=next_deadline,
                    estimated_minutes=task.estimated_minutes,
                    priority=task.priority,
                    status=TaskStatusEnum.ASSIGNED,
                    recurrence=task.recurrence
                )
                db_session.add(new_task)
                success_message = f"Task completed and recurring task scheduled for {next_deadline.strftime('%b-%d-%Y')}."

                # --- VAT Form logic, now tied to the completion of a VAT task ---
                if (task.task_template and task.task_template.service and task.task_template.service.name == 'Tax Services' and
                        task.task_template and task.task_template.title == 'VAT Returns'):
                    
                    vat_month_date = next_deadline - relativedelta(months=1)
                    vat_month_str = vat_month_date.strftime('%b-%Y')

                    vat_form_exists = VatFilingMonth.query.filter_by(
                        job_id=task.job_id, month=vat_month_str
                    ).first()
                    if not vat_form_exists:
                        new_vat_form = VatFilingMonth(
                            job_id=task.job_id,
                            month=vat_month_str,
                            nature_of_business=task.job.client.name
                        )
                        db_session.add(new_vat_form)
                        flash(f"New VAT form for {vat_month_str} created.", "info")

    except Exception as e:
        current_app.logger.error(f"Error during recurrence logic for task {task.id}: {e}", exc_info=True)
        flash("A server error occurred while creating the recurring task. Please notify an administrator.", "danger")

    return success_message

@task_bp.route("/task/new", methods=["GET", "POST"])
@login_required
def create_task():
    local_tz = pytz.timezone("Africa/Nairobi")
    # --- GET FORM DATA (USERS, CLIENTS, TEMPLATES, SERVICES, JOBS) ---
    form_data = get_task_form_data()
    users = form_data["users"]
    templates = form_data["templates"]
    services = form_data["services"]
    jobs = form_data["jobs"]

    preselected_client = None
    preselected_client_id = request.args.get("client_id", type=int)
    preselected_job_id = request.args.get("job_id", type=int)


    if preselected_client_id:
        preselected_client = Client.query.get(preselected_client_id)



    if request.method == "POST":
        # --- 1) Parse form values ---
        deadline_str = request.form.get("deadline")
        if deadline_str:
            naive_deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
            local_deadline = local_tz.localize(naive_deadline)
            utc_deadline = local_deadline.astimezone(pytz.utc)

        assigned_to_id = int(request.form.get("assigned_to"))
        client_id = request.form.get("client_id")
        task_template_id = request.form.get("task_template_id")
        service_id = request.form.get("service_id")

        value = int(request.form.get("estimated_value", 0))
        unit = request.form.get("estimated_unit", "minutes")
        title = request.form.get("title")
        priority_str = request.form.get("priority", "MEDIUM")
        description = request.form.get("description")
        recurrence_str = request.form.get("recurrence", "NONE")
        job_id_from_form = request.form.get("job_id")
        final_job_id = int(job_id_from_form) if job_id_from_form else None

        # --- 2) Permission check ---
        if not can_assign_task(assigned_to_id):
            flash("You are not allowed to assign this task to the selected user.", "danger")
            return redirect(url_for("task.create_task"))

        # --- 3) Create task ---
        task = make_task_from_data(
            title=title,
            description=description,
            assigned_to_id=assigned_to_id,
            created_by_id=current_user.id,
            client_id=int(client_id) if client_id else None,
            task_template_id=int(task_template_id) if task_template_id else None,
            job_id=final_job_id,
            deadline_str=deadline_str,
            estimated_value=value,
            estimated_unit=unit,
            priority_str=priority_str,
            recurrence_str=recurrence_str
        )

        # --- 4) Add service to job if provided ---
        if final_job_id and service_id:
            service_msg = add_service_to_job(final_job_id, int(service_id))
            if service_msg:
                flash(service_msg, "info")

        # --- 5) Check for VAT task ---
        vat_msg = create_vat_form(task)
        if vat_msg:
            flash(vat_msg, "info")

        # --- 6) Commit all changes ---
        db.session.commit()

        # --- 7) Notifications ---
        notif_msg = f"You've been assigned a new task: {task.title}"
        notif_url = url_for("task.get_task", task_id=task.id)
        create_and_emit_notification(task.assigned_to_id, notif_msg, notif_url, actor_id=current_user.id)
        run_async_in_background(send_task_notification_async, task.id)

        flash("Task created successfully!", "success")
        return redirect(url_for("task.get_task", task_id=task.id))

    # --- GET: Render template ---
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_local = now_utc.astimezone(local_tz)

    return render_template(
        "tasks/new_task.html",
        users=users,
        templates=templates,
        services=services,
        jobs=jobs,
        now_local=now_local,
        preselected_job_id=preselected_job_id,
        preselected_client=preselected_client
    )

@task_bp.route('/task/<int:task_id>')
@login_required
def get_task(task_id):

    assignable_users = get_users_for_assignment()
    
    # 1. THE FIX: ONE query to get everything
    # We load the task AND all its related data at the same time.
    task = Task.query.options(
        # Use subqueryload for collections (lists of items)
        # and chain 'joinedload' to get the user for each item
        subqueryload(Task.logs).joinedload(TaskLog.user),
        subqueryload(Task.approvals).joinedload(TaskApproval.approver),
        subqueryload(Task.notes).joinedload(TaskNote.user),
        subqueryload(Task.documents).joinedload(TaskDocument.uploaded_by),
        
        # Use joinedload for single-item relationships
        # and chain to get related items (job's client, template's service)
        joinedload(Task.job).joinedload(Job.client),
        joinedload(Task.creator),
        joinedload(Task.assignee),
        joinedload(Task.task_template).joinedload(TaskTemplate.service)
    ).get_or_404(task_id)

    # 2. Authorization (No change)
    privileged_roles = {'SUPERVISOR', 'DIRECTOR', 'ADMIN'}
    if not (
        task.assigned_to_id == current_user.id or
        task.created_by_id == current_user.id or
        current_user.role in privileged_roles
    ):
        return abort(403, description="You are not authorized to view this task.")

    # 3. --- NO MORE QUERIES ---
    #    Accessing this data is now "free". It's already in memory.
    logs = sorted(task.logs, key=lambda x: x.start_time, reverse=True)
    approvals = sorted(task.approvals, key=lambda x: x.id, reverse=True)
    job = task.job # Also "free"

    # 4. The rest of your logic is unchanged
    #    These targeted queries are specific and efficient, so they are fine.
    local_tz = pytz.timezone('Africa/Nairobi')
    vat_form = None 

    if job: # 'job' is already loaded
        # 'task.task_template' and 'service' are also already loaded
        if (task.task_template and task.task_template.service and task.task_template.service.name == 'Tax Services' and 
            task.task_template and task.task_template.title == 'VAT Returns' and 
            task.deadline):
            
            vat_month_date = task.deadline.astimezone(local_tz) - relativedelta(months=1)
            month_str = vat_month_date.strftime('%b-%Y')
            
            # This is Query 2 (which is fine)
            vat_form = VatFilingMonth.query.filter_by(job_id=job.id, month=month_str).first()

    # This is Query 3 (fine)
    last_active_log = TaskLog.query.filter_by(
        task_id=task.id,
        user_id=current_user.id
    ).filter(
        (TaskLog.status == LogStatusEnum.STARTED) | (TaskLog.status == LogStatusEnum.PAUSED)
    ).order_by(
        TaskLog.start_time.desc()
    ).first()

    # This is Query 4 (fine)
    latest_completed_log = TaskLog.query.filter_by(
        task_id=task.id,
        user_id=current_user.id,
        status=LogStatusEnum.COMPLETED
    ).order_by(
        TaskLog.end_time.desc()
    ).first()

    # 5. Render
    return render_template('tasks/task_detail.html',
                           task=task,
                           logs=logs,
                           approvals=approvals,
                           local_tz=local_tz,
                           pytz=pytz,
                           last_active_log=last_active_log,
                           latest_completed_log=latest_completed_log,
                           TaskStatusEnum=TaskStatusEnum,
                           PriorityEnum=PriorityEnum,
                           job=job,
                           vat_form=vat_form,
                           users=assignable_users
                          )

@task_bp.route('/tasks/assigned/<int:user_id>', methods=['GET'])
@login_required
def get_assigned_tasks(user_id):
    target_user = User.query.get_or_404(user_id)

    # --- NEW PERMISSION CHECK ---
    # Check if the current user is the target user OR has a privileged role
    if not (current_user.id == target_user.id or 
            current_user.role in ['ADMIN', 'DIRECTOR', 'SUPERVISOR']):
        
        # If not, deny access
        flash('You do not have permission to view these tasks.', 'danger')
        return redirect(url_for('main.dashboard')) # Or any other safe page
    # --- END PERMISSION CHECK --
    
    # Get parameters from URL: /.../123?tab=in_progress&page=2
    current_tab = request.args.get('tab', 'assigned') # Default to 'assigned' tab
    page = request.args.get('page', 1, type=int)
    
    # --- THIS IS THE NEW PART ---
    # Check if this is an async request from our JavaScript
    is_partial = request.args.get('partial') == 'true'
    # --- END NEW PART ---

    pagination_data = None
    local_tz = pytz.timezone('Africa/Nairobi')
    now = datetime.utcnow()

    # ... (Your entire query logic for 'base_task_query', 'if current_tab == ...', etc. stays EXACTLY THE SAME) ...
    # Base Task Query (applies to most tabs)
    base_task_query = Task.query.filter(
        Task.assigned_to_id == user_id,
        Task.deleted_at == None
    )
    
    task_options = [
        joinedload(Task.creator),
        joinedload(Task.client),
        joinedload(Task.job)
    ]
    
    query = None # Initialize query
    if current_tab == 'assigned':
        query = base_task_query.filter(Task.status == TaskStatusEnum.ASSIGNED).options(*task_options).order_by(Task.deadline.asc())
    elif current_tab == 'in_progress':
        query = base_task_query.filter(Task.status == TaskStatusEnum.IN_PROGRESS).options(*task_options).order_by(Task.deadline.asc())
    elif current_tab == 'paused':
        query = base_task_query.filter(Task.status == TaskStatusEnum.PAUSED).options(*task_options).order_by(Task.deadline.asc())
    elif current_tab == 'under_review':
        query = base_task_query.filter(Task.status.in_([TaskStatusEnum.REVIEW, TaskStatusEnum.MANAGER_REVIEW, TaskStatusEnum.PARTNER_REVIEW])).options(*task_options).order_by(Task.updated_at.desc())
    elif current_tab == 'rejected':
        query = base_task_query.filter(Task.status == TaskStatusEnum.RE_ASSIGNED).options(*task_options).order_by(Task.updated_at.desc())
    elif current_tab == 'overdue':
        query = base_task_query.filter(Task.deadline < now, Task.status.notin_([TaskStatusEnum.COMPLETED, TaskStatusEnum.REVIEW, TaskStatusEnum.MANAGER_REVIEW, TaskStatusEnum.PARTNER_REVIEW])).options(*task_options).order_by(Task.deadline.asc())
    elif current_tab == 'engagements':
        query = Job.query.filter(Job.tasks.any(Task.assigned_to_id == user_id), Job.deleted_at == None).options(subqueryload(Job.tasks).joinedload(Task.assignee), joinedload(Job.client), joinedload(Job.creator), joinedload(Job.services)).order_by(Job.created_at.desc())
    else: # Default case
        query = base_task_query.filter(Task.status == TaskStatusEnum.ASSIGNED).options(*task_options).order_by(Task.deadline.asc())

    # Paginate the selected query
    pagination_data = query.paginate(page=page, per_page=15, error_out=False)

    # --- THIS IS THE NEW PART ---
    # Prepare the context dictionary
    context = {
        'pagination': pagination_data,
        'target_user': target_user,
        'current_tab': current_tab,
        'local_tz': local_tz,
        'pytz': pytz,
        'now': now,
        'timedelta': timedelta
    }

    if is_partial:
        # If it's an async request, send ONLY the partial
        if current_tab == 'engagements':
            return render_template('partials/_engagement_list.html', **context)
        else:
            return render_template('partials/_task_list_table.html', **context)
    else:
        # If it's a normal page load, send the full page
        return render_template('tasks/tasks.html', **context)

@task_bp.route('/task/<int:task_id>/<action>', methods=['POST'])
@login_required
def update_task_progress(task_id, action):
    task = Task.query.get_or_404(task_id)

    # ✅ Only the assigned user may update the task
    if task.assigned_to_id != current_user.id:
        return jsonify({
            "error": "You are not authorized to perform this action. Only the assignee may update this task."
        }), 403

    try:
        action = action.lower()

        if action in ['start', 'resume']:
            if task.status in [TaskStatusEnum.ASSIGNED, TaskStatusEnum.PAUSED, TaskStatusEnum.RE_ASSIGNED]:
                new_log = TaskLog(
                    task_id=task.id, user_id=current_user.id,
                    status=LogStatusEnum.STARTED, start_time=datetime.utcnow()
                )
                db.session.add(new_log)
                task.status = TaskStatusEnum.IN_PROGRESS
                db.session.commit()
                return jsonify({
                    "message": f"Task {'resumed' if action == 'resume' else 'started'} successfully.",
                    "task_status": task.status.value
                }), 200
            else:
                return jsonify({"error": "Task cannot be started/resumed from its current status."}), 400

        elif action == 'pause':
            # --- This section is correct, no changes needed ---
            if task.status == TaskStatusEnum.IN_PROGRESS:
                active_log = TaskLog.query.filter_by(
                    task_id=task.id, user_id=current_user.id, status=LogStatusEnum.STARTED
                ).order_by(TaskLog.start_time.desc()).first()

                if active_log:
                    active_log.end_time = datetime.utcnow()
                    active_log.status = LogStatusEnum.PAUSED
                    task.status = TaskStatusEnum.PAUSED
                    db.session.commit()
                    return jsonify({"message": "Task paused successfully.", "task_status": task.status.value}), 200
                else:
                    return jsonify({"error": "No active task log found to pause."}), 400
            else:
                return jsonify({"error": "Only tasks 'In Progress' can be paused."}), 400

        # --- THIS IS THE CORRECTED AND RESTRUCTURED SECTION ---
        elif action == 'complete':
            # New Validation Check: Must have at least one note or document
            has_note = TaskNote.query.filter_by(
                task_id=task.id, user_id=current_user.id
            ).first() is not None
            has_document = TaskDocument.query.filter_by(
                task_id=task.id, uploaded_by_id=current_user.id
            ).first() is not None

            if not has_note and not has_document:
                return jsonify({
                    "error": "You must attach at least one note or document before completing the task."
                }), 400
            # 1. Add a "guard clause" to handle wrong status immediately.
            if task.status != TaskStatusEnum.IN_PROGRESS:
                return jsonify({"error": "Only tasks 'In Progress' can be submitted."}), 400

            # 2. Complete the active log
            active_log = TaskLog.query.filter_by(
                task_id=task.id, user_id=current_user.id, status=LogStatusEnum.STARTED
            ).order_by(TaskLog.start_time.desc()).first()

            if active_log:
                active_log.end_time = datetime.utcnow()
                active_log.status = LogStatusEnum.COMPLETED
            
            # 3. Determine if it's a VAT task
            # --- FIX: Get the template and service from the task object ---
            template = task.task_template
            template_service = template.service if template else None
            
            is_vat_task = (
                task.job and
                template_service and template_service.name == 'Tax Services' and
                template and template.title == 'VAT Returns'
            )

            # 4. Set status and send the correct notification
            if is_vat_task:
                task.status = TaskStatusEnum.MANAGER_REVIEW
                message = "Task submitted for manager review."
                department = task.job.creator.department
                notif_msg = f"VAT Task '{task.title}' submitted by {current_user.first_name} requires your review."
                notif_url = url_for('task.get_task', task_id=task.id)
                
                if department and department.reviewers:
                    for reviewer in department.reviewers:
                        create_and_emit_notification(reviewer.id, notif_msg, notif_url, actor_id=current_user.id)
            else:
                task.status = TaskStatusEnum.REVIEW
                message = "Task submitted for review."
                notif_msg = f"{current_user.first_name} has submitted task '{task.title}' for your review."
                notif_url = url_for('task.get_task', task_id=task.id)
                create_and_emit_notification(task.created_by_id, notif_msg, notif_url, actor_id=current_user.id)
            
            # 5. Commit and return a single, clean response
            db.session.commit()
            return jsonify({
                "message": message,
                "task_status": task.status.value
            }), 200

        else:
            return jsonify({"error": f"'{action}' is not a valid task action."}), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[Error] Task Update Failed: {e}")
        return jsonify({"error": "Something went wrong while updating the task."}), 500

@task_bp.route('/clients/search')
@login_required
def search_clients():
    query = request.args.get('q', '', type=str)
    results = search_clients_by_name(query)
    return jsonify(clients=results)


@task_bp.route('/task/<int:task_id>/upload', methods=['POST'])
@login_required
def upload_document(task_id):
    task = Task.query.get_or_404(task_id)
    files = request.files.getlist('document')

    if not files or files[0].filename == '':
        flash("No files selected.", "danger")
        return redirect(url_for('task.get_task', task_id=task.id))

    successful_uploads = 0

    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)

            if not allowed_file(filename):
                flash(f"File type for '{filename}' is not allowed.", "danger")
                continue

            try:
                # Upload to DigitalOcean Spaces
                from app.utils.storage_service import storage_service
                upload_result = storage_service.upload_file(file, folder='task_documents')
                
                # Store file info in database
                document = TaskDocument(
                    task_id=task.id,
                    uploaded_by_id=current_user.id,
                    file_name=upload_result['original_filename'],
                    file_path=upload_result['key'],
                    file_mime_type=upload_result['mimetype']
                )
                
                db.session.add(document)
                successful_uploads += 1

            except Exception as e:
                print(f"❌ ERROR in upload_document: {type(e).__name__}: {e}")
                flash(f"Error uploading '{filename}': {str(e)}", "danger")

    if successful_uploads > 0:
        try:
            db.session.commit()
            flash(f"{successful_uploads} document(s) uploaded successfully.", "success")
        except Exception as e:
            db.session.rollback()
            print(f"❌ DB commit error: {e}")
            flash("Failed to save document metadata.", "danger")

    return redirect(url_for('task.get_task', task_id=task.id))

# --- DELETE DOCUMENT ROUTE ---
@task_bp.route('/task/<int:task_id>/document/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_document(task_id, doc_id):
    document = TaskDocument.query.get_or_404(doc_id)

    # Authorization Check
    if current_user.id != document.uploaded_by_id:
        flash("You are not authorised to delete this document.", "danger")
        return redirect(url_for('task.get_task', task_id=task_id))

    file_deleted_from_storage = False

    try:
        from app.utils.storage_service import storage_service
        
        # 1. Attempt to delete from DigitalOcean Spaces
        if storage_service.delete_file(document.file_path):
            file_deleted_from_storage = True
        else:
            # The service logs the error, we warn the user and proceed to cleanup DB anyway
            # IMPORTANT: For an orphaned file, you might choose to delete the DB entry anyway 
            # and rely on monitoring to clean up the DO file later. 
            # I will assume you want to stop the process if the file key is found in the DB but not on DO.
            flash("Warning: Could not confirm deletion of file from storage. Database entry was not removed.", "warning")
            return redirect(url_for('task.get_task', task_id=task_id))
            
    except Exception as e:
        # Catch connection/critical errors
        current_app.logger.error(f"❌ Critical error during file deletion for {document.file_path}: {e}")
        flash(f"Critical error deleting file: {str(e)}. Database entry was not removed.", "danger")
        return redirect(url_for('task.get_task', task_id=task_id))

    # 2. If storage deletion was successful, delete the database entry
    if file_deleted_from_storage:
        try:
            db.session.delete(document)
            db.session.commit()
            flash("✅ Document and its storage file deleted successfully.", "success")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"❌ DB commit error during TaskDocument deletion: {e}")
            # If DB commit fails, you have an orphaned file (deleted from DO, but still in DB)
            flash("Error deleting database record. File was deleted from storage, but is still listed here.", "danger")

    return redirect(url_for('task.get_task', task_id=task_id))


@task_bp.route('/task/<int:task_id>/note/<int:note_id>/delete', methods=['POST'])
@login_required
def delete_note(task_id, note_id):
    note = TaskNote.query.get_or_404(note_id)

    # Check if the current user is the one who wrote the note
    if current_user.id != note.user_id:
        flash("You are not authorised to delete this note.", "danger")
        return redirect(url_for('task.get_task', task_id=task_id))

    # Attempt to delete the note from the database
    try:
        db.session.delete(note)
        db.session.commit()
        flash(f"Note has been delted successfully,", "success")
        return redirect(url_for('task.get_task', task_id=task_id))

    except Exception as e:
        current_app.logger.error(f"Error deleting file {note}: {e}")
        db.session.rollback()
    flash("Document deleted successfully.", "success")
    return redirect(url_for('task.get_task', task_id=task_id))

@task_bp.route('/task/<int:task_id>/add_note', methods=['POST'])
@login_required
def add_task_note(task_id):
    task = Task.query.get_or_404(task_id)
    content = request.form.get('note_content', '').strip()

    if not content:
        flash("Note content cannot be empty.", "danger")
        return redirect(url_for('task.get_task', task_id=task_id))

    note = TaskNote(
        task_id=task.id,
        user_id=current_user.id,
        content=content
    )
    db.session.add(note)
    db.session.commit()

    # --- NEW NOTIFICATION LOGIC ---
    
    # 1. Define the notification details
    notif_msg = f"{current_user.first_name} added a note to your task: '{task.title}'"
    notif_url = url_for('task.get_task', task_id=task.id)
    
    # 2. Determine who to notify
    # Create a set to store unique user IDs to avoid sending duplicate notifications
    recipients = set()
    
    # Notify the assigned user, unless they are the one adding the note
    if task.assigned_to_id != current_user.id:
        recipients.add(task.assigned_to_id)

    # Notify the task creator, unless they are the one adding the note (and not the assignee)
    if task.created_by_id != current_user.id and task.created_by_id != task.assigned_to_id:
        recipients.add(task.created_by_id)

    # 3. Emit the notification to all recipients
    for user_id in recipients:
        create_and_emit_notification(user_id, notif_msg, actor_id=current_user.id)
    
    flash("Note added.", "success")
    return redirect(url_for('task.get_task', task_id=task_id))

@task_bp.route('/task/download/<path:file_path>')
@login_required
def download_file(file_path):
    """Generate a temporary download URL for files in DigitalOcean Spaces"""
    # Find the document by file_path (S3 key)
    document = TaskDocument.query.filter(TaskDocument.file_path == file_path).first_or_404()
    
    # Authorization check
    task = document.task 
    privileged_roles = {'SUPERVISOR', 'DIRECTOR', 'ADMIN'}
    if not (
        task.assigned_to_id == current_user.id or
        task.created_by_id == current_user.id or
        current_user.role in privileged_roles
    ):
        abort(403, description="You are not authorized to download this file.")
    
    try:
        from app.utils.storage_service import storage_service
        
        # Generate a presigned URL valid for 1 hour (3600 seconds)
        url = storage_service.get_file_url(document.file_path, expires_in=3600)
        
        if url:
            # Redirect to the temporary S3 URL
            return redirect(url)
        else:
            flash("Could not generate download URL.", "danger")
            return redirect(url_for('task.get_task', task_id=task.id))
            
    except Exception as e:
        print(f"❌ Error downloading file: {e}")
        flash(f"Error downloading file: {str(e)}", "danger")
        return redirect(url_for('task.get_task', task_id=task.id))

@task_bp.route('/task/<int:task_id>/review', methods=['POST'])
@login_required
def review_task(task_id):
    task = Task.query.get_or_404(task_id)
    decision_str = request.form.get('decision')
    remarks = request.form.get('remarks')

    try:
        decision = DecisionEnum(decision_str)
    except ValueError:
        flash("Invalid decision provided.", "danger")
        return redirect(url_for('task.get_task', task_id=task.id))

    # Record the approval decision (common to all workflows)
    approval = TaskApproval(
        task_id=task.id,
        approved_by_id=current_user.id,
        decision=decision,
        remarks=remarks
    )
    db.session.add(approval)

    # ====================================================================
    # === WORKFLOW LOGIC BASED ON TASK STATUS
    # ====================================================================

    # --- Workflow for tasks waiting on a Manager ---
    if task.status == TaskStatusEnum.MANAGER_REVIEW:
        is_reviewer = current_user in task.assignee.department.reviewers
        is_director = current_user.role == 'DIRECTOR'

        # A user can approve if they are a director, OR if they are a designated reviewer AND not the creator.
        if not is_director and (not is_reviewer or current_user.id == task.created_by_id):
            flash("You are not authorized to review this task.", "danger")
            return redirect(url_for('task.get_task', task_id=task.id))

        if decision == DecisionEnum.APPROVED:
            task.status = TaskStatusEnum.PARTNER_REVIEW
            flash("Task approved and forwarded for Partner review.", "success")
            if task.job and task.job.review_partner:
                notif_msg = f"VAT Task '{task.title}' is ready for your final review."
                notif_url = url_for('task.get_task', task_id=task.id)
                create_and_emit_notification(task.job.review_partner.id, notif_msg, notif_url, actor_id=current_user.id)
        else: # REJECT
            task.status = TaskStatusEnum.RE_ASSIGNED
            flash("Task sent back to the assignee for revision.", "warning")
            notif_msg = f"Your task '{task.title}' requires revision based on the manager's feedback."
            notif_url = url_for('task.get_task', task_id=task.id)
            create_and_emit_notification(task.assigned_to_id, notif_msg, notif_url, actor_id=current_user.id)

    # --- Workflow for tasks waiting on a Partner/Director ---
    elif task.status == TaskStatusEnum.PARTNER_REVIEW:

        # For this high-level review, only the designated partner can approve.
        # The self-approval rule is waived here as per your point.

        if not (task.job and task.job.review_partner_id == current_user.id):
            flash("You are not the designated Review Partner for this task's engagement.", "danger")
            return redirect(url_for('task.get_task', task_id=task.id))
        
        if decision == DecisionEnum.APPROVED:
            task.status = TaskStatusEnum.COMPLETED
            # --- NEW: Call the helper function on completion ---
            success_message = _handle_task_completion(task, db.session)
            flash(success_message, "success")
            notif_msg = f"Your task '{task.title}' is now complete."
            notif_url = url_for('task.get_task', task_id=task.id)
            create_and_emit_notification(task.assigned_to_id, notif_msg, notif_url, actor_id=current_user.id)
        
        else: # REJECT
            task.status = TaskStatusEnum.RE_ASSIGNED
            flash("Task sent back to the assignee with Partner feedback.", "warning")
            notif_msg = f"Your task '{task.title}' requires revision based on the Partner's feedback."
            notif_url = url_for('task.get_task', task_id=task.id)
            create_and_emit_notification(task.assigned_to_id, notif_msg, notif_url, actor_id=current_user.id)

    # --- Workflow for other standard tasks ---
    elif task.status == TaskStatusEnum.REVIEW:
        is_director = current_user.role == 'DIRECTOR'
        is_supervisor_of_creator = (current_user.role == 'SUPERVISOR' and 
                                      task.creator and 
                                      current_user.department_id == task.creator.department_id
                                      and current_user)
        
        # --- FIX 1: DEFINE is_reviewer HERE ---
        # Check if the user is a designated reviewer for the task ASSIGNEE's department
        is_reviewer = False  # Default to false
        if task.assignee and task.assignee.department:
            is_reviewer = current_user in task.assignee.department.reviewers

        
        # --- FIX 2: UPDATE THE IF STATEMENT ---
        # We check if the user fails ALL THREE conditions
        is_not_director = not is_director
        is_not_valid_supervisor = (not is_supervisor_of_creator or current_user.id == task.created_by_id)
        is_not_reviewer = not is_reviewer

        if is_not_director and is_not_valid_supervisor and is_not_reviewer:
            
            # --- FIX 3: UPDATE THE ERROR MESSAGE ---
            flash("You are not authorized to review this task. Only a Director, the creator's Supervisor, or a designated Department Reviewer may do so.", "danger")
            return redirect(url_for('task.get_task', task_id=task.id))
            
        if decision == DecisionEnum.APPROVED:
            task.status = TaskStatusEnum.COMPLETED
            # --- NEW: Call the helper function on completion ---
            success_message = _handle_task_completion(task, db.session)
            review_result = "approved and completed"
            notif_msg = f"Your task '{task.title}' was reviewed and {review_result}."
            notif_url = url_for('task.get_task', task_id=task.id)
            create_and_emit_notification(task.assigned_to_id, notif_msg, notif_url, actor_id=current_user.id)
        else: # REJECT
            task.status = TaskStatusEnum.RE_ASSIGNED
            flash("Task sent back for revision.", "warning")
            review_result = "sent back for revision"
            notif_msg = f"Your task '{task.title}' was reviewed and {review_result}."
            notif_url = url_for('task.get_task', task_id=task.id)
            create_and_emit_notification(task.assigned_to_id, notif_msg, notif_url, actor_id=current_user.id)
        
    else:
        flash("This task is not currently in a reviewable state.", "warning")
        return redirect(url_for('task.get_task', task_id=task.id))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to commit changes for task {task.id} review: {e}", exc_info=True)
        flash("A database error occurred while saving the review. Please try again.", "danger")

    return redirect(url_for('task.get_task', task_id=task.id))

# ROUTE 1: THE (NEW) MAIN DASHBOARD (ACTION ITEMS)
@task_bp.route('/tasks/dashboard', methods=['GET']) 
@login_required
def task_dashboard():
    
    today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
    
    # Get pagination parameters from query string, default to page 1
    # We use different page parameters for VAT and Standard to allow independent pagination
    page_vat = request.args.get('page_vat', 1, type=int)
    page_standard = request.args.get('page_standard', 1, type=int)
    per_page = 10 # Tasks per page for the 'Older' sections

    # Base query options to pre-load data for the review table
    review_table_options = [
        joinedload(Task.assignee),
        joinedload(Task.creator),
        joinedload(Task.job).joinedload(Job.client)
    ]

    # 1a. Today's VAT (No Pagination)
    todays_vat_tasks = Task.query.join(Job, Task.job_id == Job.id)\
        .filter(
            Task.status == TaskStatusEnum.PARTNER_REVIEW,
            Task.updated_at >= today_start,
            Task.deleted_at == None
        ).options(*review_table_options).order_by(Task.updated_at.desc()).all()

    # 1b. Older VAT (Paginated)
    older_vat_query = Task.query.join(Job, Task.job_id == Job.id)\
        .filter(
            Task.status == TaskStatusEnum.PARTNER_REVIEW,
            Task.updated_at < today_start,
            Task.deleted_at == None
        ).options(*review_table_options).order_by(Task.updated_at.desc())
    
    older_vat_pagination = older_vat_query.paginate(page=page_vat, per_page=per_page, error_out=False)
    older_vat_tasks = older_vat_pagination.items

    # 1c. Today's Standard (No Pagination)
    todays_standard_tasks = Task.query.filter(
        Task.status.in_([TaskStatusEnum.REVIEW, TaskStatusEnum.MANAGER_REVIEW]),
        Task.updated_at >= today_start,
        Task.deleted_at == None
    ).options(*review_table_options).order_by(Task.updated_at.desc()).all()

    # 1d. Older Standard (Paginated)
    older_standard_query = Task.query.filter(
        Task.status.in_([TaskStatusEnum.REVIEW, TaskStatusEnum.MANAGER_REVIEW]),
        Task.updated_at < today_start,
        Task.deleted_at == None
    ).options(*review_table_options).order_by(Task.updated_at.desc())
    
    older_standard_pagination = older_standard_query.paginate(page=page_standard, per_page=per_page, error_out=False)
    older_standard_tasks = older_standard_pagination.items

    return render_template(
        'tasks/tasks_dashboard.html',
        # Pass *only* the data this page needs
        todays_vat_tasks=todays_vat_tasks,
        
        # Paginated results and pagination objects for Older VAT
        older_vat_tasks=older_vat_tasks, # The items for the current page
        older_vat_pagination=older_vat_pagination, # The pagination object

        todays_standard_tasks=todays_standard_tasks,
        
        # Paginated results and pagination objects for Older Standard
        older_standard_tasks=older_standard_tasks, # The items for the current page
        older_standard_pagination=older_standard_pagination, # The pagination object
        
        current_page='actions' # For the template to highlight the active tab
    )

@task_bp.route('/dashboard/user-workload/<int:user_id>', methods=['GET'])
@login_required
def get_user_workload_stats(user_id):
    """Get workload stats for a specific user and time period"""
    period = request.args.get('period', 'today')
    
    # Calculate the date range based on period
    start_date = get_date_range(period)
    
    # Build the query with dynamic date filtering
    stats_query = db.session.query(
        # Count tasks with date filtering
        func.count(distinct(case((
            (Task.status == TaskStatusEnum.IN_PROGRESS) & 
            (Task.updated_at >= start_date if start_date else True), 
            Task.id
        )))).label('in_progress'),
        
        func.count(distinct(case((
            (Task.status == TaskStatusEnum.PAUSED) & 
            (Task.updated_at >= start_date if start_date else True), 
            Task.id
        )))).label('paused'),
        
        func.count(distinct(case((
            (Task.status.in_([TaskStatusEnum.REVIEW, TaskStatusEnum.MANAGER_REVIEW, TaskStatusEnum.PARTNER_REVIEW])) & 
            (Task.updated_at >= start_date if start_date else True), 
            Task.id
        )))).label('under_review'),
        
        func.count(distinct(case((
            (Task.status == TaskStatusEnum.RE_ASSIGNED) & 
            (Task.updated_at >= start_date if start_date else True), 
            Task.id
        )))).label('redo'),
        
        func.count(distinct(case((
            (Task.status == TaskStatusEnum.COMPLETED) & 
            (Task.updated_at >= start_date if start_date else True), 
            Task.id
        )))).label('completed')
    ).filter(
        Task.assigned_to_id == user_id,
        Task.deleted_at == None
    )
    
    result = stats_query.first()
    
    if result:
        stats = {
            'in_progress': result.in_progress or 0,
            'paused': result.paused or 0,
            'under_review': result.under_review or 0,
            'redo': result.redo or 0,
            'completed': result.completed or 0
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    else:
        return jsonify({
            'success': False,
            'error': 'User not found or no tasks'
        })

@task_bp.route('/tasks/dashboard/team-workload', methods=['GET'])
@login_required
def task_dashboard_workload():
    # Use the helper function to get today's start
    start_date = get_date_range('today')

    # 1. Determine the scope of the filter
    dept_filter = []

    # Check roles and build filter list
    if current_user.has_role(RoleEnum.DIRECTOR) or current_user.has_role(RoleEnum.ADMIN):
        # Directors and Admins see everything (leave filter empty or logic-free)
        is_restricted = False
    elif current_user.has_role(RoleEnum.SUPERVISOR):
        # Supervisors only see their own department
        is_restricted = True
        # Use current_user.department_id directly or from your helper
        supervised_dept_ids = [current_user.department_id] if current_user.department_id else []
    else:
        # Regular users only see their own department (or you can restrict this route entirely)
        is_restricted = True
        supervised_dept_ids = [current_user.department_id] if current_user.department_id else []

    # 2. Build the Base Query
    stats_query = db.session.query(
        User.id.label('user_id'),
        User.first_name,
        User.last_name,
        User.role,
        Department.name.label('department_name'),
        
        func.count(distinct(case(((Task.status == TaskStatusEnum.IN_PROGRESS) & (Task.updated_at >= start_date), Task.id)))).label('in_progress'),
        func.count(distinct(case(((Task.status == TaskStatusEnum.PAUSED) & (Task.updated_at >= start_date), Task.id)))).label('paused'),
        func.count(distinct(case(((Task.status.in_([TaskStatusEnum.REVIEW, TaskStatusEnum.MANAGER_REVIEW, TaskStatusEnum.PARTNER_REVIEW])) & (Task.updated_at >= start_date), Task.id)))).label('under_review'),
        func.count(distinct(case(((Task.status == TaskStatusEnum.RE_ASSIGNED) & (Task.updated_at >= start_date), Task.id)))).label('redo'),
        func.count(distinct(case(((Task.status == TaskStatusEnum.COMPLETED) & (Task.updated_at >= start_date), Task.id)))).label('completed')
    )\
    .join(Department, User.department_id == Department.id)\
    .outerjoin(Task, (Task.assigned_to_id == User.id) & (Task.deleted_at == None))\
    .filter(Department.name != 'Partners', User.deleted_at == None)

    # 3. Apply Department Restriction
    if is_restricted:
        stats_query = stats_query.filter(User.department_id.in_(supervised_dept_ids))

    # 4. Finalize Query
    team_workload_results = stats_query.group_by(
        User.id, User.first_name, User.last_name, User.role, Department.name
    ).order_by(Department.name, User.first_name).all()

    # 5. Prepare Data for Template
    team_workload_data = []
    for row in team_workload_results:
        team_workload_data.append({
            'user': {
                'full_name': f"{row.first_name} {row.last_name}", 
                'role': {'value': row.role}, 
                'id': row.user_id
            },
            'department': row.department_name,
            'stats': {
                'in_progress': row.in_progress or 0,
                'paused': row.paused or 0,
                'under_review': row.under_review or 0,
                'redo': row.redo or 0,
                'completed': row.completed or 0
            }
        })

    # Group the data by department for the template view
    grouped_workload = {k: list(v) for k, v in groupby(team_workload_data, key=lambda x: x['department'])}

    return render_template(
        'tasks/tasks_dashboard_workload.html',
        team_workload=grouped_workload,
        current_page='workload'
    )

# ROUTE 3: NEW TASK ANALYTICS PAGE
@task_bp.route('/tasks/dashboard/analytics', methods=['GET'])
@login_required
def task_dashboard_analytics():
    # This page now handles all the reporting widgets
    
    page = request.args.get('page', 1, type=int)
    dept_filter = request.args.get('dept', type=int)
    
    # 1. Assigned Tasks (Paginated)
    assigned_query = Task.query.filter(
        Task.status == TaskStatusEnum.ASSIGNED,
        Task.deleted_at == None
    ).options(joinedload(Task.assignee)).order_by(Task.deadline.asc())
    assigned = assigned_query.paginate(page=page, per_page=10, error_out=False)

    # 2. Overall Most Performed (No change, already efficient)
    overall_query = db.session.query(
        Task.title, func.count(Task.id).label('count')
    ).filter(Task.deleted_at == None)\
     .group_by(Task.title).order_by(desc('count')).limit(10).all()

    # 3. By Department (Paginated)
    dept_query = db.session.query(
        Department.name.label('dept'), Task.title, func.count(Task.id).label('count')
    ).join(User, User.department_id == Department.id)\
     .join(Task, Task.assigned_to_id == User.id)\
     .filter(Department.deleted_at == None, Task.deleted_at == None)\
     .group_by(Department.name, Task.title).order_by(Department.name, desc('count'))
    
    if dept_filter:
        dept_query = dept_query.filter(Department.id == dept_filter)
    dept_tasks = dept_query.paginate(page=page, per_page=10, error_out=False)

    # 4. By Service (Paginated)
    TaskTemplateAlias = aliased(TaskTemplate)
    ServiceAlias = aliased(Service)
    service_tasks_query = db.session.query(
        ServiceAlias.name.label('service'), Task.title, func.count(Task.id).label('count')
    ).join(TaskTemplateAlias, Task.task_template_id == TaskTemplateAlias.id)\
     .join(ServiceAlias, ServiceAlias.id == TaskTemplateAlias.service_id)\
     .filter(ServiceAlias.deleted_at == None, Task.deleted_at == None)\
     .group_by(ServiceAlias.name, Task.title).order_by(ServiceAlias.name, desc('count'))
    service_tasks = service_tasks_query.paginate(page=page, per_page=10, error_out=False)

    # 5. User Ranking
    user_ranking = (
        db.session.query(User, func.count(Task.id).label('task_count'))
        .join(Task, Task.assigned_to_id == User.id)
        .filter(Task.deleted_at == None)
        .group_by(User.id)
        .order_by(desc('task_count'))
        .options(joinedload(User.department))  # Fix N+1 in template
        .all()
    )

    depts = Department.query.filter(Department.deleted_at == None).all()

    return render_template(
        'tasks/tasks_dashboard_analytics.html',
        assigned=assigned,
        overall=overall_query,
        dept_tasks=dept_tasks,
        service_tasks=service_tasks,
        user_ranking=user_ranking,
        depts=depts,
        selected_dept=dept_filter,
        current_page='analytics'
    )

@task_bp.route('/dashboard/user-workload/<int:user_id>')
@login_required
def get_user_workload_data(user_id):
    """
    API endpoint to fetch a SINGLE user's workload data as JSON.
    Supports timeframes (week, month, etc.) OR a specific date.
    """
    try:
        timeframe = request.args.get('period', 'today')
        specific_date_str = request.args.get('date') # Format: YYYY-MM-DD
        
        today = datetime.utcnow().date()
        end_datetime = None # Default: No upper bound (all tasks since start_date)

        if specific_date_str:
            # Logic for a single specific day
            selected_date = datetime.strptime(specific_date_str, '%Y-%m-%d').date()
            start_datetime = datetime.combine(selected_date, datetime.min.time())
            # Set end_datetime to the very end of that specific day
            end_datetime = datetime.combine(selected_date, datetime.max.time())
        else:
            # Logic for your existing timeframes
            start_date = today
            if timeframe == 'week':
                start_date = today - timedelta(days=today.weekday())
            elif timeframe == 'month':
                start_date = today.replace(day=1)
            elif timeframe == '6months':
                start_date = today - timedelta(days=180)
            
            start_datetime = datetime.combine(start_date, datetime.min.time())

        # --- UPDATED QUERY ---
        # We add a filter for end_datetime if a specific date was chosen
        filters = [
            Task.assigned_to_id == user_id,
            Task.deleted_at == None,
            Task.updated_at >= start_datetime
        ]
        
        if end_datetime:
            filters.append(Task.updated_at <= end_datetime)

        stats = db.session.query(
            func.count(case(((Task.status == TaskStatusEnum.IN_PROGRESS), 1))).label('in_progress'),
            func.count(case(((Task.status == TaskStatusEnum.PAUSED), 1))).label('paused'),
            func.count(case(((Task.status.in_([TaskStatusEnum.REVIEW, TaskStatusEnum.MANAGER_REVIEW, TaskStatusEnum.PARTNER_REVIEW])), 1))).label('under_review'),
            func.count(case(((Task.status == TaskStatusEnum.COMPLETED), 1))).label('completed'),
            func.count(case(((Task.status == TaskStatusEnum.RE_ASSIGNED), 1))).label('redo')
        ).filter(*filters).one()

        return jsonify(success=True, stats={
            'in_progress': stats.in_progress,
            'paused': stats.paused,
            'under_review': stats.under_review,
            'completed': stats.completed,
            'redo': stats.redo,
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching user workload data for user {user_id}: {e}")
        return jsonify(success=False, error="Could not retrieve data."), 500

@task_bp.route('/tasks/<int:task_id>/enable-vat', methods=['POST'])
def enable_vat_requirement(task_id):
    task = Task.query.get_or_404(task_id)
    task.requires_vat_form = True
    db.session.commit()
    return jsonify({"success": True}), 200

@task_bp.route('/task/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    # 1. Retrieve the Task
    task = Task.query.get_or_404(task_id)

    if not can_delete_task(task, current_user):
        flash('You do not have permission to delete this task.', 'danger')
        return redirect(url_for('task.get_task', task_id=task_id))

    try:
        now = datetime.utcnow()
        deleter_id = current_user.id

        # 2. Soft Delete the Task
        task.deleted_at = now
        task.deleted_by_id = deleter_id
        
        # 4. Commit all changes
        db.session.commit()

        flash(f"Task '{task.title}' and all related items have been moved to the trash.", 'success')
        return redirect(url_for('task.get_assigned_tasks', user_id=current_user.id))

    except Exception as e:
        db.session.rollback()
        # Optional: Add error logging here (e.g., current_app.logger.error)
        flash("An error occurred while trying to move the task to trash.", "danger")
        return redirect(url_for('task.get_task', task_id=task_id))

@task_bp.route('/tasks/documents/<int:document_id>/view')
@login_required
def view_task_document(document_id):
    """
    Generate a temporary URL to view/download a document from DigitalOcean Spaces
    """
    document = TaskDocument.query.get_or_404(document_id)

    # Authorization check
    task = document.task 
    privileged_roles = {'SUPERVISOR', 'DIRECTOR', 'ADMIN'}
    if not (
        task.assigned_to_id == current_user.id or
        task.created_by_id == current_user.id or
        current_user.role in privileged_roles
    ):
        abort(403, description="You are not authorized to view this document.")

    try:
        from app.utils.storage_service import storage_service
        
        # Generate a presigned URL valid for 1 hour
        url = storage_service.get_file_url(document.file_path, expires_in=3600)
        
        if url:
            # Redirect to the temporary S3 URL
            return redirect(url)
        else:
            flash("Could not generate access URL for document.", "danger")
            return redirect(url_for('task.get_task', task_id=task.id))
            
    except Exception as e:
        current_app.logger.error(f"Error accessing document: {e}")
        flash(f"Error accessing document: {str(e)}", "danger")
        return redirect(url_for('task.get_task', task_id=task.id))

@task_bp.route('/task/<int:task_id>/assign', methods=['POST'])
@login_required
def assign_task(task_id):

    data = request.get_json() or {}
    new_user_id = data.get('user_id')

    if not new_user_id:
        return jsonify({'success': False, 'message': 'Missing user_id'}), 400

    # Get the task
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Task not found'}), 404
    # Update the assignee
    task.assigned_to_id = int(new_user_id)  # ensure it's an integer
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Task reassigned to user {new_user_id}',
        'task_id': task_id,
        'user_id': new_user_id
    })

