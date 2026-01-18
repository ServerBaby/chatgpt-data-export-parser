"""
convert.py

Stage 1 goals:
- Load a ChatGPT export-like JSON file (e.g. examples/conversations_fake.json)
- Build a simple internal Conversation model (using model.py)
- Preserve:
  - user vs assistant role
  - titles/timestamps (when available)
  - alternates (regen answers) as alternates
  - project metadata (if present)
- Print a readable summary to the terminal

This is intentionally minimal. Later stages will:
- split parsing into parser.py
- add renderers/ for txt/md/html/docx/pdf
"""

# argparse is the standard library tool for command-line arguments.
import argparse

# json lets Python load JSON files.
import json

# Path is a nice way to handle file paths.
from pathlib import Path

# typing helps describe expected shapes (for clarity, not required to run).
from typing import Any, Dict, List, Optional, Tuple

# Import internal structures from model.py
from model import Conversation, Message, Turn


def extract_text_from_content(content: Optional[Dict[str, Any]]) -> str:
    """
    Converts a message 'content' object into a readable string.

    The export usually stores text like:
      {"content_type": "text", "parts": ["hello", "world"]}

    For non-text content, this function returns a clear placeholder so the tool
    never crashes and the transcript remains readable.
    """
    # If content is missing entirely, return a placeholder.
    if content is None:
        return "[no content]"

    # Get the content type, if it exists.
    content_type = content.get("content_type")

    # If it's plain text, combine the "parts" list into a readable string.
    if content_type == "text":
        parts = content.get("parts", [])
        # Join list items with newlines to preserve multi-paragraph messages.
        return "\n".join(str(p) for p in parts).strip()

    # If it's something else (tool result, attachments, etc.), return placeholder.
    return f"[{content_type or 'unknown_content'}]"


