"""
model.py

This file defines the *internal* data shapes used by the program.

Think of this as: "What is a Conversation? What is a Message?"
It does NOT read JSON and it does NOT write output files.

It only defines clean structures that other code can use.
"""

# dataclass = an easy way to define "data holder" classes in Python.
from dataclasses import dataclass, field

# Optional means "this value can be a string OR it can be None".
from typing import Optional, List, Dict


@dataclass
class Message:
    """
    Represents a single message in a conversation.

    role: who wrote it (e.g. "user", "assistant", "system", "tool")
    text: the readable content for the message (or a placeholder)
    timestamp: when it happened (float seconds since epoch) if available
    """

    role: str
    text: str
    timestamp: Optional[float] = None


@dataclass
class Turn:
    """
    Represents one "turn" of conversation:
    - a user message
    - the assistant's main response
    - any alternate assistant responses (regenerations)
    """

    user: Message
    assistant: Optional[Message] = None

    # alternates = extra assistant answers at the same step
    alternates: List[Message] = field(default_factory=list)


@dataclass
class Conversation:
    """
    Represents a whole conversation thread.

    id: conversation id from the export
    title: title from the export (may be missing)
    create_time / update_time: timestamps if present
    project: optional project metadata (if the export includes it)
    turns: the ordered list of turns
    """

    id: str
    title: str
    create_time: Optional[float] = None
    update_time: Optional[float] = None

    # project holds tags like {"id": "...", "name": "..."} if present.
    project: Optional[Dict[str, str]] = None

    turns: List[Turn] = field(default_factory=list)
