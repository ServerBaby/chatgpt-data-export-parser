from __future__ import annotations

from typing import Any, Dict, Optional

from model import Conversation
from .paths import compute_main_path
from .turns import build_turns_from_main_path


def parse_conversation(raw: Dict[str, Any]) -> Conversation:
    """
    Parse one raw conversation export object into our internal Conversation.

    - selects main path (longest path; tie-break latest timestamp)
    - extracts Turns along that path
    """
    convo_id = str(raw.get("id", "unknown-id"))
    title = str(raw.get("title") or "Untitled (no title)")

    create_time = raw.get("create_time")
    update_time = raw.get("update_time")
    project = raw.get("project")

    mapping: Dict[str, Any] = raw.get("mapping") or {}

    convo = Conversation(
        id=convo_id,
        title=title,
        create_time=float(create_time) if create_time is not None else None,
        update_time=float(update_time) if update_time is not None else None,
        project=project if isinstance(project, dict) else None,
        turns=[],
    )

    if not mapping:
        return convo

    main_path = compute_main_path(mapping)
    convo.turns = build_turns_from_main_path(mapping, main_path)
    return convo
