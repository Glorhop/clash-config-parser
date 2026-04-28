import re

from .constants import (
    REGION_FILTER_KEYWORDS,
    REGION_FILTER_MODE_EXCLUDE,
    REGION_FILTER_MODE_INCLUDE,
    REGION_FILTER_MODE_OFF,
    REGION_FILTER_MODES,
)


def normalize_region_filter(value):
    if not isinstance(value, dict):
        return {"mode": REGION_FILTER_MODE_OFF, "regions": []}

    mode = str(
        value.get("mode")
        or value.get("region_filter_mode")
        or REGION_FILTER_MODE_OFF
    ).lower()
    raw_regions = value.get("regions", value.get("region_filter_regions", []))
    if isinstance(raw_regions, str):
        raw_regions = [item.strip() for item in raw_regions.split(",")]
    if not isinstance(raw_regions, list):
        raw_regions = []

    regions = []
    for region in raw_regions:
        key = str(region).strip().lower()
        if key in REGION_FILTER_KEYWORDS and key not in regions:
            regions.append(key)

    if mode not in REGION_FILTER_MODES or mode == REGION_FILTER_MODE_OFF or not regions:
        return {"mode": REGION_FILTER_MODE_OFF, "regions": []}
    return {"mode": mode, "regions": regions}


def region_matches(name: str, region_key: str) -> bool:
    keywords = REGION_FILTER_KEYWORDS.get(region_key, [])
    return any(_keyword_matches(name, keyword) for keyword in keywords)


def proxy_matches_regions(name: str, regions) -> bool:
    return any(region_matches(name, region) for region in regions)


def should_keep_proxy_by_region(name: str, region_filter) -> bool:
    normalized = normalize_region_filter(region_filter)
    mode = normalized["mode"]
    if mode == REGION_FILTER_MODE_OFF:
        return True

    matched = proxy_matches_regions(name, normalized["regions"])
    if mode == REGION_FILTER_MODE_INCLUDE:
        return matched
    if mode == REGION_FILTER_MODE_EXCLUDE:
        return not matched
    return True


def _keyword_matches(name: str, keyword: str) -> bool:
    if not name or not keyword:
        return False

    keyword_lower = keyword.lower()
    name_lower = name.lower()
    if keyword_lower.isascii() and keyword_lower.replace(" ", "").isalnum():
        if len(keyword_lower) <= 3:
            pattern = rf"(?<![a-z]){re.escape(keyword_lower)}(?![a-z])"
            return re.search(pattern, name_lower) is not None
        return keyword_lower in name_lower
    return keyword in name
