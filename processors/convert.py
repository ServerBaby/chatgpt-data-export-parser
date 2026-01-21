"""
convert.py

Processing pipeline entry point.

Goal:
- Load a ChatGPT export-like JSON file (conversations.json)
- For each conversation:
    - normalize it (shape cleanup + deterministic child order)
    - derive ids (NTBA mark ids, rewrite nodes dict keys + parent/children)
    - derive paths (mark main path longest + tie-break latest create_time)
- Assign conversation-level derived identifiers:
    - P#### = project bucket number (P0000 for non-project; projects oldest first)
    - C#### = conversation number within that project bucket (oldest first)
    - PC    = "P####-C####"
- Write processed_tree_v1 JSON ready for renderers.

This is intentionally defensive and stable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .normalize import normalize_conversation
from .derive_ids import apply_mark_ids
from .derive_paths import mark_main_path


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _project_key_from_raw(raw_convo: Dict[str, Any]) -> Optional[str]:
    """
    Default rule:
      - Use project.id if present
      - Else use project.name
      - Else treat as non-project (return None)
    """
    proj = raw_convo.get("project")
    if not isinstance(proj, dict):
        return None

    pid = proj.get("id")
    if isinstance(pid, str) and pid.strip():
        return f"id:{pid.strip()}"

    pname = proj.get("name")
    if isinstance(pname, str) and pname.strip():
        return f"name:{pname.strip()}"

    return None


def _convo_time_from_raw(raw_convo: Dict[str, Any]) -> Optional[float]:
    """
    Use conversation create_time for ordering if available.
    Missing/invalid create_time is treated as "unknown" and sorted last.
    """
    return _safe_float(raw_convo.get("create_time"))


def _order_key_time_then_id(raw_convo: Dict[str, Any]) -> Tuple[int, float, str]:
    """
    Oldest-first ordering with stable tie-break.
    - Known create_time first (0), unknown last (1)
    - then by create_time
    - then by conversation_id string
    """
    ct = _convo_time_from_raw(raw_convo)
    cid = raw_convo.get("conversation_id")
    cid_s = cid if isinstance(cid, str) else ""
    if ct is None:
        return (1, 9e18, cid_s)
    return (0, ct, cid_s)


def convert_file(input_path: Path) -> List[Dict[str, Any]]:
    """
    Converts a raw export JSON file into a list of processed_tree_v1 conversations.
    Also assigns conversation-level derived identifiers (P#### / C#### / PC).
    """
    raw_text = input_path.read_text(encoding="utf-8")
    raw_data = json.loads(raw_text)

    if not isinstance(raw_data, list):
        raise SystemExit("Expected the top-level JSON to be a list of conversations.")

    # Keep only dict conversations.
    raw_convos: List[Dict[str, Any]] = [c for c in raw_data if isinstance(c, dict)]

    # ---------
    # 1) Bucket conversations into projects (including P0000 non-project).
    # ---------
    buckets: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for rc in raw_convos:
        pk = _project_key_from_raw(rc)  # None => non-project
        buckets.setdefault(pk, []).append(rc)

    # ---------
    # 2) Order projects oldest-first (by earliest conversation create_time in the bucket).
    #    Non-project bucket is always P0000 and always included (even if empty).
    # ---------
    def bucket_min_time(bucket: List[Dict[str, Any]]) -> Tuple[int, float, str]:
        # Find earliest known time; if none known, bucket sorts last.
        times = [t for t in (_convo_time_from_raw(c) for c in bucket) if t is not None]
        if not times:
            # stable tie-break by project key string later
            return (1, 9e18, "")
        return (0, min(times), "")

    project_keys = [k for k in buckets.keys() if k is not None]

    # Sort project keys by: (has_time, min_time, key_string)
    project_keys_sorted = sorted(
        project_keys,
        key=lambda k: (
            bucket_min_time(buckets.get(k, []))[0],
            bucket_min_time(buckets.get(k, []))[1],
            str(k),
        ),
    )

    # Assign P labels
    P_label_of: Dict[Optional[str], str] = {None: "P0000"}
    for i, pk in enumerate(project_keys_sorted, start=1):
        P_label_of[pk] = f"P{i:04d}"

    # ---------
    # 3) For each bucket, sort conversations oldest-first and assign C#### within bucket.
    # ---------
    # Build an ordered list of (raw_convo, P_label, C_label)
    ordered_with_labels: List[Tuple[Dict[str, Any], str, str]] = []

    # Non-project first (P0000), then projects in P order
    bucket_order: List[Optional[str]] = [None] + project_keys_sorted

    for pk in bucket_order:
        convos_in_bucket = buckets.get(pk, [])
        convos_sorted = sorted(convos_in_bucket, key=_order_key_time_then_id)

        for j, rc in enumerate(convos_sorted, start=1):
            p_label = P_label_of.get(pk, "P0000")
            c_label = f"C{j:04d}"
            ordered_with_labels.append((rc, p_label, c_label))

    # ---------
    # 4) Run processing pipeline in this derived order and attach derived identifiers.
    # ---------
    processed: List[Dict[str, Any]] = []

    for raw_convo, p_label, c_label in ordered_with_labels:
        normalized = normalize_conversation(raw_convo)
        tree = apply_mark_ids(normalized)
        tree = mark_main_path(tree)

        tree.setdefault("derived", {})
        tree["derived"]["P"] = p_label
        tree["derived"]["C"] = c_label
        tree["derived"]["PC"] = f"{p_label}-{c_label}"

        processed.append(tree)

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert ChatGPT export conversations.json into processed_tree_v1 "
            "(render-ready tree format)."
        )
    )

    parser.add_argument(
        "input",
        nargs="?",
        default="examples/test_conversations.json",
        help="Path to conversations.json (defaults to examples/test_conversations.json)",
    )

    parser.add_argument(
        "--out",
        default="examples/test_processed_from_convert.json",
        help="Output JSON file path (defaults to examples/test_processed_from_convert.json)",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    out_path = Path(args.out)

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    processed = convert_file(input_path)

    out_path.write_text(
        json.dumps(processed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("Conversion complete")
    print("=" * 72)
    print(f"Input:  {input_path}")
    print(f"Output: {out_path}")
    print(f"Conversations: {len(processed)}")
    print()


if __name__ == "__main__":
    main()
