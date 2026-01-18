from __future__ import annotations

from typing import Any, Dict, List, Optional

from model import Turn
from .mapping import (
    is_assistant_message,
    is_user_message,
    node_to_message,
)
from .paths import children_of, next_on_main_path


def build_turns_from_main_path(mapping: Dict[str, Any], main_path: List[str]) -> List[Turn]:
    """
    Walk the selected main path and build Turns:
      - whenever we hit a user node, create a Turn
      - assistant on main path (if present) becomes turn.assistant
      - other assistant children of that user become alternates
    """
    turns: List[Turn] = []
    if not mapping or not main_path:
        return turns

    for node_id in main_path:
        node = mapping.get(node_id) or {}

        if not is_user_message(node):
            continue

        user_msg = node_to_message(node_id, node)

        # Assistant candidates are assistant-children of this user node
        user_children = children_of(mapping, node_id)
        assistant_child_ids = [
            cid for cid in user_children if is_assistant_message(mapping.get(cid, {}) or {})
        ]

        # Main assistant = whichever assistant is on the main path next (if any)
        main_assistant_id: Optional[str] = None
        nxt = next_on_main_path(main_path, node_id)
        if nxt is not None and nxt in assistant_child_ids:
            main_assistant_id = nxt

        assistant_msg = None
        alternates = []

        if main_assistant_id is not None:
            assistant_msg = node_to_message(main_assistant_id, mapping.get(main_assistant_id, {}) or {})

        for cid in assistant_child_ids:
            if cid != main_assistant_id:
                alternates.append(node_to_message(cid, mapping.get(cid, {}) or {}))

        turns.append(Turn(user=user_msg, assistant=assistant_msg, alternates=alternates))

    return turns
