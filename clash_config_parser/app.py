import os
import sys
import logging
from io import StringIO
from urllib.parse import urlparse

import requests as http_requests
from flask import Flask, request, Response, session, redirect, url_for, jsonify, render_template, send_from_directory, abort
from werkzeug.exceptions import RequestEntityTooLarge
from ruamel.yaml import YAML

from .constants import REQUEST_TIMEOUT, REGION_FILTER_OPTIONS
from .parsers import _parse_subscription_links
from .converter import (
    force_block_style, clean_proxies, process_groups,
    inject_tun, enforce_rules, apply_load_balance_group,
    inject_load_balance_rules, inject_vip_and_ai_rules,
    build_clash_config, _ensure_commented_map,
)
from .config_store import load_configs, upsert_config, delete_config
from .rules_store import start_rules_watcher, get_rules_text, save_rules
from .cache import maybe_get_cached, cache_response, clear_cache
from .auth import login_required, ADMIN_PASSWORD
from .download_assets import (
    MIHOMO_FILES,
    build_installer_script,
    download_file_path,
    list_download_entries,
    list_script_entries,
    normalize_arch,
    save_download_file,
)
from .paths import DOWNLOADS_DIR
from .region_filter import normalize_region_filter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("clash-config-parser")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(32).hex())
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("HOSTED_FILE_MAX_MB", "256")) * 1024 * 1024

yaml = YAML()
yaml.preserve_quotes = False
yaml.default_flow_style = False

http_session = http_requests.Session()


def _fetch_config_text(source_url: str):
    headers = {
        'User-Agent': 'clash-meta/1.18.0',
        'Accept': '*/*',
    }
    resp = http_session.get(source_url, timeout=REQUEST_TIMEOUT, headers=headers)
    resp.raise_for_status()
    return resp.text


def _sanitize_config_entry(entry: dict) -> dict:
    normalized_filter = normalize_region_filter(entry)
    entry["region_filter_mode"] = normalized_filter["mode"]
    entry["region_filter_regions"] = normalized_filter["regions"]
    return entry


def _region_filter_for_request(config_entry: dict) -> dict:
    region_mode = request.args.get("region_mode")
    regions = request.args.get("regions")
    if region_mode is None and regions is None:
        return config_entry

    override = dict(config_entry)
    if region_mode is not None:
        override["region_filter_mode"] = region_mode
    if regions is not None:
        override["region_filter_regions"] = regions
    return override


# ==========================================
# Auth routes
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if not ADMIN_PASSWORD:
        session['authenticated'] = True
        return redirect(url_for('index'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='密码错误')
    return render_template('login.html', error=None)


@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login_page'))


# ==========================================
# Web UI
# ==========================================

@app.route('/')
@login_required
def index():
    return render_template('index.html')


# ==========================================
# Config management API
# ==========================================

@app.route('/api/configs', methods=['GET'])
@login_required
def api_list_configs():
    return jsonify(load_configs())


@app.route('/api/region-options', methods=['GET'])
@login_required
def api_region_options():
    return jsonify([
        {"key": option["key"], "label": option["label"]}
        for option in REGION_FILTER_OPTIONS
    ])


@app.route('/api/configs', methods=['POST'])
@login_required
def api_add_config():
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    entry = {k: v for k, v in data.items() if k != 'name'}
    if 'url' not in entry:
        return jsonify({"error": "url is required"}), 400
    entry = _sanitize_config_entry(entry)
    upsert_config(name, entry)
    return jsonify({"ok": True})


@app.route('/api/configs/<name>', methods=['PUT'])
@login_required
def api_update_config(name):
    data = request.get_json(force=True)
    new_name = data.get('new_name', '').strip()
    entry = {k: v for k, v in data.items() if k not in ('name', 'new_name')}
    if 'url' not in entry:
        return jsonify({"error": "url is required"}), 400
    entry = _sanitize_config_entry(entry)
    if new_name and new_name != name:
        delete_config(name)
        upsert_config(new_name, entry)
    else:
        upsert_config(name, entry)
    return jsonify({"ok": True})


@app.route('/api/configs/<name>', methods=['DELETE'])
@login_required
def api_delete_config(name):
    if delete_config(name):
        return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


# ==========================================
# Rules management API
# ==========================================

@app.route('/api/rules', methods=['GET'])
@login_required
def api_get_rules():
    return jsonify({"content": get_rules_text()})


@app.route('/api/rules', methods=['PUT'])
@login_required
def api_save_rules():
    data = request.get_json(force=True)
    content = data.get('content', '')
    save_rules(content)
    return jsonify({"ok": True})


@app.route('/api/clear-cache', methods=['POST'])
@login_required
def api_clear_cache():
    clear_cache()
    return jsonify({"ok": True})


# ==========================================
# File hosting
# ==========================================

@app.route('/api/downloads', methods=['GET'])
@login_required
def api_downloads():
    return jsonify({
        "files": list_download_entries(),
        "scripts": list_script_entries(),
    })


@app.route('/api/downloads/<path:filename>', methods=['POST'])
@login_required
def api_update_download(filename):
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "file is required"}), 400
    try:
        info = save_download_file(filename, uploaded)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except OSError as exc:
        logger.exception("failed to update hosted file filename=%s", filename)
        return jsonify({"error": str(exc)}), 500
    if info is None:
        return jsonify({"error": "unsupported hosted file"}), 404
    logger.info("hosted file updated filename=%s size=%s", filename, info["size"])
    return jsonify({"ok": True, "file": {"filename": filename, **info}})


