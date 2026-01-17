# --- task_factory.py ---
from app.utils.cache import cache  
from app.utils.db import db  
from app.models import User, Client, TaskTemplate, Service, Job, VatFilingMonth, Task, PriorityEnum, RecurrenceEnum, TaskStatusEnum
from datetime import datetime
import pytz
from dateutil.relativedelta import relativedelta
from app.services.users.user_service import get_users_for_assignment
from app.services.clients.client_query_service import get_clients_for_forms
from app.services.services.service_query_servic import get_services_for_forms
from app.services.jobs.job_query_service import get_jobs_for_forms
from app.services.templates.task_template_query_service import get_templates_for_forms
# -----------------------------
# 1) Form data service with caching
# -----------------------------
def get_task_form_data():
    """
    Fetch all data needed to render the create task form
    Cached for 5 minutes
    """
    cache_key = "task_form_data"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Users for assignment
    users = get_users_for_assignment()

    # Task templates
    templates = get_templates_for_forms()

    # Services
    services = get_services_for_forms()

    # Jobs + eager load services to avoid n+1
    jobs = get_jobs_for_forms()

    data = {
        "users": users,
        "templates": templates,
        "services": services,
        "jobs": jobs
    }
    cache.set(cache_key, data, timeout=300)
    return data

# -----------------------------
# 2) Add service to job helper
# -----------------------------
def add_service_to_job(job_id: int, service_id: int):
    """
    Attach a service to a job if not already attached
    """
    job = Job.query.get(job_id)
    service = Service.query.get(service_id)
    if job and service and service not in job.services:
        job.services.append(service)
        return f"Service '{service.name}' added to job."
    return None

# -----------------------------
# 3) Create VAT form helper
# -----------------------------
def create_vat_form(task: Task):
    """
    If the task is VAT-related, create VatFilingMonth record if it doesn't exist
    """
    if not task.job_id or not task.task_template_id or not task.deadline:
        return None

    job = Job.query.get(task.job_id)
    template = TaskTemplate.query.get(task.task_template_id)
    template_service = template.service if template else None

    is_vat_task = (
        template_service and template_service.name == "Tax Services"
        and template and template.title == "VAT Returns"
    )
    if not is_vat_task:
        return None

    filing_month_date = task.deadline - relativedelta(months=1)
    filing_month_str = filing_month_date.strftime("%b-%Y")

    existing_form = VatFilingMonth.query.filter_by(
        job_id=job.id, month=filing_month_str
    ).first()

    if existing_form:
        return None

    new_vat_form = VatFilingMonth(
        job_id=job.id,
        month=filing_month_str,
        nature_of_business=job.client.name
    )
    db.session.add(new_vat_form)
    return f"VAT form for {filing_month_str} created."

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
