from app.models import Job
from app.utils.cache import cache  
from app.utils.db import db  
from sqlalchemy.orm import selectinload

CACHE_TTL = 300

def get_jobs_for_forms():
    """
    Fetch jobs for dropdowns / task creation forms
    Includes services to avoid N+1 when accessing job.services
    """
    cache_key = "jobs:for_forms"
    cached = cache.get(cache_key)
    if cached:
        return cached

    jobs = (
        Job.query.options(selectinload(Job.services))
        .filter(
            Job.deleted_at.is_(None),
        )
        .order_by(Job.name)
        .all()
    )

    cache.set(cache_key, jobs, timeout=CACHE_TTL)
    return jobs
