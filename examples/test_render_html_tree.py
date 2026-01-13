"""
test_render_html_tree.py

Goal:
- Render a processed_tree_v1 JSON as a literal tree in HTML.
- Uses a real layout (computed x/y positions), instead of using nested HTML 
  lists and CSS to approximate a tree layout.
- Draws connectors with an SVG behind the boxes.

Usage:
  python examples\\test_render_html_tree.py examples\\test_processed.json examples\\test-files
"""

# annotations = stores type hints as strings to delay evaluation until runtime
from __future__ import annotations
# argparse = standard library CLI parsing (reads args like input/outdir)
import argparse
# html = standard library helpers for escaping text for HTML output 
import html
# json = standard library JSON parsing/serialization
import json
# dataclass = auto-generates __init__ and stores fields for simple data classes
from dataclasses import dataclass
# Path = path handling that works cleanly on Windows (and other OSes)
from pathlib import Path
# typing imports = type hints only 
from typing import Any, Dict, List, Tuple

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _safe_str(value: Any) -> str:
    # Converts any value to a string for safe display.
    # If value is None, return an empty string.
    # - Ensures "None" never appears in HTML output.
    return "" if value is None else str(value)


def sanitize_filename(name: str) -> str:
    # Creates a safe filename from a conversation title.
    # If filename is missing, return a non-empty default.
    # Replaces illegal characters and limits length to 120 characters.
    name = (name or "").strip() or "untitled"
    bad = '<>:"/\\|?*'                         # Forbidden Windows characters
    for ch in bad:
        name = name.replace(ch, "_")
    return name[:120].strip(" ._")


def get_role(node: Dict[str, Any]) -> str:
    # Pull "role" out of node["message"] if it exists.
    # If node has no message, return a default of "none".
    # If role is missing or invalid, return a default of "unknown".
    # "none" is an intentional role value for nodes without messages,
    # allowing consistent CSS styling and visible labels in the UI.
    msg = node.get("message")                  # node["message"] is optional
    if not msg:
        return "none"
    return _safe_str(msg.get("role", "unknown"))


def get_message_id(node: Dict[str, Any]) -> str:
    # Pull the source message id (if present) from node["message"].
    # If message id is missing or None, return an empty string.
    msg = node.get("message")
    if not msg:
        return ""
    return _safe_str(msg.get("source_message_id") or "")


def get_create_time(node: Dict[str, Any]) -> str:
    # Pull message create_time (if present). Keep it as a string.
    # If create_time is missing, return an empty string.
    msg = node.get("message")
    if not msg:
        return ""
    ct = msg.get("create_time")                # type varies in source data
    return _safe_str(ct) if ct is not None else ""


def extract_text(node: Dict[str, Any], max_len: int = 250) -> str:
    # Extract a short text preview for display inside a fixed-size box.
    # This function intentionally limits text length for UI performance.
    # Full message text should be rendered by final output exporters.
    # If node has no message, return "[no message]".
    # If text is empty or whitespace, return "[empty text]".
    # If text exceeds max_len, truncate it; remaining text scrolls in the UI.
    msg = node.get("message")
    if not msg:
        return "[no message]"
    text = _safe_str(msg.get("text", "")).strip() or "[empty text]"
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


# ---------------------------------------------------------------------------
# Layout model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LayoutConfig:
    # Fixed box width in pixels.
    # Fixed width keeps layout predictable and math simple.
    box_w: int = 220

    # Fixed box height in pixels.
    # Fixed height stabilizes layout and keeps connectors simple.
    # Long text scrolls inside the box (CSS overflow: auto).
    box_h: int = 120

    # Horizontal gap between sibling boxes (space between columns).
    x_gap: int = 40

    # Vertical gap between parent/child levels (space between rows).
    y_gap: int = 70

    # Padding around the tree so boxes are not glued to the edges.
    padding: int = 30


@dataclass
class NodePos:
    # Stores a node's computed top-left position in pixels.
    # node_id is kept to aid debugging and logging.
    node_id: str
    x: int
    y: int


