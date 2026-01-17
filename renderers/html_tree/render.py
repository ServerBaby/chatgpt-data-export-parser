"""
HTML rendering for the HTML tree visualiser.

Produces a standalone HTML page containing:
- a scrollable canvas
- an SVG "wires" layer behind
- absolutely positioned node boxes
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Tuple

from .extract import (
    extract_text,
    format_create_time_human,
    get_alternate_id,
    get_branch_id,
    get_create_time,
    get_message_id,
    get_role,
    get_turn_id,
    safe_str,
)
from .layout import LayoutConfig, build_children_index, layout_tree


def render_processed_conversation(
    convo: Dict[str, Any],
    cfg: LayoutConfig,
) -> Tuple[str, str]:
    title = safe_str(convo.get("title") or "Untitled")
    convo_id = safe_str(convo.get("conversation_id", "unknown"))

    project = convo.get("project") or {}
    project_name = safe_str(project.get("name", ""))

    nodes = convo.get("nodes") or {}
    root = convo.get("root_node_id")

    subtitle_parts = [f"id={convo_id}", f"root={root or '??'}"]
    if project_name:
        subtitle_parts.append(f"project={project_name}")
    subtitle = " | ".join(subtitle_parts)

    if not root or root not in nodes:
        page = build_full_html_page(title, subtitle, "<!-- invalid root -->")
        return title, page

    children_of = build_children_index(nodes)
    nodes_xy, width_px, height_px, edges = layout_tree(root, children_of, cfg)

    # -------------------------------------------------------------------------
    # SVG connector lines (family-tree style)
    # - one trunk down from parent
    # - one horizontal bar spanning all children
    # - one short vertical down to each child
    # -------------------------------------------------------------------------
    svg_lines: List[str] = []

    children_map: Dict[str, List[str]] = {}
    for parent_id, child_id in edges:
        children_map.setdefault(parent_id, []).append(child_id)

    for parent_id, child_ids in children_map.items():
        if parent_id not in nodes_xy:
            continue

        child_ids = [cid for cid in child_ids if cid in nodes_xy]
        if not child_ids:
            continue

        p = nodes_xy[parent_id]
        px = p.x + cfg.box_w // 2
        py_bottom = p.y + cfg.box_h

        # One child: straight line
        if len(child_ids) == 1:
            c = nodes_xy[child_ids[0]]
            cx = c.x + cfg.box_w // 2
            cy_top = c.y
            svg_lines.append(
                f'<line x1="{px}" y1="{py_bottom}" x2="{cx}" y2="{cy_top}" '
                f'stroke="#b0b0b0" stroke-width="2" />'
            )
            continue

        # Multiple children: trunk + bar + drops
        child_centers: List[int] = []
        child_top_y: int | None = None
        for cid in child_ids:
            c = nodes_xy[cid]
            child_centers.append(c.x + cfg.box_w // 2)
            child_top_y = c.y if child_top_y is None else min(child_top_y, c.y)

        min_x = min(child_centers)
        max_x = max(child_centers)

        junction_y = py_bottom + (cfg.y_gap // 2)

        # Parent trunk
        svg_lines.append(
            f'<line x1="{px}" y1="{py_bottom}" x2="{px}" y2="{junction_y}" '
            f'stroke="#b0b0b0" stroke-width="2" />'
        )

        # Horizontal bar
        svg_lines.append(
            f'<line x1="{min_x}" y1="{junction_y}" x2="{max_x}" y2="{junction_y}" '
            f'stroke="#b0b0b0" stroke-width="2" />'
        )

        # Drops to each child
        for cx in child_centers:
            svg_lines.append(
                f'<line x1="{cx}" y1="{junction_y}" x2="{cx}" y2="{child_top_y}" '
                f'stroke="#b0b0b0" stroke-width="2" />'
            )

    svg = (
        f'<svg class="wires" width="{width_px}" height="{height_px}" '
        f'viewBox="0 0 {width_px} {height_px}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        + "".join(svg_lines)
        + "</svg>"
    )

    boxes: List[str] = []
    for node_id, pos in nodes_xy.items():
        node = nodes.get(node_id, {})

        role = get_role(node)
        msg_id = get_message_id(node)
        ct = get_create_time(node)
        human_ts = format_create_time_human(ct)

        branch_id = get_branch_id(node)
        turn_id = get_turn_id(node)
        alternate_id = get_alternate_id(node)

        text = extract_text(node)

        esc_node_id = html.escape(node_id)
        esc_msg_id = html.escape(msg_id)
        esc_role = html.escape(role)
        esc_ct = html.escape(ct)

        esc_branch_id = html.escape(branch_id)
        esc_turn_id = html.escape(turn_id)
        esc_alternate_id = html.escape(alternate_id)
        esc_human_ts = html.escape(human_ts)

        esc_text = html.escape(text).replace("\n", "<br>")

        ct_value = esc_ct if ct else ""

        boxes.append(
            f"""
            <div class="box role-{esc_role}"
                 style="left:{pos.x}px; top:{pos.y}px; width:{cfg.box_w}px;
                        height:{cfg.box_h}px;">
              <div class="meta">
                <div class="kv"><span class="label">node_id</span> <span class="value">{esc_node_id}</span></div>
                <div class="kv"><span class="label">msg_id</span> <span class="value">{esc_msg_id or "(none)"}</span></div>
                <div class="kv"><span class="label">role</span> <span class="value">{esc_role}</span></div>
                <div class="kv"><span class="label">creation_time</span> <span class="value">{ct_value}</span></div>

                <div class="gap"></div>

                <div class="kv"><span class="label">branch_id</span> <span class="value">{esc_branch_id}</span></div>
                <div class="kv"><span class="label">turn_id</span> <span class="value">{esc_turn_id}</span></div>
                <div class="kv"><span class="label">alternate_id</span> <span class="value">{esc_alternate_id}</span></div>
                <div class="kv"><span class="label">timestamp</span> <span class="value">{esc_human_ts}</span></div>

                <div class="gap"></div>
              </div>

              <div class="text">{esc_text}</div>
            </div>
            """
        )

    canvas = f"""
    <div class="canvas" style="width:{width_px}px; height:{height_px}px;">
      {svg}
      {''.join(boxes)}
    </div>
    """

    page = build_full_html_page(title, subtitle, canvas)
    return title, page


def build_full_html_page(title: str, subtitle: str, content_html: str) -> str:
    esc_title = html.escape(title)
    esc_subtitle = html.escape(subtitle)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{esc_title}</title>
<style>
:root {{
  font-family: system-ui, Segoe UI, Arial, sans-serif;
}}

body {{
  margin: 0;
  padding: 16px;
  background: #f2f3f6;
}}

header {{
  margin-bottom: 12px;
}}

h1 {{
  font-size: 18px;
  margin: 0 0 4px 0;
}}

.subtitle {{
  font-size: 13px;
  color: #5f5f5f;
}}

.wrap {{
  overflow: auto;
  background: white;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  padding: 12px;
}}

.canvas {{
  position: relative;
}}

.wires {{
  position: absolute;
  left: 0;
  top: 0;
  z-index: 0;
}}

.box {{
  position: absolute;
  z-index: 1;
  background: #ffffff;
  border: 2px solid #b0b0b0;
  border-radius: 10px;
  padding: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  box-sizing: border-box;
  overflow: hidden;
}}

.kv {{
  font-size: 11px;
  word-break: break-all;
  margin-bottom: 2px;
}}

.label {{
  font-weight: 700;
  color: #5f5f5f;
  margin-right: 6px;
}}

.value {{
  font-weight: 400;
  color: #222;
}}

.gap {{
  height: 8px; /* your “empty line” */
}}

/* --- Hover-collapse behaviour --- */
/* Default: hide metadata, let text take full height */
.meta {{
  display: none;
}}

.box:not(:hover) .text {{
  height: calc(100% - 0px);
}}

/* On hover: show metadata and shrink text area */
.box:hover .meta {{
  display: block;
}}

/* This is the only "tuning knob" you might ever need:
   If text area becomes too small/large on hover, adjust 138px. */
.box:hover .text {{
  height: calc(100% - 138px);
}}

.text {{
  font-size: 12.5px;
  line-height: 1.35;
  margin-top: 6px;
  overflow: auto;
  padding-right: 4px;
}}

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
