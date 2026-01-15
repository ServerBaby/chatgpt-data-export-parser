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

# annotations = stores type hints as strings to delay evaluation
from __future__ import annotations
# argparse = standard library CLI parsing (reads args like input/outdir)
import argparse
# html = standard library helpers for escaping text for HTML output
import html
# json = standard library JSON parsing/serialization
import json
# dataclass = auto-generates __init__ for simple data classes
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


# -----------------------------------------------------------------------------
# Layout model
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class LayoutConfig:
    # Fixed box width in pixels.
    # Fixed width makes layout predictable and keeps math simple.
    box_w: int = 220

    # Fixed box height in pixels.
    # This is a deliberate design choice: 
    # - stable layout, no reflow, easy connectors.
    # Long text scrolls inside the box (CSS overflow: auto).
    box_h: int = 120

    # Horizontal gap between sibling boxes (space between columns).
    x_gap: int = 40

    # Vertical gap between parent/child levels (space between rows).
    y_gap: int = 70

    # Padding around the whole tree so boxes aren't glued to the edges.
    padding: int = 30


@dataclass
class NodePos:
    # One computed position for a node box (top-left corner).
    # node_id is stored to make debugging and logging easier.
    node_id: str
    x: int
    y: int


# -----------------------------------------------------------------------------
# Tree layout (simple tidy layout)
# -----------------------------------------------------------------------------

def build_children_index(nodes: Dict[str, Any]) -> Dict[str, List[str]]:
    # Build a lookup table: node_id -> list of child node_ids.
    # If a node has no children, use an empty list.
    # list(...) copies the list to avoid mutating the input JSON.
    return (
        {node_id: list(node.get("children") or [])
         for node_id, node in nodes.items()}
    )


