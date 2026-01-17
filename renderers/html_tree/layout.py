"""
Tree layout for HTML tree renderer.

Computes deterministic x/y pixel positions for nodes based on a simple tidy layout:
- Leaves assigned to left-to-right slots
- Parents centered above children
- Depth controls y position
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class LayoutConfig:
    # Fixed box width in pixels.
    # Fixed width makes layout predictable and keeps math simple.
    box_w: int = 325

    # Fixed box height in pixels.
    # Long text scrolls inside the box (CSS overflow: auto).
    box_h: int = 200

    # Horizontal gap between sibling boxes (space between columns).
    x_gap: int = 40

    # Vertical gap between parent/child levels (space between rows).
    y_gap: int = 70

    # Padding around the whole tree so boxes aren't glued to the edges.
    padding: int = 30


@dataclass
class NodePos:
    # One computed position for a node box (top-left corner).
    node_id: str
    x: int
    y: int


def build_children_index(nodes: Dict[str, Any]) -> Dict[str, List[str]]:
    # Build a lookup table: node_id -> list of child node_ids.
    # If a node has no children, use an empty list.
    # list(...) copies the list to avoid mutating the input JSON.
    return {node_id: list(node.get("children") or []) for node_id, node in nodes.items()}


def layout_tree(
    root_id: str,
    children_of: Dict[str, List[str]],
    cfg: LayoutConfig,
) -> Tuple[Dict[str, NodePos], int, int, List[Tuple[str, str]]]:
    """
    Compute x/y pixel positions for each node in the tree.

    Returns:
      nodes_xy: node_id -> NodePos
      width_px: canvas width
      height_px: canvas height
      edges: (parent_id, child_id) pairs for connectors
    """

    edges: List[Tuple[str, str]] = []
    leaf_x_slot: Dict[str, int] = {}
    next_leaf_slot = 0

    def dfs_assign_slots(node_id: str) -> Tuple[int, int]:
        nonlocal next_leaf_slot

        kids = children_of.get(node_id, [])
        for k in kids:
            edges.append((node_id, k))

        if not kids:
            leaf_x_slot[node_id] = next_leaf_slot
            next_leaf_slot += 1
            return leaf_x_slot[node_id], leaf_x_slot[node_id]

        spans = [dfs_assign_slots(k) for k in kids]
        min_slot = min(s[0] for s in spans)
        max_slot = max(s[1] for s in spans)
        return min_slot, max_slot

    dfs_assign_slots(root_id)

    nodes_xy: Dict[str, NodePos] = {}

    def dfs_place(node_id: str, depth: int) -> Tuple[int, int]:
        kids = children_of.get(node_id, [])

        if not kids:
            slot = leaf_x_slot[node_id]
            x = cfg.padding + slot * (cfg.box_w + cfg.x_gap)
            y = cfg.padding + depth * (cfg.box_h + cfg.y_gap)
            nodes_xy[node_id] = NodePos(node_id=node_id, x=x, y=y)
            return slot, slot

        spans = [dfs_place(k, depth + 1) for k in kids]
        min_slot = min(s[0] for s in spans)
        max_slot = max(s[1] for s in spans)

        center_slot = (min_slot + max_slot) / 2.0
        x = cfg.padding + int(center_slot * (cfg.box_w + cfg.x_gap))
        y = cfg.padding + depth * (cfg.box_h + cfg.y_gap)

        nodes_xy[node_id] = NodePos(node_id=node_id, x=x, y=y)
        return min_slot, max_slot

    dfs_place(root_id, 0)

    num_leafs = max(1, next_leaf_slot)
    width_px = cfg.padding * 2 + num_leafs * cfg.box_w + (num_leafs - 1) * cfg.x_gap

    max_y = 0
    for pos in nodes_xy.values():
        max_y = max(max_y, pos.y)

    height_px = max_y + cfg.box_h + cfg.padding

    return nodes_xy, width_px, height_px, edges
