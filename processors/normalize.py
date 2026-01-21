"""
normalize.py

Stage: RAW EXPORT -> NORMALIZED TREE (still using source_node_ids internally)

Goal:
- Take one raw conversation dict from conversations.json
- Extract:
  - conversation metadata
  - the mapping tree nodes (source ids)
  - plain text content + role + create_time
- Normalize children ordering deterministically (so later steps are stable)

This stage does NOT compute NTBA mark ids.
This stage does NOT rewrite parent/children to mark ids.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def safe_str(value: Any) -> str:
    # Converts any value to a string for safe display.
    return "" if value is None else str(value)


def extract_text_from_content(content: Optional[Dict[str, Any]]) -> str:
    """
    Converts a raw export message 'content' into a readable string.

    Export shape is usually:
      {"content_type": "text", "parts": ["hello", "world"]}

    For non-text content (tools, images, etc.), return a stable placeholder.
    """
    if content is None:
        return "[no content]"

    content_type = content.get("content_type")

    if content_type == "text":
        parts = content.get("parts", []) or []
        return "\n".join(str(p) for p in parts).strip()

    return f"[{content_type or 'unknown_content'}]"


def node_message_summary(node: Dict[str, Any]) -> Tuple[Optional[float], str]:
    """
    Returns (create_time, source_node_id) ranking keys for deterministic sorting.

    - create_time can be missing or None.
    - source_node_id is used as a stable tie-breaker.
    """
    msg = node.get("message") or {}
    ct = msg.get("create_time")
    if ct is None:
        return (None, "")
    try:
        return (float(ct), "")
    except Exception:
        return (None, "")


def find_root_id(mapping: Dict[str, Any]) -> str:
    """
    Finds the root node id for a raw export mapping.

    Most exports use a root node where parent == None.
    Some older sample formats use a literal "root" key.
    """
    if "root" in mapping:
        return "root"

    for node_id, node in mapping.items():
        if node.get("parent") is None:
            return node_id

    return next(iter(mapping.keys()))


def normalize_mapping_tree(mapping: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Normalizes the mapping tree in-place style (but returns a new dict).

    What "normalized" means here:
    - every node has: parent (maybe None), children (list), message (maybe None)
    - children are sorted deterministically:
        by child's message create_time (None last),
        then by child_id as a stable tie-breaker
    - message content is NOT simplified here; we just keep the raw message object
      for later extraction.
    """
    norm: Dict[str, Dict[str, Any]] = {}

    # First pass: shallow copy and normalize shapes.
    for node_id, node in (mapping or {}).items():
        parent = node.get("parent")
        children = node.get("children", []) or []
        message = node.get("message")

        norm[node_id] = {
            "parent": parent,
            "children": list(children),
            "message": message,
        }

    # Second pass: deterministic child sorting for every node.
    for node_id, node in norm.items():
        kids = node.get("children", []) or []

        def sort_key(child_id: str) -> Tuple[int, float, str]:
            child = norm.get(child_id, {})
            msg = child.get("message") or {}
            ct = msg.get("create_time")
            if ct is None:
                # Put missing timestamps after real timestamps.
                return (1, 9e18, child_id)
            try:
                return (0, float(ct), child_id)
            except Exception:
                return (1, 9e18, child_id)

        kids_sorted = sorted(kids, key=sort_key)
        node["children"] = kids_sorted

    return norm


def extract_node_fields(source_node_id: str, node: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts display-friendly fields from a normalized node.

    Output is a minimal dict used by later stages.
    """
    msg = node.get("message")
    if not msg:
        return {
            "source_node_id": source_node_id,
            "message": None,
            "parent": node.get("parent"),
            "children": list(node.get("children", []) or []),
        }

    author = msg.get("author") or {}
    role = safe_str(author.get("role", "unknown"))

    source_message_id = safe_str(msg.get("id") or msg.get("source_message_id") or "")
    # Note: exports vary; sometimes "id" is the message id, sometimes source_message_id.
    # We store *something* stable if it exists.

    ct = msg.get("create_time")
    create_time: Optional[float] = None
    if ct is not None:
        try:
            create_time = float(ct)
        except Exception:
            create_time = None

    content = msg.get("content")
    text = extract_text_from_content(content)

    return {
        "source_node_id": source_node_id,
        "message": {
            "role": role,
            "source_message_id": source_message_id,
            "create_time": create_time,
            "text": text,
        },
        "parent": node.get("parent"),
        "children": list(node.get("children", []) or []),
    }


def normalize_conversation(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes one raw export conversation.

    Returns a dict with:
    - metadata
    - root_source_node_id
    - nodes (still keyed by source_node_id)
    """
    convo_id = safe_str(raw.get("id") or raw.get("conversation_id") or "unknown-id")
    title = safe_str(raw.get("title") or "Untitled")
    create_time = raw.get("create_time")
    update_time = raw.get("update_time")
    project = raw.get("project") if isinstance(raw.get("project"), dict) else None

    mapping: Dict[str, Any] = raw.get("mapping") or raw.get("nodes") or {}

    if not isinstance(mapping, dict) or not mapping:
        return {
            "conversation_id": convo_id,
            "title": title,
            "create_time": float(create_time) if create_time is not None else None,
            "update_time": float(update_time) if update_time is not None else None,
            "project": project,
            "root_source_node_id": "",
            "nodes": {},
        }

    norm_mapping = normalize_mapping_tree(mapping)
    root_id = find_root_id(norm_mapping)

    nodes_out: Dict[str, Any] = {}
    for source_node_id, node in norm_mapping.items():
        nodes_out[source_node_id] = extract_node_fields(source_node_id, node)

    return {
        "conversation_id": convo_id,
        "title": title,
        "create_time": float(create_time) if create_time is not None else None,
        "update_time": float(update_time) if update_time is not None else None,
        "project": project,
        "root_source_node_id": root_id,
        "nodes": nodes_out,
    }
