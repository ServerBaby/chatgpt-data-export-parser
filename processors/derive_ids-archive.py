"""
derive_ids.py

Stage: NORMALIZED TREE -> DERIVED IDS (NTBA) + MARK IDS

This stage computes:
- A = alternate label among siblings (chronological 1..X) as "A i of X"
- B = branch count along the path from root (counts ancestors with >1 child)
- T = chronological turn index across the whole conversation
- N = DFS order index across the whole tree

Then it builds:
- mark_id string per node, e.g. "N0012-T0015-B03-A 2 of 4"
- a rewritten tree where:
    - nodes dict keys are mark_ids
    - parent/children values are mark_ids
    - source_node_id remains the original
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def format_human_time(ts: Optional[float]) -> str:
    """
    Converts epoch seconds to: "DD Mon YYYY HH:MM:SS" (UTC).
    If ts is missing, returns "".
    """
    if ts is None:
        return ""
    try:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return dt.strftime("%d %b %Y %H:%M:%S")
    except Exception:
        return ""


def sort_children_by_time(nodes: Dict[str, Any], child_ids: List[str]) -> List[str]:
    """
    Deterministic child order:
    - by create_time (None last)
    - then by source_node_id (stable tie-break)
    """
    def key(cid: str) -> Tuple[int, float, str]:
        n = nodes.get(cid, {})
        msg = (n.get("message") or {})
        ct = msg.get("create_time")
        if ct is None:
            return (1, 9e18, cid)
        try:
            return (0, float(ct), cid)
        except Exception:
            return (1, 9e18, cid)

    return sorted(list(child_ids), key=key)


def compute_A_labels(nodes: Dict[str, Any], root_id: str) -> Dict[str, str]:
    """
    A label exists whenever a node has a parent.
    It is the child's position among its siblings after deterministic sorting.

    If there is only one sibling, the label is still "A 1 of 1".
    """
    # Build parent -> [children] map.
    parent_to_children: Dict[str, List[str]] = {}
    for node_id, node in nodes.items():
        parent = node.get("parent")
        if parent is None:
            continue
        parent_to_children.setdefault(parent, []).append(node_id)

    A: Dict[str, str] = {}

    for parent_id, kids in parent_to_children.items():
        kids_sorted = sort_children_by_time(nodes, kids)
        total = len(kids_sorted)

        for idx, child_id in enumerate(kids_sorted, start=1):
            A[child_id] = f"A {idx} of {total}"

        # Also rewrite the stored child order (so everyone downstream agrees).
        # This is important for consistent left->right rendering.
        if parent_id in nodes:
            nodes[parent_id]["children"] = kids_sorted

    # Root has no A label (no parent).
    if root_id in A:
        del A[root_id]

    return A


def compute_B_labels(nodes: Dict[str, Any], root_id: str) -> Dict[str, str]:
    """
    B is the number of branchpoints along the route from root to this node.

    A "branchpoint" is a node with >1 child.

    Root is "B00".
    """
    B: Dict[str, int] = {}

    def dfs(node_id: str, branch_count: int) -> None:
        B[node_id] = branch_count

        kids = nodes.get(node_id, {}).get("children", []) or []
        is_branchpoint = len(kids) > 1

        next_branch_count = branch_count + (1 if is_branchpoint else 0)
        for cid in kids:
            dfs(cid, next_branch_count)

    dfs(root_id, 0)

    return {nid: f"B{B[nid]:02d}" for nid in B}


def compute_T_labels(nodes: Dict[str, Any]) -> Dict[str, str]:
    """
    T is global chronological order across the whole conversation.

    Sorting:
    - nodes WITH create_time come first, sorted by create_time then node_id
    - nodes WITHOUT create_time come last, sorted by node_id

    This keeps "real messages" in the timeline order, but still assigns T to
    structural nodes so they have a complete NTBA string.
    """
    def key(nid: str) -> Tuple[int, float, str]:
        msg = (nodes.get(nid, {}).get("message") or {})
        ct = msg.get("create_time")
        if ct is None:
            return (1, 9e18, nid)
        try:
            return (0, float(ct), nid)
        except Exception:
            return (1, 9e18, nid)

    ordered = sorted(list(nodes.keys()), key=key)

    T: Dict[str, str] = {}
    for i, nid in enumerate(ordered, start=1):
        T[nid] = f"T{i:04d}"
    return T


def compute_N_labels(nodes: Dict[str, Any], root_id: str) -> Dict[str, str]:
    """
    N is a DFS (depth-first) numbering over the tree.

    DFS uses the already-normalized children order (which we fix in compute_A_labels).
    """
    N: Dict[str, str] = {}
    counter = 0

    def dfs(nid: str) -> None:
        nonlocal counter
        counter += 1
        N[nid] = f"N{counter:04d}"

        kids = nodes.get(nid, {}).get("children", []) or []
        for cid in kids:
            dfs(cid)

    dfs(root_id)
    return N


def build_mark_id(N: str, T: str, B: str, A: str) -> str:
    """
    A single printable ID string.

    You can change formatting later without changing the rest of the pipeline.
    """
    # Root has no A in our rules. Give it a consistent placeholder.
    A_value = A or "A 0 of 0"
    return f"{N} {T} {B} {A_value}"


def apply_mark_ids(normalized: Dict[str, Any]) -> Dict[str, Any]:
    """
    Takes normalized conversation dict and returns a processed_tree_v1 dict:

    - nodes dict keys become mark ids
    - node["parent"] and node["children"] become mark ids
    - node["source_node_id"] stays the original source id
    - derived fields are added for convenience
    """
    convo_id = normalized.get("conversation_id", "unknown-id")
    title = normalized.get("title", "Untitled")
    project = normalized.get("project")
    create_time = normalized.get("create_time")
    update_time = normalized.get("update_time")

    root_source = normalized.get("root_source_node_id", "")
    nodes: Dict[str, Any] = normalized.get("nodes") or {}

    if not root_source or root_source not in nodes:
        return {
            "schema": "processed_tree_v1",
            "conversation_id": convo_id,
            "title": title,
            "create_time": create_time,
            "update_time": update_time,
            "project": project,
            "root_node_id": "",
            "nodes": {},
        }

    # 1) Ensure A labels exist and also normalize children ordering.
    A = compute_A_labels(nodes, root_source)

    # 2) Compute B/T/N.
    B = compute_B_labels(nodes, root_source)
    T = compute_T_labels(nodes)
    N = compute_N_labels(nodes, root_source)

    # 3) Create mark id per source node id.
    mark_of: Dict[str, str] = {}
    for source_node_id in nodes.keys():
        mark_of[source_node_id] = build_mark_id(
            N=N.get(source_node_id, "N0000"),
            T=T.get(source_node_id, "T0000"),
            B=B.get(source_node_id, "B00"),
            A=A.get(source_node_id, ""),
        )

    # 4) Build processed nodes dict keyed by mark id.
    processed_nodes: Dict[str, Any] = {}
    for source_node_id, node in nodes.items():
        mark_id = mark_of[source_node_id]

        parent_source = node.get("parent")
        parent_mark = mark_of.get(parent_source) if parent_source else None

        children_source = node.get("children", []) or []
        children_mark = [mark_of[cid] for cid in children_source if cid in mark_of]

        msg = node.get("message")
        if msg is None:
            message_out = None
        else:
            message_out = {
                "role": msg.get("role", "unknown"),
                "source_message_id": msg.get("source_message_id", ""),
                "create_time": msg.get("create_time"),
                "text": msg.get("text", ""),
            }

        processed_nodes[mark_id] = {
            "source_node_id": source_node_id,
            "parent": parent_mark,
            "children": children_mark,
            "message": message_out,
            "derived": {
                "N": N.get(source_node_id, ""),
                "T": T.get(source_node_id, ""),
                "B": B.get(source_node_id, ""),
                "A": A.get(source_node_id, ""),
                "timestamp_human": format_human_time(
                    (msg or {}).get("create_time") if msg else None
                ),
            },
        }

    root_mark = mark_of[root_source]

    return {
        "schema": "processed_tree_v1",
        "conversation_id": convo_id,
        "title": title,
        "create_time": create_time,
        "update_time": update_time,
        "project": project,
        "root_node_id": root_mark,
        "nodes": processed_nodes,
    }
