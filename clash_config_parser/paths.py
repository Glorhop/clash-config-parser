from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
CONFIGS_FILE = DATA_DIR / "configs.json"

CONFIG_DIR = PROJECT_ROOT / "config"
RULES_FILE = CONFIG_DIR / "rules.txt"

DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
