import base64
import json
import logging
from urllib.parse import urlparse, parse_qs, unquote

from ruamel.yaml.comments import CommentedMap, CommentedSeq

logger = logging.getLogger("clash-config-parser")


def _decode_base64_content(content: str) -> str:
    """Decode base64 content, handling padding issues."""
    content = content.strip()
    padding = 4 - len(content) % 4
    if padding != 4:
        content += '=' * padding
    try:
        return base64.b64decode(content).decode('utf-8')
    except Exception:
        return base64.urlsafe_b64decode(content).decode('utf-8')


def _parse_hysteria2(url: str) -> dict:
    """Parse hysteria2:// URL to Clash proxy config."""
    parsed = urlparse(url)
    fragment = unquote(parsed.fragment) if parsed.fragment else ""
    query = parse_qs(parsed.query)

    proxy = {
        "name": fragment or f"hysteria2-{parsed.hostname}",
        "type": "hysteria2",
        "server": parsed.hostname,
        "port": parsed.port or 443,
        "password": parsed.username or "",
    }

    if query.get("sni"):
        proxy["sni"] = query["sni"][0]
    if query.get("insecure") and query["insecure"][0] == "1":
        proxy["skip-cert-verify"] = True
    if query.get("obfs"):
        proxy["obfs"] = query["obfs"][0]
    if query.get("obfs-password"):
        proxy["obfs-password"] = query["obfs-password"][0]

    return proxy


def _parse_vmess(url: str) -> dict:
    """Parse vmess:// URL to Clash proxy config."""
    content = url.replace("vmess://", "")
    try:
        decoded = _decode_base64_content(content)
        data = json.loads(decoded)
    except Exception as e:
        logger.warning("failed to parse vmess URL: %s", e)
        return None

    proxy = {
        "name": data.get("ps", f"vmess-{data.get('add', 'unknown')}"),
        "type": "vmess",
        "server": data.get("add", ""),
        "port": int(data.get("port", 443)),
        "uuid": data.get("id", ""),
        "alterId": int(data.get("aid", 0)),
        "cipher": data.get("scy", "auto"),
    }

    net = data.get("net", "tcp")
    if net == "ws":
        proxy["network"] = "ws"
        proxy["ws-opts"] = {}
        if data.get("path"):
            proxy["ws-opts"]["path"] = data["path"]
        if data.get("host"):
            proxy["ws-opts"]["headers"] = {"Host": data["host"]}
    elif net == "grpc":
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {}
        if data.get("path"):
            proxy["grpc-opts"]["grpc-service-name"] = data["path"]
    elif net == "h2":
        proxy["network"] = "h2"
        proxy["h2-opts"] = {}
        if data.get("path"):
            proxy["h2-opts"]["path"] = data["path"]
        if data.get("host"):
            proxy["h2-opts"]["host"] = [data["host"]]

    if data.get("tls") == "tls":
        proxy["tls"] = True
        if data.get("sni"):
            proxy["servername"] = data["sni"]
        if data.get("fp"):
            proxy["client-fingerprint"] = data["fp"]

    if data.get("skip-cert-verify"):
        proxy["skip-cert-verify"] = True

    return proxy


def _parse_vless(url: str) -> dict:
    """Parse vless:// URL to Clash proxy config."""
    parsed = urlparse(url)
    fragment = unquote(parsed.fragment) if parsed.fragment else ""
    query = parse_qs(parsed.query)

    proxy = {
        "name": fragment or f"vless-{parsed.hostname}",
        "type": "vless",
        "server": parsed.hostname,
        "port": parsed.port or 443,
        "uuid": parsed.username or "",
    }

    security = query.get("security", ["none"])[0]
    if security == "reality":
        proxy["tls"] = True
        proxy["network"] = "tcp"
        if query.get("sni"):
            proxy["servername"] = query["sni"][0]
        if query.get("fp"):
            proxy["client-fingerprint"] = query["fp"][0]
        pbk = query.get("pbk", [""])[0]
        sid = query.get("sid", [""])[0]
        if pbk:
            proxy["reality-opts"] = {"public-key": pbk}
            if sid:
                proxy["reality-opts"]["short-id"] = sid
    elif security == "tls":
        proxy["tls"] = True
        if query.get("sni"):
            proxy["servername"] = query["sni"][0]
        if query.get("fp"):
            proxy["client-fingerprint"] = query["fp"][0]

    flow = query.get("flow", [""])[0]
    if flow:
        proxy["flow"] = flow

    net = query.get("type", ["tcp"])[0]
    if net == "ws":
        proxy["network"] = "ws"
        proxy["ws-opts"] = {}
        if query.get("path"):
            proxy["ws-opts"]["path"] = query["path"][0]
        if query.get("host"):
            proxy["ws-opts"]["headers"] = {"Host": query["host"][0]}
    elif net == "grpc":
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {}
        if query.get("serviceName"):
            proxy["grpc-opts"]["grpc-service-name"] = query["serviceName"][0]

    return proxy