@app.route('/downloads/mihomo/<arch>')
def download_mihomo_arch(arch):
    normalized_arch = normalize_arch(arch)
    if normalized_arch not in MIHOMO_FILES:
        abort(404)
    filename = MIHOMO_FILES[normalized_arch]["filename"]
    if not download_file_path(filename):
        abort(404)
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)


@app.route('/downloads/<path:filename>')
def download_hosted_file(filename):
    if not download_file_path(filename):
        abort(404)
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)


@app.route('/install/mihomo.sh')
def install_mihomo_auto():
    return _installer_response()


@app.route('/install/mihomo-amd64.sh')
def install_mihomo_amd64():
    return _installer_response("amd64")


@app.route('/install/mihomo-arm64.sh')
def install_mihomo_arm64():
    return _installer_response("arm64")


def _installer_response(arch=None):
    script = build_installer_script(request.url_root, arch)
    return Response(script, content_type='text/x-shellscript; charset=utf-8')


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(exc):
    limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify({"error": f"file is too large; max {limit_mb} MB"}), 413


# ==========================================
# Core convert endpoint (no auth)
# ==========================================

@app.route('/convert')
def convert():
    config_name = request.args.get('config')
    enable_tun = request.args.get('tun', 'false').lower() in ['true', '1', 'yes']
    load_balance_param = request.args.get('load_balance')

    configs = load_configs()
    config_entry = configs.get(config_name or "")
    default_load_balance = bool(config_entry.get("default_load_balance")) if config_entry else False
    if load_balance_param is None:
        enable_load_balance = default_load_balance
    else:
        enable_load_balance = load_balance_param.lower() in ['true', '1', 'yes']
    region_filter = _region_filter_for_request(config_entry or {})
    normalized_region_filter = normalize_region_filter(region_filter)
    logger.info(
        "convert request config=%s tun=%s load_balance=%s region_filter=%s",
        config_name,
        enable_tun,
        enable_load_balance,
        normalized_region_filter,
    )

    if not config_name:
        return Response("Missing 'config' parameter", status=400, mimetype='text/plain')

    if not config_entry:
        return Response("Unknown 'config' parameter", status=400, mimetype='text/plain')

    source_url = config_entry["url"]
    config_type = config_entry.get("type", "yaml")
    parsed = urlparse(source_url)
    cached = maybe_get_cached(source_url)
    if cached is not None:
        logger.info("cache hit host=%s", parsed.netloc or "unknown")
        raw_text = cached
    else:
        try:
            raw_text = _fetch_config_text(source_url)
            cache_response(source_url, raw_text)
            logger.info("cache store host=%s", parsed.netloc or "unknown")
        except http_requests.RequestException as e:
            return Response(f"Fetch Error: {str(e)}", status=500, mimetype='text/plain')
        except Exception as e:
            return Response(f"Parse Error: {str(e)}", status=500, mimetype='text/plain')

    try:
        if config_type == "base64":
            proxies = _parse_subscription_links(raw_text)
            if not proxies:
                return Response("No valid proxies found in subscription", status=400, mimetype='text/plain')
            logger.info("parsed base64 subscription proxy_count=%d", len(proxies))
            config = build_clash_config(proxies)
        else:
            config = _ensure_commented_map(yaml.load(raw_text))
    except Exception as e:
        return Response(f"YAML Parse Error: {str(e)}", status=500, mimetype='text/plain')

    removed_names = clean_proxies(config, normalized_region_filter)
    process_groups(config, removed_names)
    inject_tun(config, enable_tun)

    if enable_load_balance:
        apply_load_balance_group(config, config_name)

    enable_vip = config_entry.get("enable_vip", True)
    if enable_vip:
        inject_vip_and_ai_rules(config)

    skip_rules_file = config_entry.get("skip_rules_file", False)
    enforce_rules(config, use_minimal=skip_rules_file)

    if enable_load_balance:
        inject_load_balance_rules(config)

    force_block_style(config)
    stream = StringIO()
    yaml.dump(config, stream)

    rendered = stream.getvalue()
    return Response(rendered, mimetype='text/yaml; charset=utf-8')


@app.route('/health')
def health():
    return Response('OK', status=200, mimetype='text/plain')


# Start background tasks
start_rules_watcher()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
