"""
model.py

This file defines the *internal* data shapes used by the processing pipeline.

Think of this as:
- "What is a processed conversation tree?"
- "What does a processed node look like?"

It does NOT parse raw export JSON directly.
It does NOT render output formats like HTML/MD/PDF.

It only defines clean structures that other code can use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProcessedMessage:
    """
    Represents the display-friendly message content for a node.

    role:
      - "user", "assistant", "system", "tool", etc.
    source_message_id:
      - OpenAI's message id if present (may be missing)
    create_time:
      - float seconds since epoch, if present
    text:
      - plain text (already extracted from the raw export content)
    """

    role: str
    source_message_id: str = ""
    create_time: Optional[float] = None
    text: str = ""


@dataclass
class ProcessedNode:
    """
    Represents one node in the processed tree.

    IMPORTANT:
    - node_key is NOT stored here.
      The node_key is the dictionary key in ProcessedConversation.nodes.

    source_node_id:
      - the original OpenAI mapping node id (UUID-like string)
      - this is how you trace back to the raw export

    parent:
      - the processed node_key of the parent (NOT the source_node_id)
      - None if this is the root

    children:
      - list of processed node_keys of the children (NOT source_node_ids)

    message:
      - None if this is a structural node with no message
      - otherwise a ProcessedMessage
    """

    source_node_id: str
    parent: Optional[str]
    children: List[str] = field(default_factory=list)
    message: Optional[ProcessedMessage] = None

    # derived = extra computed fields that ALL renderers might want.
    # Example fields:
    # - "N", "T", "B", "A"
    # - "timestamp_human"
    # - "is_main_path"
    derived: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedConversation:
    """
    Represents one processed conversation in "processed_tree_v1" format.

    schema:
      - always "processed_tree_v1" for this output format
    conversation_id:
      - OpenAI conversation id
    title:
      - conversation title or "Untitled"
    create_time / update_time:
      - float seconds since epoch if present
    project:
      - optional dict like {"id": "...", "name": "..."} if present
    root_node_id:
      - the processed node_key of the root node
    nodes:
      - dict mapping processed node_key -> ProcessedNode
    """

    schema: str
    conversation_id: str
    title: str
    create_time: Optional[float] = None
    update_time: Optional[float] = None
    project: Optional[Dict[str, str]] = None

    root_node_id: str = ""
    nodes: Dict[str, ProcessedNode] = field(default_factory=dict)
