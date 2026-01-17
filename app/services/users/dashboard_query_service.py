from datetime import datetime, date, time
from sqlalchemy import func, distinct
from app.utils.cache import cache
from app.models import User, Service, Client, Job, Task, TaskStatusEnum
from app.utils.db import db

CACHE_TTL = 120

def get_director_dashboard_stats():
    cache_key = "dashboard:director:stats"
    cached = cache.get(cache_key)
    if cached:
        return cached

    users_count, services_count, clients_count = db.session.query(
        func.count(distinct(User.id)),
        func.count(distinct(Service.id)),
        func.count(distinct(Client.id))
    ).one()

    ongoing_statuses = [
        TaskStatusEnum.ASSIGNED,
        TaskStatusEnum.IN_PROGRESS,
        TaskStatusEnum.PAUSED,
        TaskStatusEnum.REVIEW,
        TaskStatusEnum.MANAGER_REVIEW,
        TaskStatusEnum.PARTNER_REVIEW,
    ]

    engagements_count = (
        db.session.query(func.count(distinct(Job.id)))
        .join(Job.tasks)
        .filter(func.date(Job.created_at) == date.today())
        .filter(Task.status.in_(ongoing_statuses))
        .scalar()
    )

    today = datetime.utcnow().date()
    actionable_tasks_count = Task.query.filter(
        Task.status.in_([
            TaskStatusEnum.REVIEW,
            TaskStatusEnum.MANAGER_REVIEW,
            TaskStatusEnum.PARTNER_REVIEW
        ]),
        Task.updated_at >= datetime.combine(today, time.min),
        Task.updated_at <= datetime.combine(today, time.max)
    ).count()

    result = {
        "users_count": users_count,
        "services_count": services_count,
        "clients_count": clients_count,
        "engagements_count": engagements_count,
        "actionable_tasks_count": actionable_tasks_count,
    }

    cache.set(cache_key, result, CACHE_TTL)
    return result
