from typing import Any


def sanitize_surrogates(text: str) -> str:
    """Strip lone/unpaired Unicode surrogate code points and NUL bytes that corrupt databases."""
    if not text:
        return text
    cleaned = text.replace("\x00", "")
    return cleaned.encode("utf-8", "ignore").decode("utf-8")


def sanitize_obj(obj: Any) -> Any:
    """Recursively sanitize strings in nested dicts/lists/tuples to remove Unicode surrogates."""
    if isinstance(obj, str):
        return sanitize_surrogates(obj)
    elif isinstance(obj, dict):
        return {k: sanitize_obj(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_obj(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(sanitize_obj(v) for v in obj)
    return obj
