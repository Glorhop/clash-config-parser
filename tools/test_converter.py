#!/usr/bin/env python3
"""
Test script to verify the Clash config conversion logic
"""

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
import json
import os
import re
from io import StringIO

# Predefined removal rules
BLOCK_UUIDS = ["6c50c1b6-aa0d-3648-85ae-e5f6b9f7be1d"]
BLOCK_KEYWORDS = [
    "最新网址",
    "foosber.com",
    "节点变化频繁",
    "双旦优惠",
    "认准官网地址",
    "专属五折",
    "已推送邮箱",
    "如果现在只能看到少数线路",
    "立即更新教程推荐最新软件",
]
MULTIPLIER_REGEX = re.compile(r'\b(10|[245])x\b', re.IGNORECASE)
LATENCY_GROUPS = {"🔰 国外流量", "💬 OpenAi"}
REQUIRED_RULES = [
    "DOMAIN-SUFFIX,1008761.xyz,DIRECT",
    "DOMAIN-SUFFIX,docker.io,{proxy_group}"
]
LATENCY_TEST_SETTINGS = {
    "type": "url-test",
    "url": "http://www.gstatic.com/generate_204",
    "interval": 30,
    "tolerance": 10
}

# VIP 节点与 AI 专属分流规则
VIP_GROUP = "💎 AI 专线"

def _load_json_env(name: str, fallback):
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


VIP_NODE = _load_json_env("VIP_NODE_JSON", {})

AI_RULES = [
    f"DOMAIN-SUFFIX,anthropic.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,claude.ai,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,claudeusercontent.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,openai.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,api.openai.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,chatgpt.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,gemini.google.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,generativelanguage.googleapis.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,ai.google.dev,{VIP_GROUP}"
]

TUN_CONFIG = {
    "allow-lan": True,
    "bind-address": "*",
    "tproxy-port": 7893,
    "dns": {
        "enable": True,
        "ipv6": False,
        "listen": "0.0.0.0:5353",
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "fake-ip-filter": ["+.lan", "+.local"],
        "nameserver": ["223.5.5.5", "8.8.8.8"]
    },
    "tun": {
        "enable": False,
        "stack": "gvisor",
        "dns-hijack": ["any:53"],
        "auto-route": True,
        "auto-detect-interface": True
    }
}

def _ensure_commented_map(value):
    if isinstance(value, CommentedMap):
        return value
    if isinstance(value, dict):
        cm = CommentedMap()
        for k, v in value.items():
            cm[k] = _ensure_commented_map(v)
        return cm
    if isinstance(value, list):
        return [_ensure_commented_map(v) for v in value]
    return value


def _inject_vip_and_ai_rules(config):
    """注入 VIP 节点、策略组和 AI 分流规则。"""
    if not isinstance(VIP_NODE, dict) or not VIP_NODE.get("name"):
        print("\n[SKIPPED] VIP node injection: VIP_NODE_JSON is not configured")
        return

    if 'proxies' not in config or config['proxies'] is None:
        config['proxies'] = []

    if not any(p.get('name') == VIP_NODE['name'] for p in config['proxies']):
        config['proxies'].insert(0, _ensure_commented_map(VIP_NODE))

    if 'proxy-groups' not in config or config['proxy-groups'] is None:
        config['proxy-groups'] = []

    airport_names = [p.get('name') for p in config['proxies'] if p.get('name') != VIP_NODE['name']]
    auto_candidates = [
        g.get('name') for g in config['proxy-groups']
        if isinstance(g, dict) and '自动选择' in str(g.get('name', ''))
    ]
    auto_group = auto_candidates[0] if auto_candidates else None

    fallback_proxies = [auto_group] if auto_group else []
    fallback_proxies.extend(airport_names[:3])
    fallback_proxies = [p for i, p in enumerate(fallback_proxies) if p and p not in fallback_proxies[:i]]

    vip_group = _ensure_commented_map({
        "name": VIP_GROUP,
        "type": "select",
        "proxies": [VIP_NODE['name']] + fallback_proxies
    })

    if not any(g.get('name') == vip_group['name'] for g in config['proxy-groups']):
        config['proxy-groups'].insert(0, vip_group)

    if 'rules' not in config or config['rules'] is None:
        config['rules'] = []

    for rule in reversed(AI_RULES):
        if rule not in config['rules']:
            config['rules'].insert(0, rule)


def _pick_default_proxy_group(config):
    """选择一个存在的主策略组，用于兜底规则目标。"""
    groups = config.get('proxy-groups') or []
    names = [g.get('name') for g in groups if isinstance(g, dict) and g.get('name')]
    preferred = ["🔰 国外流量", "🚀 节点选择", "一分机场", "PROXY", "Proxy"]
    for name in preferred:
        if name in names:
            return name
    return names[0] if names else "DIRECT"

