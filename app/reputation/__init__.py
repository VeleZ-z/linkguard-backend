"""Paquete de reputación: claves canónicas, allowlist, blocklist y señales."""

from app.reputation.allowlist import ALLOWLIST_PATH, is_allowlisted, load_allowlist
from app.reputation.blocklist import (
    BLOCKLIST_HOSTS_PATH,
    BLOCKLIST_URLS_PATH,
    lookup_host,
    lookup_url,
)
from app.reputation.canonical import canonical_url_key
from app.reputation.loader import ReputationSignals, get_load_status, get_reputation
from app.reputation.store import store

__all__ = [
    "canonical_url_key",
    "store",
    "is_allowlisted",
    "ALLOWLIST_PATH",
    "load_allowlist",
    "lookup_url",
    "lookup_host",
    "BLOCKLIST_URLS_PATH",
    "BLOCKLIST_HOSTS_PATH",
    "ReputationSignals",
    "get_reputation",
    "get_load_status",
]
