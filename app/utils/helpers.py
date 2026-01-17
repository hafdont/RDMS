# app/utils/helpers.py
from datetime import datetime
import pytz
from app import db
from app.models import *
from datetime import datetime, timezone
from flask_login import login_required, current_user
from sqlalchemy import func, case
from sqlalchemy.orm import joinedload, subqueryload


def get_next_reviewer_info(task):
    """
    Helper function to determine who is next in line to review a task.
    Returns a string of user names.
    """
    reviewers = []
    
    if task.status == TaskStatusEnum.REVIEW:
        # Standard task review logic: Director OR creator's department supervisor(s)
        if task.creator and task.creator.department:
            # Find supervisors in the creator's department
            supervisors = User.query.filter(
                User.department_id == task.creator.department_id,
                User.role == 'SUPERVISOR'
            ).all()
            if supervisors:
                reviewers.extend([s.first_name for s in supervisors])
        
        # Add Director as a general rule if no specific supervisors found
        if not reviewers:
            return "Director or All Supervisors"
        return f"Director or {', '.join(reviewers)}"

    elif task.status == TaskStatusEnum.MANAGER_REVIEW:
        # VAT task, first review logic: Director OR assignee's department reviewer(s)
        if task.assignee and task.assignee.department and task.assignee.department.reviewers:
            reviewers.extend([r.first_name for r in task.assignee.department.reviewers])

        if not reviewers:
            return "Director or Dept. Reviewer"
        return f"Director or {', '.join(reviewers)}"

    elif task.status == TaskStatusEnum.PARTNER_REVIEW:
        # VAT task, final review logic: The job's review partner
        if task.job and task.job.review_partner:
            return f"Partner: {task.job.review_partner.full_name}"
        return "Review Partner (Not Assigned)"
    
    # For any other status, return nothing as it's not "action required"
    return ""

def make_task_from_data(
    title: str,
    description: str,
    assigned_to_id: int,
    created_by_id: int,
    client_id: int,
    task_template_id: int,
    job_id: int = None,
    deadline_str: str = None,
    estimated_value: int = 0,
    estimated_unit: str = 'minutes',
    priority_str: str = 'Medium', # Ensure this default is 'Medium'
    tz_name: str = 'Africa/Nairobi',
    recurrence_str: str = 'NONE'
) -> Task:
    # 1) Deadline conversion
    utc_deadline = None
    if deadline_str:
        local_tz = pytz.timezone(tz_name)
        naive = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
        local_dt = local_tz.localize(naive)
        utc_deadline = local_dt.astimezone(pytz.utc)

    # 2) Estimated time
    val = int(estimated_value)
    if estimated_unit == 'days':
        minutes = val * 24 * 60
    elif estimated_unit == 'hours':
        minutes = val * 60
    else:
        minutes = val

    # --- THIS IS THE CRITICAL FIX FOR PRIORITY ---
    # Look up PriorityEnum member by its string value, not its name
    priority_enum_member = PriorityEnum.MEDIUM # Default in case the string doesn't match any enum value
    for p_enum in PriorityEnum:
        if p_enum.value == priority_str:
            priority_enum_member = p_enum
            break
    # --- END CRITICAL FIX ---

    # Also ensure TaskStatusEnum is handled similarly if it's coming from a string
    status_str = 'Assigned' # Assuming a default or passed in some other way
    status_enum_member = TaskStatusEnum.ASSIGNED
    for s_enum in TaskStatusEnum:
        if s_enum.value == status_str:
            status_enum_member = s_enum
            break

        # --- Recurrence handling ---
    recurrence_enum_member = RecurrenceEnum.NONE
    try:
        recurrence_enum_member = RecurrenceEnum[recurrence_str.upper()]
    except KeyError:
        pass  # fallback to NONE if invalid
    

    task = Task(
        title=title,
        description=description,
        assigned_to_id=assigned_to_id,
        created_by_id=created_by_id,
        client_id=client_id,
        task_template_id=task_template_id,
        job_id=job_id,
        status=status_enum_member, # Use the enum member
        deadline=utc_deadline,
        estimated_minutes=minutes,
        priority=priority_enum_member, # <--- Use the correctly determined enum member
        recurrence=recurrence_enum_member 
    )
    db.session.add(task)
    return task

def can_assign_task(assigned_to_id):
    assignee = User.query.get(assigned_to_id)

    if not assignee:
        return False  # Target user doesn't exist

    # No one can assign tasks to a Director
    if assignee.role == 'DIRECTOR':
        return False

    # Interns can assign tasks only to other Interns
    if current_user.role == 'INTERN':
        return assignee.role == ['INTERN', 'ADMIN']

    # Officers can only assign to Interns
    if current_user.role == 'OFFICER':
        return assignee.role in ['INTERN', 'OFFICER', 'SUPERVISOR', 'ADMIN']

    # Supervisors can assign to Interns and Officers
    if current_user.role == 'SUPERVISOR':
        return assignee.role in ['INTERN', 'OFFICER', 'SUPERVISOR', 'ADMIN']

    # Directors can assign to anyone except other Directors (already checked above)
    if current_user.role in ('ADMIN', 'DIRECTOR'):
        return True

    return False  # fallback

def get_employee_ids():
    # This function retrieves all employee IDs (excluding managers and directors)
    return [user.id for user in User.query.filter(User.role == 'officer').all()]

def can_delete_task(task, user):
    return (
        task.created_by_id == user.id or 
        user.role in ['ADMIN', 'SUPERVISOR', 'DIRECTOR']
    )

def can_delete_job(job, user):
    """Checks if a user has permission to delete an engagement."""
    # --- FIX: Compare user.role to the enum's .value (the string) ---
    return (
        job.created_by_id == user.id or
        user.role in ['ADMIN', 'DIRECTOR', 'SUPERVISOR']
    )

def time_ago_helper(dt):
    """
    Converts a datetime object to a human-readable 'time ago' string.
    """
    if not dt:
        return ""
    
    # If the datetime object is naive, assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt
    
    seconds = diff.total_seconds()
    minutes = round(seconds / 60)
    hours = round(minutes / 60)
    days = round(hours / 24)

    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    elif minutes < 60:
        return f"{minutes} minutes ago"
    elif hours < 24:
        return f"{hours} hours ago"
    elif days < 30:
        return f"{days} days ago"
    else:
        return dt.strftime('%b %d, %Y')

