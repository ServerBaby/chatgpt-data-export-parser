from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from renderers.html_tree.extract import safe_str, sanitize_filename
from renderers.html_tree.layout import LayoutConfig
from renderers.html_tree.render import render_processed_conversation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render processed_tree_v1 JSON as a real positioned HTML tree."
    )
    parser.add_argument("input", help="processed JSON (object or list)")
    parser.add_argument("outdir", help="output folder")
    args = parser.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    raw = json.loads(input_path.read_text(encoding="utf-8"))
    conversations = raw if isinstance(raw, list) else [raw]

    cfg = LayoutConfig()

    written = 0
    for i, convo in enumerate(conversations, start=1):
        if not isinstance(convo, dict):
            continue
        if convo.get("schema") != "processed_tree_v1":
            continue

        title, page = render_processed_conversation(convo, cfg)
        safe_title = sanitize_filename(title)
        convo_id = safe_str(convo.get("conversation_id", f"unknown-{i}"))

        out_path = outdir / f"{i:03d}__{safe_title}__{convo_id}.html"
        out_path.write_text(page, encoding="utf-8")
        written += 1

    print(f"Wrote {written} HTML file(s) to: {outdir.resolve()}")


if __name__ == "__main__":
    main()
