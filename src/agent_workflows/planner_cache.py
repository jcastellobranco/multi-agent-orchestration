"""Opt-in bounded in-process planner cache; scoped by tenant and policy version.

No shared Redis and no cross-worker coherence. Disabled by default.
Never cache agent execution results, tool side effects, credentials or raw prompts in keys.
"""
import copy
import hashlib
import hmac
import os
import threading
import time
from collections import OrderedDict

_LOCK = threading.Lock()
_ENTRIES = OrderedDict()
_MAX_ITEMS = 128

def _enabled():
    return os.getenv("ATLAS_PLANNER_CACHE_ENABLED", "false").lower() == "true"

def _key(tenant: str, prompt: str, model: str, policy: str) -> str:
    secret = os.getenv("ATLAS_CACHE_HMAC_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("ATLAS_CACHE_HMAC_KEY must be at least 32 characters")
    material = "\x00".join((tenant, model, policy, prompt)).encode("utf-8")
    return hmac.new(secret.encode(), material, hashlib.sha256).hexdigest()

def get(tenant: str, prompt: str, model: str, policy: str):
    if not _enabled():
        return None
    key = _key(tenant, prompt, model, policy)
    with _LOCK:
        entry = _ENTRIES.get(key)
        if entry is None:
            return None
        expires, value = entry
        if expires <= time.monotonic():
            del _ENTRIES[key]
            return None
        _ENTRIES.move_to_end(key)
        return copy.deepcopy(value)

def put(tenant: str, prompt: str, model: str, policy: str, value):
    if not _enabled():
        return
    key = _key(tenant, prompt, model, policy)
    ttl = int(os.getenv("ATLAS_PLANNER_CACHE_TTL_SECONDS", "120"))
    if not 1 <= ttl <= 3600:
        raise ValueError("Cache TTL must be 1..3600 seconds")
    with _LOCK:
        _ENTRIES[key] = (time.monotonic() + ttl, copy.deepcopy(value))
        _ENTRIES.move_to_end(key)
        while len(_ENTRIES) > _MAX_ITEMS:
            _ENTRIES.popitem(last=False)

def clear():
    with _LOCK:
        _ENTRIES.clear()