def layout_tree(
    root_id: str,
    children_of: Dict[str, List[str]],
    cfg: LayoutConfig,
) -> Tuple[Dict[str, NodePos], int, int, List[Tuple[str, str]]]:
    """
    Compute x/y pixel positions for each node in the tree.

    Layout rules:
    - Leaf nodes are placed left to right in numbered slots.
    - Parent nodes are centered above their children.
    - Vertical position depends only on depth in the tree.

    Design intent:
    - Deterministic layout for the same input tree.
    - Clear tree shape without CSS list hacks or external layout libraries.

    Returns:
      nodes_xy: node_id -> NodePos (top-left pixel position for each node box)
      width_px: total canvas width in pixels
      height_px: total canvas height in pixels
      edges: (parent_id, child_id) pairs for SVG connector lines
    """

    # Store parent -> child pairs for drawing connector lines later.
    edges: List[Tuple[str, str]] = []

    # Map each leaf node_id to an assigned horizontal slot number.
    leaf_x_slot: Dict[str, int] = {}

    # Counter used to assign the next available leaf slot.
    next_leaf_slot = 0

    def dfs_assign_slots(node_id: str) -> Tuple[int, int]:
        """
        First depth-first search pass: assign slot numbers to leaf nodes.

        Returns: (min_slot, max_slot) for this node's subtree span.

        Rules:
        - If node is a leaf:
            assign it the next slot and return (slot, slot)
        - If node has children:
            recurse into children, then return (min child slot, max child slot)
        - Record edges (parent -> child) for connector drawing.
        """
        nonlocal next_leaf_slot                 # mutate the outer counter

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

    # Run first pass from root.
    # This populates leaf_x_slot, edges, and next_leaf_slot.
    dfs_assign_slots(root_id)

    # nodes_xy stores the final top-left pixel position for every node.
    nodes_xy: Dict[str, NodePos] = {}

    def dfs_place(node_id: str, depth: int) -> Tuple[int, int]:
        """
        Second depth-first search pass: assign pixel positions.

        This pass uses leaf_x_slot from the first pass.
        It places children first so parent nodes can be centered.

        Returns: (min_slot, max_slot) for this node's subtree span.
        - internal nodes need their children spans to compute their center.
        """
        kids = children_of.get(node_id, [])

        if not kids:
            # Leaf node: leaf_x_slot already contains horizontal slot index.
            slot = leaf_x_slot[node_id]

            # x is based on the slot number (column index).
            # Each column width is one box plus one horizontal gap.
            x = cfg.padding + slot * (cfg.box_w + cfg.x_gap)

            # y is based on depth (row index).
            # Each row height is one box plus one vertical gap.
            y = cfg.padding + depth * (cfg.box_h + cfg.y_gap)

            # Store the top-left corner for this node's box.
            nodes_xy[node_id] = NodePos(node_id=node_id, x=x, y=y)

            # Span of a leaf is just its own slot (slot, slot).
            return slot, slot

        # Internal node: place all children first to get their slot spans.
        spans = [dfs_place(k, depth + 1) for k in kids]

        # Compute min/max slots from children spans.
        min_slot = min(s[0] for s in spans)
        max_slot = max(s[1] for s in spans)

        # center_slot is the midpoint between min_slot and max_slot.
        # This centers the parent above all of its descendants.
        center_slot = (min_slot + max_slot) / 2.0

        # Convert slot midpoint to pixels.
        # int(...) snaps to a stable integer pixel coordinate (x).
        x = cfg.padding + int(center_slot * (cfg.box_w + cfg.x_gap))

        # y is based on this node's depth.
        y = cfg.padding + depth * (cfg.box_h + cfg.y_gap)

        # Store the top-left corner for this node's box.
        nodes_xy[node_id] = NodePos(node_id=node_id, x=x, y=y)

        # Return this subtree span so the parent can center above it.
        return min_slot, max_slot

    # Run second pass from root with depth 0 (root starts at the top).
    dfs_place(root_id, 0)

    # Canvas size calculation:

    # num_leafs is the number of leaf slots (at least 1 for an empty tree).
    # This prevents negative widths when there are no leaves.
    num_leafs = max(1, next_leaf_slot)

    # Total width includes padding, box widths, and gaps between columns.
    width_px = cfg.padding * 2 + num_leafs * cfg.box_w
    width_px += (num_leafs - 1) * cfg.x_gap

    # Find the maximum top-left y pixel coordinate among all positioned nodes.
    max_y = 0
    for pos in nodes_xy.values():
        max_y = max(max_y, pos.y)

    # Height includes the lowest node, one box height, and bottom padding.
    height_px = max_y + cfg.box_h + cfg.padding

    # Return everything needed by the renderer:
    # - nodes_xy for absolutely-positioned boxes
    # - canvas width/height for the container and SVG
    # - edges for drawing connector lines
    return nodes_xy, width_px, height_px, edges


# -----------------------------------------------------------------------------
# HTML rendering
# -----------------------------------------------------------------------------

