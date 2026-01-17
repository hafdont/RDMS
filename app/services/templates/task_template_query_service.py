from app.models import TaskTemplate
from app.utils.cache import cache  
from app.utils.db import db  

CACHE_TTL = 300

def get_templates_for_forms():
    """
    Fetch all task templates
    Cached for forms like task creation, job creation
    """
    cache_key = "task_templates:for_forms"
    cached = cache.get(cache_key)
    if cached:
        return cached

    templates = TaskTemplate.query.options(
        db.joinedload(TaskTemplate.service)  # load related service to avoid N+1
    ).all()

    cache.set(cache_key, templates, timeout=CACHE_TTL)
    return templates
