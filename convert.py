"""
convert.py

Stage 1 goals:
- Load a ChatGPT export-like JSON file
- Build internal Conversation models (model.py)
- Main path selection:
    - longest root->leaf path
    - tie-break: latest create_time
- Print a readable summary

Processing logic lives in processors/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from model import Conversation
from processors import parse_conversation


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a ChatGPT export JSON file into an internal model and print "
            "a readable summary (stage 1)."
        )
    )

    parser.add_argument(
        "input",
        nargs="?",
        default="examples/conversations_fake.json",
        help="Path to conversations.json (defaults to examples/conversations_fake.json)",
    )

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    raw_text = input_path.read_text(encoding="utf-8")
    raw_data = json.loads(raw_text)

    if not isinstance(raw_data, list):
        raise SystemExit("Expected the top-level JSON to be a list of conversations.")

    conversations: List[Conversation] = []
    for raw_convo in raw_data:
        if isinstance(raw_convo, dict):
            conversations.append(parse_conversation(raw_convo))

    print()
    print("=" * 72)
    print("ChatGPT Data Export Parser (Stage 1 summary)")
    print("=" * 72)
    print(f"Input: {input_path}")
    print(f"Conversations parsed: {len(conversations)}")
    print()

    for idx, convo in enumerate(conversations, start=1):
        print("-" * 72)
        print(f"[{idx}] Title: {convo.title}")
        print(f"    ID: {convo.id}")

        if convo.project and convo.project.get("name"):
            print(f"    Project: {convo.project.get('name')}")

        print(f"    Turns: {len(convo.turns)}")
        print()

        for t_index, turn in enumerate(convo.turns[:5], start=1):
            print(f"    Turn {t_index}:")
            print(f"      User: {turn.user.text}")

            if turn.assistant is not None:
                print(f"      Assistant: {turn.assistant.text}")
            else:
                print("      Assistant: [missing]")

            if turn.alternates:
                print("      Alternates:")
                for a_i, alt in enumerate(turn.alternates, start=1):
                    print(f"        ({a_i}) {alt.text}")

            print()

        if len(convo.turns) > 5:
            print(f"    ... ({len(convo.turns) - 5} more turns not shown)")
            print()

    print("Done.")
    print()


if __name__ == "__main__":
    main()
