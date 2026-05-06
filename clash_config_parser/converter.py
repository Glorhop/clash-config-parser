import logging

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .constants import (
    VIP_GROUP, VIP_NODE, AI_RULES,
    BLOCK_UUIDS, BLOCK_KEYWORDS, MULTIPLIER_REGEX,
    LATENCY_GROUPS, LATENCY_TEST_SETTINGS, TUN_CONFIG,
    MINIMAL_REQUIRED_RULES,
    LOAD_BALANCE_GROUP_NAME, LOAD_BALANCE_MAX_PROXIES,
    LOAD_BALANCE_SETTINGS, LOAD_BALANCE_CONFIGS,
    LOAD_BALANCE_RULES, LOAD_BALANCE_PAYLOAD,
    HF_REGION_LIMIT_CONFIGS, HF_REGION_KEYWORDS, HF_DEDICATED_KEYWORDS,
    LOW_MULTIPLIER_KEYWORD,
)
from .region_filter import should_keep_proxy_by_region
from .rules_store import load_rules

logger = logging.getLogger("clash-config-parser")


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


def force_block_style(data):
    """Recursively force block style for all mappings and sequences."""
    if isinstance(data, (dict, CommentedMap)):
        if hasattr(data, 'fa'):
            data.fa.set_block_style()
        for key, value in data.items():
            force_block_style(value)
    elif isinstance(data, (list, CommentedSeq)):
        if hasattr(data, 'fa'):
            data.fa.set_block_style()
        for item in data:
            force_block_style(item)


def _matches_any_keyword(name: str, keywords) -> bool:
    if not name:
        return False
    lower_name = name.lower()
    for kw in keywords:
        if kw in name or kw.lower() in lower_name:
            return True
    return False


def _is_region(name: str, region_key: str) -> bool:
    return _matches_any_keyword(name, HF_REGION_KEYWORDS.get(region_key, []))


def _is_dedicated_route(name: str) -> bool:
    return _matches_any_keyword(name, HF_DEDICATED_KEYWORDS)


def _filter_hf_region_proxies(proxy_names):
    """Select HK/JP/SG dedicated routes for huggingface load-balance."""
    filtered = []
    region_order = ["hk", "jp", "sg"]
    region_buckets = {region: [] for region in region_order}
    for name in proxy_names:
        if not name or not _is_dedicated_route(name):
            continue
        for region in region_order:
            if _is_region(name, region):
                region_buckets[region].append(name)
                break

    for region in region_order:
        for name in region_buckets[region]:
            if name in filtered:
                continue
            filtered.append(name)
            if len(filtered) >= LOAD_BALANCE_MAX_PROXIES:
                return filtered

    return filtered


def _is_hk_or_dedicated(name: str) -> bool:
    if not name:
        return False
    if _is_dedicated_route(name):
        return True
    return _is_region(name, "hk")


def inject_vip_and_ai_rules(config):
    """Inject the AI route group, optional VIP proxy, and AI routing rules."""
    def _ensure_map(d):
        if isinstance(d, CommentedMap):
            return d
        cm = CommentedMap()
        for k, v in d.items():
            if isinstance(v, dict):
                cm[k] = _ensure_map(v)
            elif isinstance(v, list):
                cm[k] = v
            else:
                cm[k] = v
        return cm

    def _unique_names(names):
        unique = []
        for name in names:
            if name and name not in unique:
                unique.append(name)
        return unique

    vip_name = None

    # 1. 注入可选 VIP 节点 (Proxy)
    if 'proxies' not in config or config['proxies'] is None:
        config['proxies'] = []

    if isinstance(VIP_NODE, dict) and VIP_NODE.get("name"):
        vip_name = VIP_NODE["name"]
        vip_proxy = _ensure_map(dict(VIP_NODE))
        existing_names = {
            p.get('name') for p in config['proxies']
            if isinstance(p, (dict, CommentedMap))
        }
        if vip_name not in existing_names:
            config['proxies'].insert(0, vip_proxy)
    else:
        logger.warning("VIP_NODE_JSON is not configured; AI group will use existing proxies")

    # 2. 注入 AI 专线策略组 (Proxy Group)
    if 'proxy-groups' not in config or config['proxy-groups'] is None:
        config['proxy-groups'] = []

    airport_names = [
        p.get('name') for p in config['proxies']
        if isinstance(p, (dict, CommentedMap)) and p.get('name') and p.get('name') != vip_name
    ]

    group_names = [
        g.get('name') for g in config['proxy-groups']
        if isinstance(g, (dict, CommentedMap)) and g.get('name')
    ]
    auto_group = next(
        (name for name in group_names if name in ("♻️ 自动选择", "自动选择") or "自动选择" in str(name)),
        None,
    )
    ai_like_group = next(
        (
            name for name in group_names
            if name != VIP_GROUP
            and (
                any(
                    token in str(name).lower()
                    for token in ("openai", "chatgpt", "gpt", "claude", "gemini")
                )
                or "AI" in str(name)
            )
        ),
        None,
    )
    primary_group = next(
        (
            name for name in group_names
            if name != VIP_GROUP and name in ("🔰 国外流量", "🚀 节点选择", "PROXY", "Proxy", "一分机场")
        ),
        None,
    )

    dedicated_proxies = [
        name for name in airport_names
        if _is_dedicated_route(name)
    ]
    low_rate_proxies = [
        name for name in airport_names
        if LOW_MULTIPLIER_KEYWORD in name
    ]

    ai_group_proxies = _unique_names(
        [vip_name, ai_like_group, auto_group, primary_group]
        + dedicated_proxies[:LOAD_BALANCE_MAX_PROXIES]
        + low_rate_proxies[:LOAD_BALANCE_MAX_PROXIES]
        + airport_names[:LOAD_BALANCE_MAX_PROXIES]
    )
    if not ai_group_proxies:
        ai_group_proxies = ["DIRECT"]

    vip_group = _ensure_map({
        "name": VIP_GROUP,
        "type": "select",
        "proxies": ai_group_proxies
    })

    existing_group = next(
        (
            g for g in config['proxy-groups']
            if isinstance(g, (dict, CommentedMap)) and g.get('name') == vip_group['name']
        ),
        None,
    )
    if existing_group:
        existing_proxies = existing_group.get('proxies') or []
        if not isinstance(existing_proxies, (list, CommentedSeq)):
            existing_proxies = [existing_proxies]
        existing_group['type'] = existing_group.get('type') or 'select'
        existing_group['proxies'] = _unique_names(ai_group_proxies + list(existing_proxies))
    else:
        config['proxy-groups'].insert(0, vip_group)

    # 3. 注入分流规则 (Rule)
    if 'rules' not in config or config['rules'] is None:
        config['rules'] = []

    for rule in reversed(AI_RULES):
        if rule not in config['rules']:
            config['rules'].insert(0, rule)