def render_processed_conversation(
    convo: Dict[str, Any],
    cfg: LayoutConfig,
) -> Tuple[str, str]:
    # Extract conversation title for:
    # - the <h1> page heading
    # - the output filename
    title = _safe_str(convo.get("title") or "Untitled")

    # Extract conversation_id for:
    # - the subtitle line
    # - the output filename (helps disambiguate same-title conversations)
    convo_id = _safe_str(convo.get("conversation_id", "unknown"))

    # project is optional in processed_tree_v1.
    # If missing, default to empty dict so .get(...) works safely.
    project = convo.get("project") or {}

    # Extract project name for subtitle (only shown if non-empty).
    project_name = _safe_str(project.get("name", ""))

    # nodes is the main tree data:
    # node_id -> node dict containing parent/children/message metadata.
    nodes = convo.get("nodes") or {}

    # root_node_id is the node_id of the top-most node in the tree.
    root = convo.get("root_node_id")

    # Build the subtitle line shown under the title.
    # This is diagnostic metadata to help identify what was rendered.
    subtitle_parts = [f"id={convo_id}", f"root={root or '??'}"]
    if project_name:
        subtitle_parts.append(f"project={project_name}")
    subtitle = " | ".join(subtitle_parts)

    # If root is missing or not present in nodes:
    # - still output a valid HTML file
    # - show a small HTML comment for debugging
    if not root or root not in nodes:
        page = build_full_html_page(title, subtitle, "<!-- invalid root -->")
        return title, page

    # Convert nodes into a simpler index used by the layout function:
    # node_id -> list of child node_ids
    children_of = build_children_index(nodes)

    # Compute:
    # - nodes_xy: top-left pixel position of each node box
    # - width/height: size of the canvas area in pixels
    # - edges: list of (parent_id, child_id) connectors
    nodes_xy, width_px, height_px, edges = layout_tree(root, children_of, cfg)

    # Build SVG connector lines.
    # SVG is a graphics layer. It sits behind the HTML boxes.
    svg_lines: List[str] = []
    for parent_id, child_id in edges:
        # Defensive guard:
        # Skip edges that point to nodes that did not get a position.
        if parent_id not in nodes_xy or child_id not in nodes_xy:
            continue

        # Look up pixel positions for the parent and child boxes.
        p = nodes_xy[parent_id]
        c = nodes_xy[child_id]

        # Draw a straight line from parent to child.
        # Start: bottom-center of parent box.
        # End: top-center of child box.
        x1 = p.x + cfg.box_w // 2
        y1 = p.y + cfg.box_h
        x2 = c.x + cfg.box_w // 2
        y2 = c.y

        # Add one SVG <line> element.
        # stroke controls line colour. stroke-width controls line thickness.
        svg_lines.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="#b0b0b0" stroke-width="2" />'
        )

    # Wrap all connector lines in one SVG element.
    # width/height and viewBox match the canvas pixel space exactly.
    # xmlns declares the SVG XML namespace:
    # - necessary so that the browser parses <line> etc as SVG.
    svg = (
        f'<svg class="wires" width="{width_px}" height="{height_px}" '
        f'viewBox="0 0 {width_px} {height_px}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        + "".join(svg_lines)
        + "</svg>"
    )

    # Build the node boxes.
    # Each box is one absolutely-positioned <div>.
    boxes: List[str] = []
    for node_id, pos in nodes_xy.items():
        # Fetch the node dict from the processed JSON.
        # If missing for some reason, use {} so helper getters do not crash.
        node = nodes.get(node_id, {})

        # role controls CSS tinting and the visible role pill.
        # role is usually: user / assistant / tool / system / none
        role = get_role(node)

        # msg_id links the processed node back to the original export message.
        msg_id = get_message_id(node)

        # ct is create_time (if present). This is used for display only.
        ct = get_create_time(node)

        # text is a short preview for the fixed-size UI box.
        # This is intentionally not the full message for huge conversations.
        text = extract_text(node)

        # Escape values before inserting into HTML.
        # This prevents:
        # - broken HTML when text contains < or >
        # - accidental HTML/script injection when opening the file
        esc_node_id = html.escape(node_id)
        esc_msg_id = html.escape(msg_id)
        esc_role = html.escape(role)
        esc_ct = html.escape(ct)

        # Escape message preview, then preserve newlines for readability.
        # HTML ignores raw \n, so convert \n into <br>.
        esc_text = html.escape(text).replace("\n", "<br>")

        # Build one HTML box.
        # left/top place the box using the computed pixel positions.
        # width/height match cfg.box_w/cfg.box_h for layout consistency.
        # role-{role} drives background colour in CSS.
        boxes.append(
            f"""
            <div class="box role-{esc_role}"
                 style="left:{pos.x}px; top:{pos.y}px; width:{cfg.box_w}px;
                        height:{cfg.box_h}px;">
              <div class="idline"><span class="label">node</span> {esc_node_id}
              </div>
              <div class="idline muted"><span class="label">msg</span>
                {esc_msg_id or "(none)"}
              </div>
              <div class="metaline">
                <span class="pill">{esc_role}</span>
                <span class="meta">{("t=" + esc_ct) if ct else ""}</span>
              </div>
              <div class="text">{esc_text}</div>
            </div>
            """
        )

    # Build the canvas container.
    # This is one positioned <div> that holds:
    # - the SVG wires (z-index 0, behind)
    # - the HTML boxes (z-index 1, in front)
    canvas = f"""
    <div class="canvas" style="width:{width_px}px; height:{height_px}px;">
      {svg}
      {''.join(boxes)}
    </div>
    """

    # Wrap the canvas into a complete standalone HTML document.
    page = build_full_html_page(title, subtitle, canvas)
    return title, page


