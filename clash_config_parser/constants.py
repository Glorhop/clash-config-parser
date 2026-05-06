import json
import os
import re

from .paths import RULES_FILE


def _load_json_env(name: str, fallback):
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback

# ==========================================
# VIP 节点与 AI 专属分流规则配置
# ==========================================
VIP_GROUP = "💎 AI 专线"

VIP_NODE = _load_json_env("VIP_NODE_JSON", {})

AI_RULES = [
    # Claude 规则
    f"DOMAIN-SUFFIX,anthropic.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,claude.ai,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,claudeusercontent.com,{VIP_GROUP}",
    # OpenAI 规则
    f"DOMAIN-SUFFIX,openai.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,api.openai.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,auth0.openai.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,chatgpt.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,oaistatic.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,oaiusercontent.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,openaiusercontent.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,sora.com,{VIP_GROUP}",
    f"DOMAIN-KEYWORD,openai,{VIP_GROUP}",
    f"DOMAIN-KEYWORD,chatgpt,{VIP_GROUP}",
    # Gemini 规则
    f"DOMAIN-SUFFIX,gemini.google.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,generativelanguage.googleapis.com,{VIP_GROUP}",
    f"DOMAIN-SUFFIX,ai.google.dev,{VIP_GROUP}"
]

# Predefined removal rules
BLOCK_UUIDS = ["6c50c1b6-aa0d-3648-85ae-e5f6b9f7be1d"]
BLOCK_KEYWORDS = [
    "最新网址",
    "foosber.com",
    "节点变化频繁",
    "剩余流量",
    "距离下次",
    "套餐到期",
    "双旦优惠",
    "认准官网地址",
    "专属五折",
    "已推送邮箱",
    "如果现在只能看到少数线路",
    "立即更新教程推荐最新软件",
]
MULTIPLIER_REGEX = re.compile(r'\b(10|[245])x\b', re.IGNORECASE)
LATENCY_GROUPS = {"🔰 国外流量", "💬 OpenAi"}

CACHE_KEY_PREFIX = "clash-cache:"
MINIMAL_REQUIRED_RULES = [
    "DOMAIN-SUFFIX,1008761.xyz,DIRECT",
]
REQUEST_TIMEOUT = 10
LATENCY_TEST_SETTINGS = {
    "type": "url-test",
    "url": "http://www.gstatic.com/generate_204",
    "interval": 300,
    "tolerance": 50
}

LOAD_BALANCE_GROUP_NAME = "HF-Multi-Channel"
LOAD_BALANCE_MAX_PROXIES = 8
LOAD_BALANCE_SETTINGS = {
    "type": "load-balance",
    "strategy": "round-robin",
    "url": "http://www.gstatic.com/generate_204",
    "interval": 300,
}
LOAD_BALANCE_CONFIGS = {"config2", "config4"}
HF_REGION_LIMIT_CONFIGS = {"config4"}
LOAD_BALANCE_RULES = [
    "DOMAIN-SUFFIX,huggingface.co,HF-Multi-Channel",
    "DOMAIN-SUFFIX,hf.co,HF-Multi-Channel",
    "DOMAIN-KEYWORD,huggingface,HF-Multi-Channel",
    "DOMAIN-SUFFIX,cdn-lfs.huggingface.co,HF-Multi-Channel",
    "DOMAIN-SUFFIX,huggingfaceusercontent.com,HF-Multi-Channel",
    "DOMAIN-SUFFIX,huggingface.cloud,HF-Multi-Channel",
    "DOMAIN-SUFFIX,hf.space,HF-Multi-Channel",
]
LOAD_BALANCE_PAYLOAD = [
    "+.huggingface.co",
    "+.hf.co",
    "+.cdn-lfs.huggingface.co",
    "+.huggingface.cloud",
    "+.huggingfaceusercontent.com",
    "+.hf.space",
]

HF_REGION_KEYWORDS = {
    "hk": ["香港", "hong kong", "hongkong", "hk"],
    "jp": ["日本", "东京", "tokyo", "japan", "jp"],
    "sg": ["新加坡", "singapore", "sg"],
}
HF_DEDICATED_KEYWORDS = ["专线", "專線", "iplc", "iepl", "专用"]
LOW_MULTIPLIER_KEYWORD = "0.1倍率"

REGION_FILTER_MODE_OFF = "off"
REGION_FILTER_MODE_INCLUDE = "include"
REGION_FILTER_MODE_EXCLUDE = "exclude"
REGION_FILTER_MODES = {
    REGION_FILTER_MODE_OFF,
    REGION_FILTER_MODE_INCLUDE,
    REGION_FILTER_MODE_EXCLUDE,
}
REGION_FILTER_OPTIONS = [
    {
        "key": "hk",
        "label": "香港",
        "keywords": ["🇭🇰", "香港", "hong kong", "hongkong", "hk"],
    },
    {
        "key": "jp",
        "label": "日本",
        "keywords": ["🇯🇵", "日本", "东京", "東京", "大阪", "japan", "tokyo", "osaka", "jp", "jpn"],
    },
    {
        "key": "us",
        "label": "美国",
        "keywords": [
            "🇺🇸", "美国", "美國", "洛杉矶", "洛杉磯", "西雅图", "西雅圖", "纽约", "紐約",
            "圣何塞", "聖荷西", "united states", "america", "los angeles", "seattle",
            "new york", "san jose", "sanjose", "ashburn", "virginia", "california",
            "silicon valley", "usa", "us", "lax", "sjc", "nyc",
        ],
    },
    {
        "key": "sg",
        "label": "新加坡",
        "keywords": ["🇸🇬", "新加坡", "狮城", "獅城", "singapore", "sg", "sgp"],
    },
    {
        "key": "tw",
        "label": "台湾",
        "keywords": ["🇹🇼", "台湾", "台灣", "臺灣", "taiwan", "taipei", "tw", "twn"],
    },
    {
        "key": "kr",
        "label": "韩国",
        "keywords": ["🇰🇷", "韩国", "韓國", "首尔", "首爾", "south korea", "korea", "seoul", "kr", "kor"],
    },
    {
        "key": "uk",
        "label": "英国",
        "keywords": [
            "🇬🇧", "英国", "英國", "伦敦", "倫敦", "united kingdom", "great britain",
            "britain", "london", "uk", "gb", "gbr",
        ],
    },
    {
        "key": "de",
        "label": "德国",
        "keywords": ["🇩🇪", "德国", "德國", "法兰克福", "法蘭克福", "germany", "frankfurt", "de", "deu"],
    },
    {
        "key": "fr",
        "label": "法国",
        "keywords": ["🇫🇷", "法国", "法國", "巴黎", "france", "paris", "fr", "fra"],
    },
    {
        "key": "ca",
        "label": "加拿大",
        "keywords": ["🇨🇦", "加拿大", "canada", "toronto", "vancouver", "ca", "can"],
    },
    {
        "key": "au",
        "label": "澳大利亚",
        "keywords": ["🇦🇺", "澳大利亚", "澳洲", "澳大利亞", "australia", "sydney", "melbourne", "au", "aus"],
    },
]
REGION_FILTER_KEYWORDS = {
    option["key"]: option["keywords"]
    for option in REGION_FILTER_OPTIONS
}

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
    },
    "keep-alive-interval": 15,
    "tcp-concurrent": True
}

REQUIRED_RULES_FILE = str(RULES_FILE)