# ---------------------------------------------------------------------------
# Tree layout (simple tidy layout)
# ---------------------------------------------------------------------------

def build_children_index(nodes: Dict[str, Any]) -> Dict[str, List[str]]:
    # Build a plain dict: node_id -> list of children ids.
    # The renderer expects "children" inside each node (already preprocessed).
    # list(...) copies it so we don't accidentally mutate the original JSON structure.
    return {node_id: list((node.get("children") or [])) for node_id, node in nodes.items()}


def layout_tree(
    root_id: str,
    children_of: Dict[str, List[str]],
    cfg: LayoutConfig,
) -> Tuple[Dict[str, NodePos], int, int, List[Tuple[str, str]]]:
    """
    Compute positions for each node.

    Strategy (simple tidy tree):
    - Each LEAF gets a sequential x "slot" (0, 1, 2, 3...).
    - Each INTERNAL node takes the midpoint slot of its children.
      (i.e., it is centered above its subtree).
    - y position is just depth * (box_h + y_gap).

    Why this works:
    - It's deterministic.
    - It creates an actual tree shape.
    - It avoids fragile CSS tricks and avoids needing a heavy layout library.

    Returns:
      positions: node_id -> NodePos (pixel positions for each node box)
      width_px: total canvas width in pixels
      height_px: total canvas height in pixels
      edges: list of (parent_id, child_id) used to draw SVG connector lines
    """

    # We collect edges while walking the tree so we can draw connectors later.
    edges: List[Tuple[str, str]] = []

    # leaf_x_slot maps a leaf node to its assigned column index.
    leaf_x_slot: Dict[str, int] = {}

    # next_leaf_slot is a counter we increment every time we see a leaf.
    next_leaf_slot = 0

    def dfs_assign_slots(node_id: str) -> Tuple[int, int]:
        """
        First DFS pass.

        Output: (min_slot, max_slot) for this node's subtree.

        - If node is a leaf:
            assign it the next slot and return (slot, slot)
        - If node has children:
            recurse into children, then return (min child slot, max child slot)

        Also: record edges (parent -> child) while we are here.
        """
        nonlocal next_leaf_slot  # we need to mutate the outer counter

        kids = children_of.get(node_id, [])     # children list (or empty)
        for k in kids:
            edges.append((node_id, k))          # record connector edge

        if not kids:
            # Leaf: give it the next available slot on the x-axis.
            leaf_x_slot[node_id] = next_leaf_slot
            next_leaf_slot += 1
            return leaf_x_slot[node_id], leaf_x_slot[node_id]

        # Internal node: gather spans from all children.
        spans = [dfs_assign_slots(k) for k in kids]

        # The subtree span is the min/max of the children spans.
        min_slot = min(s[0] for s in spans)
        max_slot = max(s[1] for s in spans)
        return min_slot, max_slot

    # Run first pass from root. We don't actually use root_span later,
    # but calling dfs_assign_slots populates leaf_x_slot + edges + next_leaf_slot.
    root_span = dfs_assign_slots(root_id)

    # positions will store final pixel coordinates for every node we place.
    positions: Dict[str, NodePos] = {}

    def dfs_place(node_id: str, depth: int) -> Tuple[int, int]:
        """
        Second DFS pass.

        This is where we convert "slots" into actual pixel x positions.

        Returns: (min_slot, max_slot) for the node's subtree again,
        because internal nodes need their children spans to compute their center.
        """
        kids = children_of.get(node_id, [])

        if not kids:
            # Leaf: we already assigned it a slot number.
            slot = leaf_x_slot[node_id]

            # Convert the slot number into pixel x.
            # Each slot is one box plus one horizontal gap.
            x = cfg.padding + slot * (cfg.box_w + cfg.x_gap)

            # y is depth-based (top level is depth=0).
            y = cfg.padding + depth * (cfg.box_h + cfg.y_gap)

            # Save this node position.
            positions[node_id] = NodePos(node_id=node_id, x=x, y=y)

            # Span of a leaf is just (slot, slot).
            return slot, slot

        # Internal node: place children first (so we know their span).
        spans = [dfs_place(k, depth + 1) for k in kids]

        # Compute min/max slots from children spans.
        min_slot = min(s[0] for s in spans)
        max_slot = max(s[1] for s in spans)

        # Center position is the midpoint between min_slot and max_slot.
        # We keep it float until the end, then int() it for stable pixels.
        center_slot = (min_slot + max_slot) / 2.0

        # Convert center slot into pixel x.
        x = cfg.padding + int(center_slot * (cfg.box_w + cfg.x_gap))

        # y is depth-based.
        y = cfg.padding + depth * (cfg.box_h + cfg.y_gap)

        # Save this node position.
        positions[node_id] = NodePos(node_id=node_id, x=x, y=y)

        # Return the span so parent nodes can center above us.
        return min_slot, max_slot

    # Run second pass from root with depth 0 (root is at the top).
    dfs_place(root_id, 0)

    # Canvas size calculation:

    # The number of leaf slots defines the horizontal size.
    num_leafs = max(1, next_leaf_slot)  # avoid 0 division / weird negative widths

    # width = left padding + (leaf_count * box_w) + (gaps between leaf columns) + right padding
    width_px = cfg.padding * 2 + num_leafs * cfg.box_w + (num_leafs - 1) * cfg.x_gap

    # Find the maximum y pixel coordinate among all nodes.
    # NOTE: this is the top-left y of boxes; we add box height later.
    max_depth = 0
    for pos in positions.values():
        max_depth = max(max_depth, pos.y)

    # Height includes:
    # - the lowest node's y position
    # - one box height
    # - bottom padding
    height_px = max_depth + cfg.box_h + cfg.padding

    # Return everything needed by the renderer.
    return positions, width_px, height_px, edges


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_processed_conversation(convo: Dict[str, Any], cfg: LayoutConfig) -> Tuple[str, str]:
    # Extract basic metadata for page header.
    title = _safe_str(convo.get("title") or "Untitled")               # title shown in h1 + filename
    convo_id = _safe_str(convo.get("conversation_id", "unknown"))     # used in subtitle + filename
    project = convo.get("project") or {}                              # project is optional
    project_name = _safe_str(project.get("name", ""))                 # show project name if present

    # The core graph data.
    nodes = convo.get("nodes") or {}                                  # node_id -> node dict
    root = convo.get("root_node_id")                                  # node id of root

    # Build the subtitle text under the title.
    subtitle_parts = [f"id={convo_id}", f"root={root or '??'}"]       # show id + root id
    if project_name:
        subtitle_parts.append(f"project={project_name}")              # include project name if we have one
    subtitle = " | ".join(subtitle_parts)                             # format nicely

    # If root is missing or points to nothing, output a valid HTML page with a comment.
    if not root or root not in nodes:
        page = build_full_html_page(title, subtitle, "<!-- invalid root -->")
        return title, page

    # Build the node_id -> children list index.
    children_of = build_children_index(nodes)

    # Compute box positions + canvas size + connector edges.
    positions, width_px, height_px, edges = layout_tree(root, children_of, cfg)

    # Build SVG connector lines.
    # SVG is placed behind the boxes so the boxes sit "on top" of the wires.
    svg_lines: List[str] = []
    for parent_id, child_id in edges:
        # Skip edges where we don't have a computed position (shouldn't happen, but defensive).
        if parent_id not in positions or child_id not in positions:
            continue

        # Parent position and child position.
        p = positions[parent_id]
        c = positions[child_id]

        # We draw a straight line from:
        #   bottom-center of the parent box
        # to:
        #   top-center of the child box
        x1 = p.x + cfg.box_w // 2         # parent center x
        y1 = p.y + cfg.box_h              # parent bottom y
        x2 = c.x + cfg.box_w // 2         # child center x
        y2 = c.y                          # child top y

        # Push a <line> element into our SVG.
        svg_lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#999" stroke-width="2" />'
        )

    # Wrap the line elements in an SVG tag sized to the whole canvas.
    svg = (
        f'<svg class="wires" width="{width_px}" height="{height_px}" '
        f'viewBox="0 0 {width_px} {height_px}" xmlns="http://www.w3.org/2000/svg">'
        + "".join(svg_lines)
        + "</svg>"
    )

    # Build the node boxes (absolutely positioned divs).
    boxes: List[str] = []
    for node_id, pos in positions.items():
        node = nodes.get(node_id, {})     # node dict from JSON (or empty if missing)
        role = get_role(node)             # user/assistant/tool/system/none
        msg_id = get_message_id(node)     # source message id (if any)
        ct = get_create_time(node)        # create_time (if any)
        text = extract_text(node)         # truncated message text

        # Escape all user-controlled data before putting it into HTML.
        # This prevents broken markup and avoids accidental HTML injection.
        esc_node_id = html.escape(node_id)
        esc_msg_id = html.escape(msg_id)
        esc_role = html.escape(role)
        esc_ct = html.escape(ct)

        # Escape text, then preserve line breaks by converting "\n" to "<br>".
        esc_text = html.escape(text).replace("\n", "<br>")

        # Build the HTML for one box.
        # style=left/top/width/height is what actually places it on the canvas.
        # class role-{role} is used to tint box background in CSS.
        boxes.append(
            f"""
            <div class="box role-{esc_role}" style="left:{pos.x}px; top:{pos.y}px; width:{cfg.box_w}px; height:{cfg.box_h}px;">
              <div class="idline"><span class="label">node</span> {esc_node_id}</div>
              <div class="idline muted"><span class="label">msg</span> {esc_msg_id or "(none)"}</div>
              <div class="metaline">
                <span class="pill">{esc_role}</span>
                <span class="meta">{("t=" + esc_ct) if ct else ""}</span>
              </div>
              <div class="text">{esc_text}</div>
            </div>
            """
        )

    # The canvas is a single positioned container holding:
    # - the SVG wires (z-index 0)
    # - the boxes (z-index 1)
    canvas = f"""
    <div class="canvas" style="width:{width_px}px; height:{height_px}px;">
      {svg}
      {''.join(boxes)}
    </div>
    """

    # Wrap everything into a complete HTML document.
    page = build_full_html_page(title, subtitle, canvas)
    return title, page