def build_full_html_page(title: str, subtitle: str, content_html: str) -> str:
    # Escape title/subtitle before inserting into the HTML template.
    # This prevents the <title> tag and header from breaking on special chars.
    esc_title = html.escape(title)
    esc_subtitle = html.escape(subtitle)

    # Return a complete standalone HTML page as one string.
    # CSS is embedded so the output is a single file (easy to share and open).
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{esc_title}</title>
<style>
:root {{
  /* Default font stack. Looks reasonable on Windows and other OSes. */
  font-family: system-ui, Segoe UI, Arial, sans-serif;
}}

body {{
  /* Page padding and neutral background colour. */
  margin: 0;
  padding: 16px;
  background: #f2f3f6;
}}

header {{
  /* Space between header and the scrollable tree area. */
  margin-bottom: 12px;
}}

h1 {{
  /* Title styling. */
  font-size: 18px;
  margin: 0 0 4px 0;
}}

.subtitle {{
  /* Smaller metadata line under the title. */
  font-size: 13px;
  color: #5f5f5f;
}}

.wrap {{
  /* Scroll container for the tree.
     The canvas may be larger than the browser viewport. */
  overflow: auto;
  background: white;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  padding: 12px;
}}

.canvas {{
  /* Positioning context for absolute children (SVG + boxes). */
  position: relative;
}}

.wires {{
  /* SVG connector layer. Positioned at (0,0) inside the canvas. */
  position: absolute;
  left: 0;
  top: 0;
  z-index: 0;
}}

.box {{
  /* Each node is one absolutely-positioned card. */
  position: absolute;
  z-index: 1; /* boxes sit above the SVG */
  background: #ffffff;
  border: 2px solid #b0b0b0;
  border-radius: 10px;
  padding: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);

  /* Include padding/border inside the fixed width/height. */
  box-sizing: border-box;

  /* Prevent internal content from expanding the box size. */
  overflow: hidden;
}}

.idline {{
  /* Node id and message id lines (small text). */
  font-size: 11px;

  /* Long ids wrap instead of overflowing outside the box. */
  word-break: break-all;
}}

.label {{
  /* Bold label text: "node" and "msg". */
  font-weight: 700;
  color: #5f5f5f;
}}

.muted {{
  /* Slightly faded line for the message id. */
  color: #6f6f6f;
}}

.metaline {{
  /* Row holding the role pill and timestamp. */
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
  border: 1px solid #d0d0d0;
  background: #e5e5e5;
}}

.meta {{
  /* Timestamp text. */
  font-size: 11px;
  color: #5f5f5f;
}}

.text {{
  /* Main message preview area inside a box. */
  font-size: 12.5px;
  line-height: 1.35;
  margin-top: 6px;

  /* Reserve space for id/meta lines above.
     The remaining vertical space is the text area. */
  height: calc(100% - 52px);

  /* Scroll inside the box for overflow text. */
  overflow: auto;
  padding-right: 4px;
}}

/* Role tinting.
   These classes match: <div class="box role-ROLE"> */