def build_parent_children_index(mapping: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """
    Builds two helpful lookup tables from the export mapping tree:

    parent_of[child_id] = parent_id
    children_of[parent_id] = [child_id, child_id, ...]

    This makes it easier to navigate the tree.
    """
    parent_of: Dict[str, str] = {}
    children_of: Dict[str, List[str]] = {}

    # Loop through each node in the mapping dict.
    for node_id, node in mapping.items():
        # Parent can be None at root.
        parent = node.get("parent")

        # Store parent if it exists.
        if parent is not None:
            parent_of[node_id] = parent

        # Children is usually a list.
        kids = node.get("children", []) or []
        children_of[node_id] = list(kids)

    return parent_of, children_of


def find_root_id(mapping: Dict[str, Any]) -> str:
    """
    Finds the root node id.

    Many exports include a literal "root" key, but this function also handles
    cases where the root is a node with no parent.
    """
    # Most common case.
    if "root" in mapping:
        return "root"

    # Otherwise, find any node with parent == None.
    for node_id, node in mapping.items():
        if node.get("parent") is None:
            return node_id

    # If everything fails, just pick something (prevents crash).
    # This is defensive coding for weird exports.
    return next(iter(mapping.keys()))


def pick_main_child(children: List[str], mapping: Dict[str, Any]) -> Optional[str]:
    """
    Picks one child node to be the "main path" continuation.

    In real exports, ordering can be messy. For stage 1, this picks the child
    with the earliest message timestamp, which is usually the intended main path.

    Returns:
      node_id of the chosen child, or None if no children exist.
    """
    if not children:
        return None

    # Create a list of (timestamp, child_id).
    ranked: List[Tuple[float, str]] = []

    for child_id in children:
        node = mapping.get(child_id, {})
        msg = node.get("message")
        # If message exists, use its create_time; else use a large value.
        ts = 9e18
        if msg and msg.get("create_time") is not None:
            ts = float(msg["create_time"])
        ranked.append((ts, child_id))

    # Sort so the earliest timestamp comes first.
    ranked.sort(key=lambda x: x[0])

    # Return the child_id with earliest timestamp.
    return ranked[0][1]


def is_user_message(node: Dict[str, Any]) -> bool:
    """Returns True if the node contains a user-authored message."""
    msg = node.get("message") or {}
    author = msg.get("author") or {}
    return author.get("role") == "user"


def is_assistant_message(node: Dict[str, Any]) -> bool:
    """Returns True if the node contains an assistant-authored message."""
    msg = node.get("message") or {}
    author = msg.get("author") or {}
    return author.get("role") == "assistant"


def node_to_message(node: Dict[str, Any]) -> Message:
    """
    Converts a raw mapping node into a Message dataclass instance.
    """
    msg = node.get("message") or {}
    author = msg.get("author") or {}
    role = str(author.get("role", "unknown"))

    # Pull raw content dict and convert it into text/placeholder.
    content = msg.get("content")
    text = extract_text_from_content(content)

    # Get timestamp if present.
    ts = msg.get("create_time")
    timestamp = float(ts) if ts is not None else None

    return Message(role=role, text=text, timestamp=timestamp)


def parse_conversation(raw: Dict[str, Any]) -> Conversation:
    """
    Parses one raw conversation object from the JSON export into our model.

    Strategy (simple stage 1):
    - Use the mapping tree
    - Walk along a main path
    - Every time we hit a user message, we create a Turn
    - We attach assistant responses as:
        - main assistant (chosen by timestamp)
        - alternates (other assistant siblings)
    """
    # Basic metadata fields (with safe defaults).
    convo_id = str(raw.get("id", "unknown-id"))
    title = str(raw.get("title") or "Untitled (no title)")
    create_time = raw.get("create_time")
    update_time = raw.get("update_time")

    # Optional project metadata (may not exist).
    project = raw.get("project")

    # The "mapping" is the tree of messages.
    mapping: Dict[str, Any] = raw.get("mapping") or {}

    # Create the Conversation object we will fill.
    convo = Conversation(
        id=convo_id,
        title=title,
        create_time=float(create_time) if create_time is not None else None,
        update_time=float(update_time) if update_time is not None else None,
        project=project if isinstance(project, dict) else None,
        turns=[],
    )

    # If mapping is empty, return the conversation as-is.
    if not mapping:
        return convo

    # Find the root node id.
    root_id = find_root_id(mapping)

    # Current node starts at root.
    current_id: Optional[str] = root_id

    # Walk the tree along a main path until we run out.
    while current_id is not None:
        current_node = mapping.get(current_id, {})

        # Look at children of current node.
        children = current_node.get("children", []) or []

        # Choose next step along the main path.
        next_id = pick_main_child(children, mapping)

        # If there is no next node, end walk.
        if next_id is None:
            break

        next_node = mapping.get(next_id, {})

        # If the next node is a user message, start a new Turn.
        if is_user_message(next_node):
            user_msg = node_to_message(next_node)

            # The user node may have children that are assistant responses.
            user_children = next_node.get("children", []) or []

            # Collect assistant child nodes.
            assistant_child_ids = [
                cid for cid in user_children if is_assistant_message(mapping.get(cid, {}))
            ]

            # Choose one assistant response as the "main" response.
            main_assistant_id = pick_main_child(assistant_child_ids, mapping)

            main_assistant_msg: Optional[Message] = None
            alternates: List[Message] = []

            if main_assistant_id is not None:
                # Convert the chosen assistant node into a Message.
                main_assistant_msg = node_to_message(mapping.get(main_assistant_id, {}))

                # Any other assistant sibling becomes an alternate response.
                for cid in assistant_child_ids:
                    if cid != main_assistant_id:
                        alternates.append(node_to_message(mapping.get(cid, {})))

            # Create and store the Turn in the Conversation.
            convo.turns.append(
                Turn(user=user_msg, assistant=main_assistant_msg, alternates=alternates)
            )

            # Continue walking from the main assistant if it exists,
            # otherwise continue walking from the user message node.
            current_id = main_assistant_id if main_assistant_id is not None else next_id
            continue

        # If it wasn't a user message, just keep walking along the chosen path.
        current_id = next_id

    return convo


def main() -> None:
    """
    Main entry point for the script.

    This function:
    - reads command-line arguments
    - loads JSON
    - parses each conversation into model objects
    - prints a readable summary
    """
    # Create a CLI argument parser.
    parser = argparse.ArgumentParser(
        description=(
            "Parse a ChatGPT export JSON file into an internal model and print "
            "a readable summary (stage 1)."
        )
    )

    # Add an input file argument.
    parser.add_argument(
        "input",
        nargs="?",
        default="examples/conversations_fake.json",
        help="Path to conversations.json (defaults to examples/conversations_fake.json)",
    )

    # Parse arguments from the command line.
    args = parser.parse_args()

    # Convert input argument into a Path object.
    input_path = Path(args.input)

    # Fail early if the file doesn't exist.
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    # Read file text.
    raw_text = input_path.read_text(encoding="utf-8")

    # Parse JSON into Python objects.
    raw_data = json.loads(raw_text)

    # The export might be a list of conversations (common).
    if not isinstance(raw_data, list):
        raise SystemExit("Expected the top-level JSON to be a list of conversations.")

    # Parse all conversations.
    conversations: List[Conversation] = []
    for raw_convo in raw_data:
        if isinstance(raw_convo, dict):
            conversations.append(parse_conversation(raw_convo))

    # Print a summary.
    print()
    print("=" * 72)
    print("ChatGPT Data Export Parser (Stage 1 summary)")
    print("=" * 72)
    print(f"Input: {input_path}")
    print(f"Conversations parsed: {len(conversations)}")
    print()

    # Print each conversation in a readable way.
    for idx, convo in enumerate(conversations, start=1):
        print("-" * 72)
        print(f"[{idx}] Title: {convo.title}")
        print(f"    ID: {convo.id}")

        # Show project tag if present.
        if convo.project and convo.project.get("name"):
            print(f"    Project: {convo.project.get('name')}")

        # Show how many turns we extracted.
        print(f"    Turns: {len(convo.turns)}")
        print()

        # Print the first few turns (not infinite spam).
        # Stage 1: print up to 5 turns.
        for t_index, turn in enumerate(convo.turns[:5], start=1):
            print(f"    Turn {t_index}:")
            print(f"      User: {turn.user.text}")

            # Main assistant response (if any).
            if turn.assistant is not None:
                print(f"      Assistant: {turn.assistant.text}")
            else:
                print("      Assistant: [missing]")

            # Alternate assistant answers.
            if turn.alternates:
                print("      Alternates:")
                for a_i, alt in enumerate(turn.alternates, start=1):
                    print(f"        ({a_i}) {alt.text}")

            print()

        # If there are more turns than shown, say so.
        if len(convo.turns) > 5:
            print(f"    ... ({len(convo.turns) - 5} more turns not shown)")
            print()

    print("Done.")
    print()


# Standard Python pattern: run main() only if executed as a script.
if __name__ == "__main__":
    main()