def build_full_html_page(title: str, subtitle: str, content_html: str) -> str:
    # Escape title/subtitle for safe insertion into HTML.
    esc_title = html.escape(title)
    esc_subtitle = html.escape(subtitle)

    # Return a full standalone HTML document string.
    # We embed CSS directly so the output is a single file you can open anywhere.
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{esc_title}</title>
<style>
:root {{
  /* Set default font to system fonts; looks fine on Windows. */
  font-family: system-ui, Segoe UI, Arial, sans-serif;
}}

body {{
  /* Basic page spacing and background. */
  margin: 0;
  padding: 16px;
  background: #f6f7f9;
}}

header {{
  /* Space between header and content. */
  margin-bottom: 12px;
}}

h1 {{
  /* Title styling. */
  font-size: 18px;
  margin: 0 0 4px 0;
}}

.subtitle {{
  /* Smaller, muted metadata line. */
  font-size: 13px;
  color: #666;
}}

.wrap {{
  /* This is the scroll container.
     The tree can be wider/taller than the viewport, so we allow scrolling. */
  overflow: auto;
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 12px;
}}

.canvas {{
  /* This is the positioning context for absolutely positioned boxes and SVG. */
  position: relative;
}}

.wires {{
  /* Put the SVG at the top-left of the canvas, behind boxes. */
  position: absolute;
  left: 0;
  top: 0;
  z-index: 0;
}}