def clean_proxies(config, region_filter=None):
    valid_proxies = []
    removed_names = set()

    if 'proxies' in config and config['proxies']:
        for p in config['proxies']:
            name = p.get('name', '')
            uuid = p.get('uuid', '')

            is_blocked_uuid = uuid in BLOCK_UUIDS
            is_blocked_keyword = any(keyword in name for keyword in BLOCK_KEYWORDS)
            is_high_rate = bool(MULTIPLIER_REGEX.search(name))
            is_region_filtered = not should_keep_proxy_by_region(name, region_filter)

            should_remove = (
                is_blocked_keyword
                or is_high_rate
                or is_region_filtered
                or (is_blocked_uuid and (is_blocked_keyword or is_high_rate))
            )

            if should_remove:
                removed_names.add(name)
            else:
                valid_proxies.append(p)

        config['proxies'] = valid_proxies

    return removed_names


def process_groups(config, removed_names):
    if 'proxy-groups' not in config or not config['proxy-groups']:
        return

    for group in config['proxy-groups']:
        if 'proxies' in group and group['proxies']:
            group['proxies'] = [n for n in group['proxies'] if n not in removed_names]

        if group.get('name') in LATENCY_GROUPS:
            group.update(LATENCY_TEST_SETTINGS)

    for group in config['proxy-groups']:
        if group.get('name') == '⚓️ 其他流量' and group.get('proxies'):
            unique = []
            for name in ['🚀 直接连接'] + group['proxies']:
                if name not in unique:
                    unique.append(name)
            group['proxies'] = unique


def apply_load_balance_group(config, config_name):
    groups = config.get('proxy-groups')
    if not groups:
        return

    available_proxy_names = [
        p.get('name') for p in config.get('proxies', [])
        if isinstance(p, (dict, CommentedMap)) and p.get('name')
    ]

    # 优先选取 HK/JP/SG 中的 0.1 倍率节点
    preferred_proxies = [
        name for name in available_proxy_names
        if LOW_MULTIPLIER_KEYWORD in name and _matches_any_keyword(name, [
            kw for region in ("hk", "jp", "sg") for kw in HF_REGION_KEYWORDS[region]
        ])
    ][:LOAD_BALANCE_MAX_PROXIES]

    # 其次选取其它地区的 0.1 倍率节点
    if not preferred_proxies:
        preferred_proxies = [
            name for name in available_proxy_names
            if LOW_MULTIPLIER_KEYWORD in name
        ][:LOAD_BALANCE_MAX_PROXIES]

    if not preferred_proxies:
        if config_name in HF_REGION_LIMIT_CONFIGS:
            preferred_proxies = _filter_hf_region_proxies(available_proxy_names)

    if not preferred_proxies:
        for name in available_proxy_names:
            if _is_hk_or_dedicated(name) and name not in preferred_proxies:
                preferred_proxies.append(name)
            if len(preferred_proxies) >= LOAD_BALANCE_MAX_PROXIES:
                break

    if preferred_proxies:
        filtered = preferred_proxies
    else:
        candidate_proxies = []
        if len(groups) >= 2 and groups[1].get('proxies'):
            candidate_proxies = groups[1].get('proxies') or []
        elif groups[0].get('proxies'):
            candidate_proxies = groups[0].get('proxies') or []
        elif available_proxy_names:
            candidate_proxies = available_proxy_names

        filtered = []
        for name in candidate_proxies:
            if name not in available_proxy_names:
                continue
            if name in filtered:
                continue
            filtered.append(name)
            if len(filtered) >= LOAD_BALANCE_MAX_PROXIES:
                break

        if not filtered:
            filtered = available_proxy_names[:LOAD_BALANCE_MAX_PROXIES]
        if not filtered:
            return

    existing_group = None
    for group in groups:
        if group.get('name') == LOAD_BALANCE_GROUP_NAME:
            existing_group = group
            break

    if existing_group:
        groups.remove(existing_group)
        target_group = existing_group
    else:
        target_group = _ensure_commented_map({"name": LOAD_BALANCE_GROUP_NAME})

    target_group['name'] = LOAD_BALANCE_GROUP_NAME
    target_group.update(LOAD_BALANCE_SETTINGS)
    target_group['proxies'] = filtered

    groups.insert(1, target_group)


