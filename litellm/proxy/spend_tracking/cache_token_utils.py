"""Provider cache-token normalization helpers for spend tracking."""


def extract_cache_read_tokens(usage_obj: dict) -> int:
    """Return provider-reported input tokens served from prompt cache."""
    explicit = usage_obj.get("cache_read_input_tokens", 0) or 0
    if explicit:
        return int(explicit)
    details = usage_obj.get("prompt_tokens_details") or {}
    return int(details.get("cached_tokens", 0) or 0)
