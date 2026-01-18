from __future__ import annotations

from typing import Any, Dict, Optional


def extract_text_from_content(content: Optional[Dict[str, Any]]) -> str:
    """
    Convert a message 'content' object into a readable string.

    Typical export shape:
      {"content_type": "text", "parts": ["hello", "world"]}

    For non-text content, return a stable placeholder so renderers never crash.
    """
    if content is None:
        return "[no content]"

    content_type = content.get("content_type")

    if content_type == "text":
        parts = content.get("parts", []) or []
        return "\n".join(str(p) for p in parts).strip()

    return f"[{content_type or 'unknown_content'}]"
