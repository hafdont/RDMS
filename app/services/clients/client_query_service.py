from app.models import Client
from app.utils.cache import cache  
from app.utils.db import db  

CACHE_TTL = 300  # 5 minutes

def get_clients_for_forms():
    """
    Fetch active clients for dropdowns / forms
    Excludes soft-deleted clients
    """
    cache_key = "clients:for_forms"
    cached = cache.get(cache_key)
    if cached:
        return cached

    clients = (
        Client.query
        .filter(Client.deleted_at.is_(None))
        .order_by(Client.name)
        .all()
    )

    cache.set(cache_key, clients, timeout=CACHE_TTL)
    return clients


def search_clients_by_name(query: str, limit: int = 10):
    """
    Fast search for clients by name.
    Returns a list of dicts: [{"id": id, "name": name}, ...]
    """
    if not query or len(query.strip()) < 2:
        return []

    query_str = query.strip()
    
    # Use startswith search for index efficiency
    matched_clients = (
        Client.query
        .filter(Client.name.ilike(f"{query_str}%"))  # or "%query%" if really needed
        .order_by(Client.name.asc())
        .limit(limit)
        .all()
    )

    return [{"id": c.id, "name": c.name} for c in matched_clients]
