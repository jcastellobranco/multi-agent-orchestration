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
import json
from collections import OrderedDict

def _redis_connection():
    import redis
    host = os.getenv("ATLAS_REDIS_HOST", "")
    secret_file = os.getenv("ATLAS_REDIS_PASSWORD_FILE", "")
    if host and secret_file:
        with open(secret_file, encoding="utf-8") as handle:
            password = handle.read().strip()
        if len(password) < 32:
            raise ValueError("Redis secret must be at least 32 characters")
        return redis.Redis(host=host, port=6379, db=0, password=password,
                           socket_connect_timeout=1, socket_timeout=1)
    url = os.getenv("ATLAS_REDIS_URL", "")
    return redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)

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
    redis_url = os.getenv("ATLAS_REDIS_URL", "") or os.getenv("ATLAS_REDIS_HOST", "")
    if redis_url:
        import redis
        try:
            value = _redis_connection().get("atlas:planner:" + key)
            return json.loads(value) if value is not None else None
        except (redis.RedisError, OSError, ValueError):
            # Never fall back to an unscoped shared cache on Redis errors.
            return None
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
    redis_url = os.getenv("ATLAS_REDIS_URL", "")
    if redis_url:
        import redis
        try:
            redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1).setex(
                "atlas:planner:" + key, ttl, json.dumps(value))
        except redis.RedisError:
            pass  # Cache is optional; never fail the actual planner.
        return
    with _LOCK:
        _ENTRIES[key] = (time.monotonic() + ttl, copy.deepcopy(value))
        _ENTRIES.move_to_end(key)
        while len(_ENTRIES) > _MAX_ITEMS:
            _ENTRIES.popitem(last=False)

def clear():
    with _LOCK:
        _ENTRIES.clear()