.box {{
  /* Each node is an absolutely-positioned "card". */
  position: absolute;
  z-index: 1; /* boxes above the SVG wires */
  background: #fff;
  border: 1px solid #bbb;
  border-radius: 10px;
  padding: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  box-sizing: border-box; /* so width/height include padding and border */
  overflow: hidden;       /* keep internal layout clean */
}}

.idline {{
  /* Node id and message id lines. */
  font-size: 11px;
  word-break: break-all; /* long ids should wrap instead of overflowing */
}}

.label {{
  /* The bold "node"/"msg" label. */
  font-weight: 700;
  color: #666;
}}

.muted {{
  /* Slightly faded line for the message id. */
  color: #777;
}}

.metaline {{
  /* Role + timestamp row. */
  display: flex;
  gap: 6px;
  margin: 6px 0;
  align-items: center;
}}

.pill {{
  /* Small rounded role badge. */
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid #ddd;
  background: #f2f2f2;
}}

.meta {{
  /* Timestamp text. */
  font-size: 11px;
  color: #666;
}}

.text {{
  /* Main message preview area. */
  font-size: 12.5px;
  line-height: 1.35;
  margin-top: 6px;

  /* The box height is fixed, so this reserves space for id/meta lines above.
     Anything longer scrolls inside the box. */
  height: calc(100% - 52px);

  overflow: auto; /* text scrolls inside the fixed-height box */
  padding-right: 4px;
}}