def inject_load_balance_rules(config):
    if 'rules' not in config or config['rules'] is None:
        config['rules'] = []
    rules = config['rules']

    for rule in reversed(LOAD_BALANCE_RULES):
        if rule not in rules:
            rules.insert(0, rule)

    payload = config.get('payload')
    if payload is None:
        payload = CommentedSeq()
        config['payload'] = payload
    if isinstance(payload, (list, CommentedSeq)):
        for entry in LOAD_BALANCE_PAYLOAD:
            if entry not in payload:
                payload.append(entry)


def inject_tun(config, enable_tun: bool):
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
            config.insert(5, 'keep-alive-interval', TUN_CONFIG['keep-alive-interval'])
            config.insert(6, 'tcp-concurrent', TUN_CONFIG["tcp-concurrent"])
        else:
            config['allow-lan'] = TUN_CONFIG['allow-lan']
            config['bind-address'] = TUN_CONFIG['bind-address']
            config['tproxy-port'] = TUN_CONFIG['tproxy-port']
            config['dns'] = dns_cfg
            config['tun'] = tun_cfg
            config['keep-alive-interval'] = TUN_CONFIG['keep-alive-interval']
            config['tcp-concurrent'] = TUN_CONFIG['tcp-concurrent']


def enforce_rules(config, use_minimal=False):
    if 'rules' not in config or config['rules'] is None:
        config['rules'] = []
    rules = config['rules']

    available_groups = {
        g.get('name') for g in (config.get('proxy-groups') or [])
        if isinstance(g, (dict, CommentedMap)) and g.get('name')
    }
    preferred_groups = ["一分机场", "🔰 国外流量", "🚀 节点选择", "PROXY", "Proxy", "自动选择"]
    fallback_group = next((name for name in preferred_groups if name in available_groups), None)
    if not fallback_group:
        fallback_group = next(iter(available_groups), "DIRECT")

    def _normalize_rule_policy(rule: str) -> str:
        parts = [p.strip() for p in str(rule).split(',')]
        if len(parts) < 3:
            return rule
        policy = parts[2]
        passthrough_policies = {
            "DIRECT", "REJECT", "REJECT-DROP", "PASS", "GLOBAL", "MATCH"
        }
        if policy in passthrough_policies or policy in available_groups:
            return rule
        parts[2] = fallback_group
        return ','.join(parts)

    if use_minimal:
        required_rules = MINIMAL_REQUIRED_RULES
    else:
        required_rules = load_rules()

    required_rules = [_normalize_rule_policy(rule) for rule in required_rules]

    for rule in reversed(required_rules):
        if rule not in rules:
            rules.insert(0, rule)


def build_clash_config(proxies: list) -> CommentedMap:
    """Build a complete Clash config from parsed proxies."""
    proxy_names = [p["name"] for p in proxies]

    config = CommentedMap()
    config["proxies"] = [_ensure_commented_map(p) for p in proxies]

    config["proxy-groups"] = [
        _ensure_commented_map({
            "name": "🔰 国外流量",
            "type": "select",
            "proxies": ["♻️ 自动选择", "🚀 直接连接"] + proxy_names,
        }),
        _ensure_commented_map({
            "name": "♻️ 自动选择",
            "type": "url-test",
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50,
            "proxies": proxy_names,
        }),
        _ensure_commented_map({
            "name": "💬 OpenAi",
            "type": "select",
            "proxies": ["🔰 国外流量", "♻️ 自动选择"] + proxy_names,
        }),
        _ensure_commented_map({
            "name": "🚀 直接连接",
            "type": "select",
            "proxies": ["DIRECT"],
        }),
        _ensure_commented_map({
            "name": "⚓️ 其他流量",
            "type": "select",
            "proxies": ["🚀 直接连接", "🔰 国外流量", "♻️ 自动选择"],
        }),
    ]

    config["rules"] = [
        "MATCH,⚓️ 其他流量",
    ]

    return config
