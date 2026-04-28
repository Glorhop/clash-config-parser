# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flask service that transforms remote Clash proxy configurations by filtering proxies, adjusting proxy groups, and injecting TUN/DNS settings. Uses Redis for optional caching.

## Common Commands

```bash
# Local development
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m clash_config_parser.app                # Dev server on port 5000
gunicorn -w 4 -b 0.0.0.0:8200 clash_config_parser.app:app

# Docker
docker compose up --build                        # App + Redis stack

```

## API Endpoints

- `GET /convert?url=<source>&tun=true|false` - Fetches, transforms, and returns processed YAML
- `GET /downloads/<filename>` - Public hosted data/package download
- `GET /downloads/mihomo/<amd64|arm64>` - Public mihomo package download by architecture
- `GET /install/mihomo.sh` - Public installer that detects client architecture
- `GET /health` - Health check (returns 200 OK)

## Architecture

**app.py** - Main Flask application with all business logic:
- `_clean_proxies()` - Filters proxies by UUID, keywords (Chinese spam), and multiplier patterns (2x, 4x, etc.)
- `_process_groups()` - Removes references to deleted proxies, converts specific groups to url-test type
- `_inject_tun()` - Adds TUN/DNS configuration at top of config when enabled
- `_enforce_rules()` - Prepends required routing rules (loaded from `config/rules.txt` or defaults)
- Background thread watches `config/rules.txt` for changes and clears caches

## Key Configuration

| Environment Variable | Default | Purpose |
|---------------------|---------|---------|
| `REDIS_URL` | (none) | Enables Redis caching when set |
| `CACHE_TTL_SECONDS` | 300 | Cache TTL for fetched configs |
| `RULES_SCAN_INTERVAL` | 15 | Seconds between config/rules.txt polls |

**config/rules.txt** - Custom routing rules (one per line, comments start with `#`). File changes trigger automatic cache invalidation.

**downloads/** - Publicly hosted files (`geosite.dat`, `Country.mmdb`, mihomo packages). Docker Compose mounts this path into `/app/downloads`.

Sensitive subscription URLs and node credentials must not be committed. Runtime config lives in ignored `data/configs.json`; optional startup seeding uses `DEFAULT_CONFIGS_JSON`, and VIP node injection uses `VIP_NODE_JSON`.

## Code Conventions

- Uses `ruamel.yaml` with `CommentedMap` to preserve YAML formatting/ordering - don't switch parsers
- Constants in `UPPER_SNAKE_CASE` at module top (blocking rules, latency groups, TUN config)
- Helper functions prefixed with `_` for internal use
- Structured logging via `logging` module (not print) in the web app