def _parse_trojan(url: str) -> dict:
    """Parse trojan:// URL to Clash proxy config."""
    parsed = urlparse(url)
    fragment = unquote(parsed.fragment) if parsed.fragment else ""
    query = parse_qs(parsed.query)

    proxy = {
        "name": fragment or f"trojan-{parsed.hostname}",
        "type": "trojan",
        "server": parsed.hostname,
        "port": parsed.port or 443,
        "password": parsed.username or "",
    }

    if query.get("sni"):
        proxy["sni"] = query["sni"][0]
    if query.get("allowInsecure") and query["allowInsecure"][0] == "1":
        proxy["skip-cert-verify"] = True
    if query.get("fp"):
        proxy["client-fingerprint"] = query["fp"][0]

    net = query.get("type", ["tcp"])[0]
    if net == "ws":
        proxy["network"] = "ws"
        proxy["ws-opts"] = {}
        if query.get("path"):
            proxy["ws-opts"]["path"] = query["path"][0]
        if query.get("host"):
            proxy["ws-opts"]["headers"] = {"Host": query["host"][0]}
    elif net == "grpc":
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {}
        if query.get("serviceName"):
            proxy["grpc-opts"]["grpc-service-name"] = query["serviceName"][0]

    return proxy


import re

def _parse_ss(url: str) -> dict:
    """Parse ss:// (Shadowsocks) URL to Clash proxy config."""
    parsed = urlparse(url)
    fragment = unquote(parsed.fragment) if parsed.fragment else ""

    if parsed.username:
        try:
            decoded = _decode_base64_content(unquote(parsed.username))
            if ':' in decoded:
                method, password = decoded.split(':', 1)
            else:
                method = "aes-256-gcm"
                password = decoded
        except Exception:
            method = "aes-256-gcm"
            password = parsed.username
        server = parsed.hostname
        port = parsed.port
    else:
        content = url.replace("ss://", "").split("#")[0]
        try:
            decoded = _decode_base64_content(content)
            match = re.match(r'([^:]+):([^@]+)@([^:]+):(\d+)', decoded)
            if match:
                method, password, server, port = match.groups()
                port = int(port)
            else:
                return None
        except Exception as e:
            logger.warning("failed to parse ss URL: %s", e)
            return None

    proxy = {
        "name": fragment or f"ss-{server}",
        "type": "ss",
        "server": server,
        "port": port,
        "cipher": method,
        "password": password,
    }

    return proxy


def _parse_subscription_links(content: str) -> list:
    """Parse base64 encoded subscription content into proxy list."""
    try:
        decoded = _decode_base64_content(content)
    except Exception as e:
        logger.warning("failed to decode base64 content: %s", e)
        return []

    proxies = []
    lines = decoded.strip().split('\n')

    for line in lines:
        line = line.strip().replace('\r', '')
        if not line:
            continue

        proxy = None
        try:
            if line.startswith("hysteria2://") or line.startswith("hy2://"):
                proxy = _parse_hysteria2(line)
            elif line.startswith("vmess://"):
                proxy = _parse_vmess(line)
            elif line.startswith("vless://"):
                proxy = _parse_vless(line)
            elif line.startswith("trojan://"):
                proxy = _parse_trojan(line)
            elif line.startswith("ss://"):
                proxy = _parse_ss(line)
            else:
                logger.debug("unsupported protocol: %s", line[:30])
        except Exception as e:
            logger.warning("failed to parse line: %s, error: %s", line[:50], e)

        if proxy:
            proxies.append(proxy)

    return proxies
