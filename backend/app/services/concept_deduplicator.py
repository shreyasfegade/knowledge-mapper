import re
from difflib import SequenceMatcher


def _normalize(label: str) -> str:
    label = label.lower().strip()
    label = re.sub(r"[^\w\s]", "", label)
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    """Check if two normalized labels are fuzzy-matches using SequenceMatcher."""
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _is_substring_match(a: str, b: str) -> bool:
    """Check if one label is a meaningful substring of another.

    'Cooling Rate' matches 'Critical Cooling Rate'
    but not short fragments like 'of' matching 'Rate of Change'.
    """
    if len(a) < 4 or len(b) < 4:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < len(longer) * 0.5:
        return False
    return shorter in longer


def deduplicate(concepts: list[dict]) -> list[dict]:
    if len(concepts) <= 1:
        return concepts

    # Phase 1: Exact normalization dedup
    seen: dict[str, int] = {}
    unique: list[dict] = []

    for c in concepts:
        norm = _normalize(c["label"])
        if not norm:
            continue
        if norm in seen:
            idx = seen[norm]
            if c["confidence"] > unique[idx]["confidence"]:
                unique[idx] = c
        else:
            seen[norm] = len(unique)
            unique.append(c)

    # Phase 2: Fuzzy and substring dedup
    # Merge concepts that are fuzzy-matches or meaningful substrings
    merged: list[dict] = []
    merged_norms: list[str] = []

    for c in unique:
        norm = _normalize(c["label"])
        found_match = False

        for idx, existing_norm in enumerate(merged_norms):
            if _fuzzy_match(norm, existing_norm) or _is_substring_match(norm, existing_norm):
                # Keep the higher-confidence version
                if c["confidence"] > merged[idx]["confidence"]:
                    merged[idx] = c
                    merged_norms[idx] = norm
                found_match = True
                break

        if not found_match:
            merged.append(c)
            merged_norms.append(norm)

    return merged
