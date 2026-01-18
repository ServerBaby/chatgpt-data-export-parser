"""
model.py

Internal data shapes used by the program.

This file defines: Conversation, Turn, Message.
It does NOT load JSON and it does NOT write output files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Message:
    """
    A single message in a conversation.

    - id: node/message id from the export mapping (useful for tracing/debugging)
    - role: "user", "assistant", "system", "tool", etc.
    - text: readable content or a placeholder
    - timestamp: float seconds since epoch, if available
    - content_type: e.g. "text", "multimodal", "tool_result" (if available)
    - metadata: raw metadata blob (kept optional + shallow for future use)
    """

    id: str
    role: str
    text: str
    timestamp: Optional[float] = None
    content_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class Turn:
    """
    One user->assistant exchange.

    - user: the user message for this turn
    - assistant: the chosen "main path" assistant response, if any
    - alternates: other assistant responses (regenerations / siblings)
    """

    user: Message
    assistant: Optional[Message] = None
    alternates: List[Message] = field(default_factory=list)


@dataclass
class Conversation:
    """
    Represents a full conversation thread.

    - id/title/create_time/update_time: from export (if present)
    - project: optional project metadata dict (kept flexible)
    - turns: ordered list of turns extracted from the chosen main path
    """

    id: str
    title: str
    create_time: Optional[float] = None
    update_time: Optional[float] = None
    project: Optional[Dict[str, Any]] = None
    turns: List[Turn] = field(default_factory=list)
