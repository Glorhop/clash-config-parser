import time
import threading
import logging
import os
import redis as redis_lib

from .constants import CACHE_KEY_PREFIX

logger = logging.getLogger("clash-config-parser")

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))

REDIS_URL = os.getenv("REDIS_URL")
redis_client = None

if REDIS_URL:
    try:
        redis_client = redis_lib.Redis.from_url(
            REDIS_URL,
            socket_timeout=1,
            socket_connect_timeout=1,
            decode_responses=False,
        )
        redis_client.ping()
        logger.info("redis cache enabled url=%s", REDIS_URL)
    except redis_lib.RedisError as exc:
        redis_client = None
        logger.warning("redis cache disabled (error): %s", exc)
else:
    logger.info("redis cache disabled (no REDIS_URL provided)")

_response_cache = {}
_cache_lock = threading.Lock()


def _cache_key(source_url: str) -> str:
    return f"{CACHE_KEY_PREFIX}{source_url}"


def maybe_get_cached(source_url):
    if redis_client:
        try:
            hit = redis_client.get(_cache_key(source_url))
            if hit is not None:
                return hit.decode("utf-8")
        except redis_lib.RedisError as exc:
            logger.warning("redis cache get failed: %s", exc)

    key = source_url
    with _cache_lock:
        entry = _response_cache.get(key)
    if not entry:
        return None
    timestamp, payload = entry
    if (time.monotonic() - timestamp) > CACHE_TTL_SECONDS:
        with _cache_lock:
            _response_cache.pop(key, None)
        return None
    return payload


def cache_response(source_url, payload):
    if redis_client:
        try:
            redis_client.setex(_cache_key(source_url), CACHE_TTL_SECONDS, payload)
            return
        except redis_lib.RedisError as exc:
            logger.warning("redis cache set failed: %s", exc)

    with _cache_lock:
        _response_cache[source_url] = (time.monotonic(), payload)


def clear_cache():
    """Clear in-memory and redis caches for Clash configs."""
    with _cache_lock:
        _response_cache.clear()

    if redis_client:
        try:
            keys = list(redis_client.scan_iter(f"{CACHE_KEY_PREFIX}*"))
            if keys:
                redis_client.delete(*keys)
                logger.info("redis cache cleared count=%s", len(keys))
        except redis_lib.RedisError as exc:
            logger.warning("redis cache clear failed: %s", exc)
