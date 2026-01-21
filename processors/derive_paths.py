"""
derive_paths.py

Stage: processed_tree_v1 -> annotate "main path" choice

Your rule:
- "Main path" is the LONGEST path (by node count or message count).
- Tie-break: if multiple longest paths exist, choose the one with the LATEST create_time.

This module does NOT change ids.
It only adds derived fields like:
- derived["is_main_path"] on nodes
- derived["main_child"] on parents (optional)
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def get_node_time(node: Dict[str, Any]) -> float:
    """
    Returns a sortable timestamp for tie-breaking.

    Uses:
    - node["message"]["create_time"] if present
    - otherwise 0.0
    """
    msg = node.get("message")
    if not msg:
        return 0.0
    ct = msg.get("create_time")
    try:
        return float(ct) if ct is not None else 0.0
    except Exception:
        return 0.0


def compute_best_path_from(
    nodes: Dict[str, Any],
    node_id: str,
) -> Tuple[int, float, Optional[str]]:
    """
    Returns:
      (best_len, best_latest_time, best_child)

    best_len:
      - length of best path starting at node_id (counts nodes)
    best_latest_time:
      - latest create_time anywhere along that best path
    best_child:
      - child id to follow for best path, or None if leaf
    """
    node = nodes.get(node_id, {})
    kids = node.get("children", []) or []

    if not kids:
        t = get_node_time(node)
        return (1, t, None)

    best_len = -1
    best_latest = -1.0
    best_child: Optional[str] = None

    for cid in kids:
        child_len, child_latest, _ = compute_best_path_from(nodes, cid)
        # If we go through this child, total length includes this node.
        total_len = 1 + child_len

        # Latest time along this path includes this node as well.
        latest_here = max(get_node_time(node), child_latest)

        if total_len > best_len:
            best_len = total_len
            best_latest = latest_here
            best_child = cid
        elif total_len == best_len:
            # Tie-break: latest create_time wins.
            if latest_here > best_latest:
                best_latest = latest_here
                best_child = cid

    return (best_len, best_latest, best_child)


def mark_main_path(tree: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adds:
      node["derived"]["is_main_path"] = True/False

    Returns the same dict (mutated), for convenience.
    """
    nodes: Dict[str, Any] = tree.get("nodes") or {}
    root = tree.get("root_node_id") or ""

    if not root or root not in nodes:
        return tree

    # We need memoization to avoid exponential recursion.
    memo: Dict[str, Tuple[int, float, Optional[str]]] = {}

    def best_from(nid: str) -> Tuple[int, float, Optional[str]]:
        if nid in memo:
            return memo[nid]
        memo[nid] = compute_best_path_from(nodes, nid)
        return memo[nid]

    # Walk from root choosing best child each time.
    current = root
    while True:
        node = nodes.get(current, {})
        node.setdefault("derived", {})
        node["derived"]["is_main_path"] = True

        _, _, best_child = best_from(current)
        if best_child is None:
            break

        current = best_child

    # Any nodes not visited should explicitly be False (nice for renderers).
    for nid, node in nodes.items():
        node.setdefault("derived", {})
        if "is_main_path" not in node["derived"]:
            node["derived"]["is_main_path"] = False

    return tree
