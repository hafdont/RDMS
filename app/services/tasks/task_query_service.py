from datetime import datetime
from sqlalchemy import func, case
from sqlalchemy.orm import joinedload
from app.utils.cache import cache
from app.models import Task, TaskApproval, TaskStatusEnum, DecisionEnum, User
from app.utils.db import db

CACHE_TTL = 120

def get_assigned_task_counts(user_id: int):
    cache_key = f"dashboard:task_counts:{user_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    now = datetime.utcnow()

    counts = db.session.query(
        func.count(case((
            (Task.deadline < now) &
            (Task.status.notin_([
                TaskStatusEnum.COMPLETED,
                TaskStatusEnum.REVIEW,
                TaskStatusEnum.MANAGER_REVIEW,
                TaskStatusEnum.PARTNER_REVIEW
            ])) &
            (~Task.approvals.any(TaskApproval.decision == DecisionEnum.APPROVED)),
            1
        ))).label('overdue'),

        func.count(case((Task.status == TaskStatusEnum.ASSIGNED, 1))).label('assigned'),
        func.count(case((Task.status == TaskStatusEnum.RE_ASSIGNED, 1))).label('rejected'),
        func.count(case((Task.status == TaskStatusEnum.IN_PROGRESS, 1))).label('in_progress'),
        func.count(case((Task.status == TaskStatusEnum.PAUSED, 1))).label('paused'),
        func.count(case((Task.status.in_([
            TaskStatusEnum.REVIEW,
            TaskStatusEnum.MANAGER_REVIEW,
            TaskStatusEnum.PARTNER_REVIEW
        ]), 1))).label('under_review'),
        func.count(case((Task.status == TaskStatusEnum.COMPLETED, 1))).label('completed'),
    ).filter(
        Task.assigned_to_id == user_id,
        Task.deleted_at.is_(None)
    ).one()

    result = {
        'overdue_tasks_count': counts.overdue,
        'assigned_tasks_count': counts.assigned,
        'rejected_tasks_count': counts.rejected,
        'in_progress_tasks_count': counts.in_progress,
        'paused_tasks_count': counts.paused,
        'under_review_tasks_count': counts.under_review,
        'completed_tasks_count': counts.completed,
    }

    cache.set(cache_key, result, CACHE_TTL)
    return result

def _cache_key(user):
    """
    Generate a safe cache key based on role & user.
    """
    if user.role == "DIRECTOR":
        return "dashboard:review_tasks:director"

    if user.role == "SUPERVISOR":
        dept_ids = sorted(d.id for d in user.reviewing_departments)
        return f"dashboard:review_tasks:supervisor:{user.id}:{'-'.join(map(str, dept_ids))}"

    return f"dashboard:review_tasks:user:{user.id}"


def get_tasks_waiting_for_review_by_user(user):
    cache_key = _cache_key(user)
    cached = cache.get(cache_key)
    if cached:
        return cached

    base_query = (
        Task.query
        .filter(Task.status == TaskStatusEnum.REVIEW)
        .options(
            joinedload(Task.creator),
            joinedload(Task.job)
        )
    )

    # -------------------------
    # Director: sees all
    # -------------------------
    if user.role == "DIRECTOR":
        tasks = base_query.all()

    # -------------------------
    # Supervisor: dept-based
    # -------------------------
    elif user.role == "SUPERVISOR":
        visible_dept_ids = {d.id for d in user.reviewing_departments}
        if user.department_id:
            visible_dept_ids.add(user.department_id)

        tasks = (
            base_query
            .join(User, Task.created_by_id == User.id)
            .filter(User.department_id.in_(visible_dept_ids))
            .all()
        )

    # -------------------------
    # Officer / Intern / Others
    # -------------------------
    else:
        tasks = (
            base_query
            .filter(Task.created_by_id == user.id)
            .all()
        )

    cache.set(cache_key, tasks, CACHE_TTL)
    return tasks