/* Role tinting.
   These classes match: <div class="box role-{{role}}"> */
.role-user {{ background: #eef6ff; }}
.role-assistant {{ background: #f3fff0; }}
.role-tool {{ background: #f7f0ff; }}
.role-system {{ background: #fff6e8; }}
.role-none {{ background: #f2f2f2; }}
</style>
</head>

<body>
<header>
  <h1>{esc_title}</h1>
  <div class="subtitle">{esc_subtitle}</div>
</header>

<div class="wrap">
  {content_html}
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    # Build the command-line interface.
    parser = argparse.ArgumentParser(
        description="Render processed_tree_v1 JSON as a real positioned HTML tree."
    )

    # First CLI arg: input JSON path (either one convo object or a list of convo objects).
    parser.add_argument("input", help="processed JSON (object or list)")

    # Second CLI arg: output directory where .html files will be written.
    parser.add_argument("outdir", help="output folder")

    # Parse arguments into args.input and args.outdir.
    args = parser.parse_args()

    # Convert CLI strings to Path objects for safe Windows path handling.
    input_path = Path(args.input)
    outdir = Path(args.outdir)

    # Create output directory if it doesn't exist.
    outdir.mkdir(parents=True, exist_ok=True)

    # Read and parse the JSON file.
    raw = json.loads(input_path.read_text(encoding="utf-8"))

    # Normalise to a list, because the export might be either:
    # - a single object
    # - a list of objects
    conversations = raw if isinstance(raw, list) else [raw]

    # Use default layout config (constants defined above).
    cfg = LayoutConfig()

    # Count how many HTML files we actually write.
    written = 0

    # Iterate every conversation object.
    for i, convo in enumerate(conversations, start=1):
        # Skip non-dict entries (defensive; export should be dicts).
        if not isinstance(convo, dict):
            continue

        # Only render our expected processed schema.
        if convo.get("schema") != "processed_tree_v1":
            continue

        # Render to HTML (returns title + full HTML page).
        title, page = render_processed_conversation(convo, cfg)

        # Make a safe filename from the title.
        safe_title = sanitize_filename(title)

        # Pull conversation_id for filename (fallback if missing).
        convo_id = _safe_str(convo.get("conversation_id", f"unknown-{i}"))

        # Build output filename with an index prefix for stable ordering.
        out_path = outdir / f"{i:03d}__{safe_title}__{convo_id}.html"

        # Write HTML file to disk.
        out_path.write_text(page, encoding="utf-8")

        # Increment the "written files" counter.
        written += 1

    # Print a blunt summary line for the user.
    print(f"Wrote {written} HTML file(s) to: {outdir.resolve()}")


# Standard Python entrypoint guard:
# - If you import this file as a module, main() won't run.
# - If you run it as a script, main() will run.
if __name__ == "__main__":
    main()
