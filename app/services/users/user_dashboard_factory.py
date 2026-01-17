from app.services.tasks.task_query_service import get_assigned_task_counts
from app.services.users.dashboard_query_service import get_director_dashboard_stats
from app.services.tasks.task_query_service import get_tasks_waiting_for_review_by_user

def build_officer_dashboard(user, context):
    context.update(get_assigned_task_counts(user.id))
    return "user/employee_dashboard.html", context

def build_intern_dashboard(user, context):
    context.update(get_assigned_task_counts(user.id))
    return "user/intern_dashboard.html", context

def build_director_dashboard(user, context):
    context.update(get_director_dashboard_stats())
    return "user/directors_dashboard.html", context

def build_supervisor_dashboard(user, context):
    context.update(get_assigned_task_counts(user.id))
    context["tasks_waiting_my_review"] = get_tasks_waiting_for_review_by_user(user)
    return "user/manager_dashboard.html", context

def build_applicant_dashboard(user, context):
    return "redirect", "opportunities.careers"

DASHBOARD_BUILDERS = {
    'OFFICER': build_officer_dashboard,
    'SUPERVISOR': build_supervisor_dashboard,
    'DIRECTOR': build_director_dashboard,
    'ADMIN': build_director_dashboard,
    'INTERN': build_intern_dashboard,
    'APPLICANT': build_applicant_dashboard
}