def convert_config(input_file, output_file, enable_tun=False):
    """Convert Clash config with filtering and TUN support"""

    # Configure YAML instance to preserve formatting
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    # Load config
    with open(input_file, 'r', encoding='utf-8') as f:
        config = _ensure_commented_map(yaml.load(f))

    # Statistics
    original_proxy_count = len(config.get('proxies', []))

    # Clean Proxies
    valid_proxies = []
    removed_names = set()

    if 'proxies' in config and config['proxies']:
        for p in config['proxies']:
            name = p.get('name', '')
            uuid = p.get('uuid', '')

            # Determine if should be removed
            # Avoid wiping whole lists when a provider reuses the same UUID; require another bad signal.
            is_blocked_uuid = uuid in BLOCK_UUIDS
            is_blocked_keyword = any(keyword in name for keyword in BLOCK_KEYWORDS)
            is_high_rate = bool(MULTIPLIER_REGEX.search(name))

            should_remove = is_blocked_keyword or is_high_rate or (is_blocked_uuid and (is_blocked_keyword or is_high_rate))

            if should_remove:
                removed_names.add(name)
                print(f"[REMOVED] {name}")
                if is_blocked_uuid:
                    print(f"  Reason: Blocked UUID ({uuid})")
                if is_blocked_keyword:
                    print(f"  Reason: Blocked keyword")
                if is_high_rate:
                    print(f"  Reason: High rate multiplier")
            else:
                valid_proxies.append(p)

        config['proxies'] = valid_proxies

    # Process Proxy Groups
    groups_modified = []
    if 'proxy-groups' in config and config['proxy-groups']:
        for group in config['proxy-groups']:
            group_name = group.get('name', 'Unknown')

            # Remove references to deleted proxies
            if 'proxies' in group and group['proxies']:
                original_count = len(group['proxies'])
                group['proxies'] = [n for n in group['proxies'] if n not in removed_names]
                new_count = len(group['proxies'])

                if original_count != new_count:
                    removed_count = original_count - new_count
                    groups_modified.append(f"{group_name}: removed {removed_count} proxy references")

            # Convert specific groups to url-test
            if group.get('name') in LATENCY_GROUPS:
                old_type = group.get('type', 'unknown')
                group.update(LATENCY_TEST_SETTINGS)
                print(f"\n[CONVERTED] Group '{group.get('name')}' : {old_type} -> url-test")

        # Prefer direct for fallback traffic
        for group in config['proxy-groups']:
            if group.get('name') == '⚓️ 其他流量' and group.get('proxies'):
                original = list(group['proxies'])
                unique = []
                for name in ['🚀 直接连接'] + group['proxies']:
                    if name not in unique:
                        unique.append(name)
                group['proxies'] = unique
                if unique != original:
                    groups_modified.append("⚓️ 其他流量: reordered to prefer direct")

    # Inject TUN configuration
    if enable_tun:
        dns_cfg = _ensure_commented_map(TUN_CONFIG['dns'])
        tun_cfg = _ensure_commented_map(TUN_CONFIG['tun'])
        if isinstance(config, CommentedMap):
            config.pop('allow-lan', None)
            config.pop('bind-address', None)
            config.pop('tproxy-port', None)
            config.pop('dns', None)
            config.pop('tun', None)
            config.insert(0, 'allow-lan', TUN_CONFIG['allow-lan'])
            config.insert(1, 'bind-address', TUN_CONFIG['bind-address'])
            config.insert(2, 'tproxy-port', TUN_CONFIG['tproxy-port'])
            config.insert(3, 'dns', dns_cfg)
            config.insert(4, 'tun', tun_cfg)
        else:
            config['allow-lan'] = TUN_CONFIG['allow-lan']
            config['bind-address'] = TUN_CONFIG['bind-address']
            config['tproxy-port'] = TUN_CONFIG['tproxy-port']
            config['dns'] = dns_cfg
            config['tun'] = tun_cfg
        print("\n[INJECTED] TUN configuration added")

    # Enforce required rules
    if 'rules' not in config or config['rules'] is None:
        config['rules'] = []

    # Inject VIP node/group and AI routing rules before generic required rules
    _inject_vip_and_ai_rules(config)

    default_group = _pick_default_proxy_group(config)
    rules = config['rules']
    added = []
    # Insert in reverse to keep REQUIRED_RULES order at the top
    for rule_tpl in reversed(REQUIRED_RULES):
        rule = rule_tpl.format(proxy_group=default_group)
        if rule not in rules:
            rules.insert(0, rule)
            added.append(rule)
    for rule in added:
        print(f"\n[INJECTED] Rule added: {rule}")

    # Output processed YAML
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f)

    # Print statistics
    print(f"\n{'='*60}")
    print(f"CONVERSION SUMMARY")
    print(f"{'='*60}")
    print(f"Original proxies: {original_proxy_count}")
    print(f"Removed proxies: {len(removed_names)}")
    print(f"Remaining proxies: {len(valid_proxies)}")
    print(f"\nGroups modified:")
    for gm in groups_modified:
        print(f"  - {gm}")
    print(f"\nTUN mode: {'Enabled' if enable_tun else 'Disabled'}")
    print(f"Output written to: {output_file}")
    print(f"{'='*60}")

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tools/test_converter.py <input_file> [output_file] [--tun]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 'output.yml'
    enable_tun = '--tun' in sys.argv

    print(f"Processing: {input_file}")
    print(f"Output to: {output_file}")
    print(f"TUN mode: {enable_tun}")
    print(f"\n{'='*60}\n")

    convert_config(input_file, output_file, enable_tun)