.role-user {{ background: #ddeeff; }}
.role-assistant {{ background: #e6f6e1; }}
.role-tool {{ background: #ece3f6; }}
.role-system {{ background: #f6ebd6; }}
.role-none {{ background: #e5e5e5; }}
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


# -----------------------------------------------------------------------------
# Command-line Interface
# -----------------------------------------------------------------------------

def main() -> None:
    # Define the command-line arguments for this script.
    # This is a simple "examples" runner, so errors are allowed to raise.
    parser = argparse.ArgumentParser(
        description="Render processed_tree_v1 JSON as a real positioned HTML "
                    "tree."
    )

    # Arg 1: input JSON path.
    # This can be:
    # - one processed conversation object
    # - a list of processed conversation objects
    parser.add_argument("input", help="processed JSON (object or list)")

    # Arg 2: output directory path.
    # One .html file is written per conversation that matches the schema.
    parser.add_argument("outdir", help="output folder")

    # Parse arguments into args.input and args.outdir.
    args = parser.parse_args()

    # Convert input/output strings into Path objects.
    # Path keeps Windows path handling clean (slashes, joins, etc).
    input_path = Path(args.input)
    outdir = Path(args.outdir)

    # Create output directory if it does not exist.
    outdir.mkdir(parents=True, exist_ok=True)

    # Read the whole file and parse it as JSON.
    raw = json.loads(input_path.read_text(encoding="utf-8"))

    # Normalize to a list:
    # - if raw is already a list, use it
    # - otherwise wrap the single object in a list
    conversations = raw if isinstance(raw, list) else [raw]

    # Use default layout settings (box sizes, gaps, padding).
    cfg = LayoutConfig()

    # Count how many HTML files are actually written to disk.
    written = 0

    # Iterate through the list entries.
    # NOTE: i is the index in the *input list*.
    # If entries are skipped, the output numbering can have gaps.
    for i, convo in enumerate(conversations, start=1):
        # Skip invalid entries (defensive; input should be dict objects).
        if not isinstance(convo, dict):
            continue

        # Skip anything that is not the expected processed schema.
        if convo.get("schema") != "processed_tree_v1":
            continue

        # Render one conversation to a full HTML page string.
        title, page = render_processed_conversation(convo, cfg)

        # Build a safe filename fragment from the conversation title.
        safe_title = sanitize_filename(title)

        # Use conversation_id in the filename for uniqueness.
        # Fall back to "unknown-N" if it is missing.
        convo_id = _safe_str(convo.get("conversation_id", f"unknown-{i}"))

        # Output filename includes:
        # - a 3-digit index for stable ordering
        # - the sanitized title
        # - the conversation_id
        out_path = outdir / f"{i:03d}__{safe_title}__{convo_id}.html"

        # Write the HTML file.
        out_path.write_text(page, encoding="utf-8")
        written += 1

    # Print a simple summary for the user.
    print(f"Wrote {written} HTML file(s) to: {outdir.resolve()}")

# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------

# Standard Python entrypoint guard:
# - When imported, this file defines functions but does not run.
# - When executed, main() runs.
if __name__ == "__main__":
    main()


# -----------------------------------------------------------------------------
# Extra Notes
# -----------------------------------------------------------------------------

"""
Notes on error handling and filenames:

This script is intended as a test / example renderer, not a production CLI.

It assumes the input JSON already exists and is valid, because it is generated
by earlier test steps using a known, correctly formatted processed_tree_v1
structure. For that reason, this script does not perform explicit validation
or error recovery.

If:
- the input file does not exist
- the JSON is malformed
- the output directory cannot be created

Python will raise an exception and exit. This is intentional to keep the example
code simple and focused on rendering behavior rather than defensive I/O logic.

Filename numbering behavior:

Output filenames are prefixed using the index of each item in the input list.
Entries that are skipped (for example, non-dict values or objects with an
unexpected schema) still advance the index counter.

This can result in gaps in the numbering (e.g. 001__, 004__). This is not a bug.
It preserves stable ordering relative to the original input data.

Using a separate counter for written files would produce contiguous numbering,
but would change filename behavior and is therefore not done here.
"""
