from app.models import Service
from app.utils.cache import cache  
from app.utils.db import db  

CACHE_TTL = 300

def get_services_for_forms():
    """
    Fetch all active services for dropdowns
    """
    cache_key = "services:for_forms"
    cached = cache.get(cache_key)
    if cached:
        return cached

    services = Service.query.order_by(Service.name).all()

    cache.set(cache_key, services, timeout=CACHE_TTL)
    return services
