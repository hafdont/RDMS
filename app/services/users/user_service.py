# app/services/user_service.py

from collections import defaultdict
from sqlalchemy import func, case
from sqlalchemy.sql import exists
from sqlalchemy.orm import joinedload, subqueryload
from app.utils.cache import cache  
from app.utils.db import db        
from app.models import (
    User, Task, TaskTemplate,
    RoleEnum, TaskStatusEnum
)

# Task statuses considered “active” for filtering
ACTIVE_STATUSES = (
    TaskStatusEnum.ASSIGNED,
    TaskStatusEnum.IN_PROGRESS,
    TaskStatusEnum.PAUSED,
    TaskStatusEnum.RE_ASSIGNED,
)

CACHE_TTL = 300  # cache results for 5 minutes


def _cache_key(filters: dict) -> str:
    """
    Generate a consistent cache key based on filter parameters.
    """
    parts = [
        f"{k}={filters[k]}"
        for k in sorted(filters)
        if filters.get(k) is not None
    ]
    return "users:list:" + "|".join(parts)


def get_users_with_stats(filters: dict):
    """
    Fetch users with precomputed task statistics:
    - assigned: total tasks assigned
    - completed: total tasks completed
    - review: tasks in review
    - redo: tasks re-assigned

    Returns a flat list of dicts:
    [
        {"user": User, "assigned": int, "completed": int, "review": int, "redo": int},
        ...
    ]
    """

    # ---------------------
    # Check cache first
    # ---------------------
    cache_key = _cache_key(filters)
    cached = cache.get(cache_key)
    if cached:
        return cached

    # ---------------------
    # Base user query
    # ---------------------
    user_query = User.query.join(User.department, isouter=True).filter(
        User.deleted_at.is_(None),
        ~User.department.has(name="Partners")  # Exclude Partners
    )

    # Search filter
    if filters.get("q"):
        search = f"%{filters['q']}%"
        user_query = user_query.filter(
            User.first_name.ilike(search) |
            User.middle_name.ilike(search) |
            User.last_name.ilike(search) |
            User.email.ilike(search) |
            User.phone_number.ilike(search)
        )

    # Department filter
    if filters.get("department_id"):
        user_query = user_query.filter(User.department_id == filters["department_id"])

    # Role filter
    if filters.get("role"):
        user_query = user_query.filter(User.role == RoleEnum[filters["role"]])

    # Client filter (active tasks)
    if filters.get("client_id"):
        user_query = user_query.filter(
            exists().where(
                Task.assigned_to_id == User.id,
                Task.client_id == filters["client_id"],
                Task.status.in_(ACTIVE_STATUSES),
            )
        )

    # Service filter (active tasks for service)
    if filters.get("service_id"):
        user_query = user_query.filter(
            exists().where(
                Task.assigned_to_id == User.id,
                Task.status.in_(ACTIVE_STATUSES),
            ).where(
                TaskTemplate.id == Task.task_template_id,
                TaskTemplate.service_id == filters["service_id"],
            )
        )

    # ---------------------
    # Fetch user IDs matching filters
    # ---------------------
    user_ids = [u.id for u in user_query.all()]
    if not user_ids:
        cache.set(cache_key, [], CACHE_TTL)
        return []

    # ---------------------
    # Aggregate task stats in SQL
    # ---------------------
    stats = (
        db.session.query(
            Task.assigned_to_id.label("user_id"),
            func.count(Task.id).label("assigned"),
            func.sum(case((Task.status == TaskStatusEnum.COMPLETED, 1), else_=0)).label("completed"),
            func.sum(case((Task.status == TaskStatusEnum.REVIEW, 1), else_=0)).label("review"),
            func.sum(case((Task.status == TaskStatusEnum.RE_ASSIGNED, 1), else_=0)).label("redo"),
        )
        .filter(Task.assigned_to_id.in_(user_ids))
        .group_by(Task.assigned_to_id)
        .all()
    )

    stats_map = {s.user_id: s for s in stats}

    # ---------------------
    # Fetch full user objects with department joined
    # ---------------------
    users = (
        User.query.options(joinedload(User.department))
        .filter(User.id.in_(user_ids))
        .order_by(User.first_name)
        .all()
    )

    # ---------------------
    # Combine user objects with stats
    # ---------------------
    result = []
    for user in users:
        s = stats_map.get(user.id)
        result.append({
            "user": user,
            "assigned": s.assigned if s else 0,
            "completed": s.completed if s else 0,
            "review": s.review if s else 0,
            "redo": s.redo if s else 0,
        })

    # ---------------------
    # Cache results
    # ---------------------
    cache.set(cache_key, result, CACHE_TTL)
    return result


def group_users_by_department(users_data):
    """
    Helper to group users by their department.
    Returns dict: {department_name: [user_data, ...], ...}
    """
    grouped = defaultdict(list)
    for row in users_data:
        dept_name = row["user"].department.name if row["user"].department else "No Department"
        grouped[dept_name].append(row)

    # Sort departments and users alphabetically
    grouped_sorted = {
        dept: sorted(users, key=lambda r: r["user"].first_name)
        for dept, users in sorted(grouped.items())
    }

    return grouped_sorted

def get_users_for_assignment():
    """
    Fetch users for assignment dropdown (lightweight, no stats)
    Excludes Partners department and deleted users
    Caches for 5 minutes
    """
    cache_key = "users:for_assignment"
    cached = cache.get(cache_key)
    if cached:
        return cached

    users = (
        User.query.options(joinedload(User.department))
        .filter(
            User.deleted_at.is_(None),
            ~User.department.has(name="Partners")  # exclude Partners
        )
        .order_by(User.first_name, User.last_name)
        .all()
    )

    cache.set(cache_key, users, timeout=300)
    return users


def get_user_by_email(email: str):
    return User.query.filter(User.email == email.lower()).first()

def get_user_for_dashboard(user_id: int):
    return (
        db.session.query(User)
        .options(subqueryload(User.reviewing_departments))
        .filter_by(id=user_id)
        .one()
    )
