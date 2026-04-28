import os
import time
import threading
import logging

from .constants import DEFAULT_REQUIRED_RULES, REQUIRED_RULES_FILE
from .cache import clear_cache

logger = logging.getLogger("clash-config-parser")

RULES_SCAN_INTERVAL = int(os.getenv("RULES_SCAN_INTERVAL", "15"))

_rules_lock = threading.Lock()
_required_rules = list(DEFAULT_REQUIRED_RULES)
_rules_file_mtime = None


def load_rules():
    """Return required rules from cached state."""
    with _rules_lock:
        return list(_required_rules)


def reload_rules():
    """Load rules.txt once and refresh cache when it changes."""
    global _required_rules, _rules_file_mtime

    new_rules = list(DEFAULT_REQUIRED_RULES)
    new_mtime = None

    if REQUIRED_RULES_FILE:
        try:
            stat = os.stat(REQUIRED_RULES_FILE)
            new_mtime = stat.st_mtime
            with open(REQUIRED_RULES_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines()]
            parsed = [line for line in lines if line and not line.startswith("#")]
            if parsed:
                new_rules = parsed
            else:
                logger.warning(
                    "REQUIRED_RULES_FILE=%s empty or only comments, falling back to defaults",
                    REQUIRED_RULES_FILE,
                )
        except OSError as exc:
            logger.warning("failed to read REQUIRED_RULES_FILE=%s: %s", REQUIRED_RULES_FILE, exc)

    with _rules_lock:
        _required_rules = new_rules
        _rules_file_mtime = new_mtime

    logger.info("required rules loaded count=%s source=%s", len(new_rules), REQUIRED_RULES_FILE or "default")


def _watch_rules():
    """Poll for rules file changes and clear caches when it updates."""
    if not REQUIRED_RULES_FILE:
        logger.info("rules watcher disabled: no REQUIRED_RULES_FILE configured")
        return

    while True:
        try:
            mtime = os.stat(REQUIRED_RULES_FILE).st_mtime
        except OSError:
            mtime = None

        with _rules_lock:
            last_mtime = _rules_file_mtime

        if mtime != last_mtime:
            logger.info("rules change detected; reloading and clearing cached configs")
            reload_rules()
            clear_cache()

        time.sleep(RULES_SCAN_INTERVAL)


def save_rules(content: str):
    """Write rules content to rules.txt."""
    os.makedirs(os.path.dirname(REQUIRED_RULES_FILE), exist_ok=True)
    with open(REQUIRED_RULES_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    reload_rules()
    clear_cache()


def get_rules_text() -> str:
    """Read raw rules.txt content."""
    try:
        with open(REQUIRED_RULES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def start_rules_watcher():
    reload_rules()
    threading.Thread(target=_watch_rules, daemon=True, name="rules-watcher").start()
