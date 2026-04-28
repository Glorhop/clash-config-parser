import json
import os
import logging
import tempfile

from .paths import CONFIGS_FILE, DATA_DIR

logger = logging.getLogger("clash-config-parser")

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_default_configs() -> dict:
    raw = os.getenv("DEFAULT_CONFIGS_JSON", "").strip()
    if not raw:
        return {}
    try:
        configs = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("failed to parse DEFAULT_CONFIGS_JSON: %s", e)
        return {}
    if not isinstance(configs, dict):
        logger.warning("DEFAULT_CONFIGS_JSON must be a JSON object")
        return {}
    return configs


def load_configs() -> dict:
    """Load configs from configs.json. Seed from DEFAULT_CONFIGS_JSON if missing."""
    _ensure_data_dir()
    if not os.path.exists(CONFIGS_FILE):
        defaults = _load_default_configs()
        save_configs(defaults)
        return defaults
    try:
        with open(CONFIGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("failed to load configs.json: %s, using empty configs", e)
        return {}


def save_configs(configs: dict):
    """Atomic write configs to configs.json."""
    _ensure_data_dir()
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(configs, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CONFIGS_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_config(name: str) -> dict | None:
    configs = load_configs()
    return configs.get(name)


def upsert_config(name: str, entry: dict):
    configs = load_configs()
    configs[name] = entry
    save_configs(configs)


def delete_config(name: str) -> bool:
    configs = load_configs()
    if name not in configs:
        return False
    del configs[name]
    save_configs(configs)
    return True
