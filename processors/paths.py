from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .mapping import get_timestamp


def find_root_id(mapping: Dict[str, Any]) -> Optional[str]:
    """
    Find the root node id. Some exports have a literal "root" key.
    Otherwise choose the node with parent == None.
    """
    if not mapping:
        return None

    if "root" in mapping:
        return "root"

    for node_id, node in mapping.items():
        if node.get("parent") is None:
            return node_id

    # Defensive fallback
    return next(iter(mapping.keys()))


def children_of(mapping: Dict[str, Any], node_id: str) -> List[str]:
    node = mapping.get(node_id) or {}
    kids = node.get("children", []) or []
    return [str(k) for k in kids]


def _path_latest_timestamp(mapping: Dict[str, Any], path: List[str]) -> float:
    """
    Tie-break timestamp for a path: the latest timestamp found along the path,
    preferring the leaf's timestamp if it exists.
    """
    best = float("-inf")
    for nid in path:
        node = mapping.get(nid) or {}
        ts = get_timestamp(node)
        if ts is not None:
            best = max(best, ts)
    return best


def compute_main_path(mapping: Dict[str, Any]) -> List[str]:
    """
    Choose a single "main path" from root to a leaf:

    - primary: longest path length
    - tie-break: latest create_time found on that path (max timestamp)
    """
    root = find_root_id(mapping)
    if root is None:
        return []

    best_path: List[str] = [root]
    best_len = 1
    best_ts = _path_latest_timestamp(mapping, best_path)

    stack: List[Tuple[str, List[str]]] = [(root, [root])]

    while stack:
        node_id, path = stack.pop()
        kids = children_of(mapping, node_id)

        if not kids:
            # Leaf path candidate
            plen = len(path)
            pts = _path_latest_timestamp(mapping, path)
            if plen > best_len or (plen == best_len and pts > best_ts):
                best_path = path
                best_len = plen
                best_ts = pts
            continue

        for kid in kids:
            stack.append((kid, path + [kid]))

    return best_path


def next_on_main_path(main_path: List[str], current_id: str) -> Optional[str]:
    """
    Given a main_path list, return the next node id after current_id.
    """
    try:
        i = main_path.index(current_id)
    except ValueError:
        return None
    if i + 1 >= len(main_path):
        return None
    return main_path[i + 1]
