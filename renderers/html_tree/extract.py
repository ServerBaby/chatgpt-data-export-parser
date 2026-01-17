"""
Extraction helpers for the HTML tree renderer.

These functions pull display-friendly values from processed_tree_v1 nodes.
They are intentionally defensive and avoid raising on missing fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


def safe_str(value: Any) -> str:
    # Converts any value to a string for safe display.
    # If value is None, return an empty string.
    # - Ensures "None" never appears in output.
    return "" if value is None else str(value)


def sanitize_filename(name: str) -> str:
    # Creates a safe filename from a conversation title.
    # If filename is missing, return a non-empty default.
    # Replaces illegal characters and limits length to 120 characters.
    name = (name or "").strip() or "untitled"
    bad = '<>:"/\\|?*'  # Forbidden Windows characters
    for ch in bad:
        name = name.replace(ch, "_")
    return name[:120].strip(" ._")


def get_role(node: Dict[str, Any]) -> str:
    msg = node.get("message")
    if not msg:
        return "none"
    return safe_str(msg.get("role", "unknown"))


def get_message_id(node: Dict[str, Any]) -> str:
    msg = node.get("message")
    if not msg:
        return ""
    return safe_str(msg.get("source_message_id") or "")


def get_create_time(node: Dict[str, Any]) -> str:
    msg = node.get("message")
    if not msg:
        return ""
    ct = msg.get("create_time")
    return safe_str(ct) if ct is not None else ""


def format_create_time_human(create_time: Any) -> str:
    """
    Convert Unix timestamp to: DD MMM YYYY HH:MM:SS (local time).

    Accepts:
    - float/int unix seconds
    - string containing a number

    Returns "" if missing/invalid.
    """
    if create_time is None or create_time == "":
        return ""
    try:
        ts = float(create_time)
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d %b %Y %H:%M:%S")
    except Exception:
        return ""


def get_branch_id(node: Dict[str, Any]) -> str:
    """
    Branch identifier for this node (if your processed_tree_v1 includes it).
    Common possibilities:
    - node["branch_id"]
    - node["branch"]  (if you used that name instead)
    """
    return safe_str(node.get("branch_id") or node.get("branch") or "")


def get_turn_id(node: Dict[str, Any]) -> str:
    """
    Turn identifier for this node (if present).
    """
    return safe_str(node.get("turn_id") or "")


def get_alternate_id(node: Dict[str, Any]) -> str:
    """
    Alternate identifier for this node (if present).
    """
    return safe_str(node.get("alternate_id") or "")


def extract_text(node: Dict[str, Any], max_len: int = 250) -> str:
    msg = node.get("message")
    if not msg:
        return "[no message]"
    text = safe_str(msg.get("text", "")).strip() or "[empty text]"
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text
