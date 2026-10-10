"""Small lane-layout model for a topologically ordered, paginated commit DAG.

Each row retains incoming/outgoing lane segments. Parents outside the loaded page
continue off its bottom; merges add lanes and shared parents collapse them.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GraphRow:
    lane: int
    incoming: tuple[tuple[int, int], ...]
    outgoing: tuple[tuple[int, int], ...]
    width: int


def layout_graph(commits):
    lanes = []
    rows = []
    for commit in commits:
        incoming_lanes = list(lanes)
        if commit.oid not in lanes: lanes.append(commit.oid)
        node = lanes.index(commit.oid)
        old = list(lanes)
        lanes.pop(node)
        for offset, parent in enumerate(commit.parents):
            if parent not in lanes: lanes.insert(min(node + offset, len(lanes)), parent)
        incoming = tuple((i, i) for i in range(len(incoming_lanes)))
        outgoing = [(i, lanes.index(oid)) for i, oid in enumerate(old)
                    if i != node and oid in lanes]
        outgoing += [(node, lanes.index(parent)) for parent in commit.parents]
        rows.append(GraphRow(node, incoming, tuple(outgoing), max(len(old), len(lanes), 1)))
    return rows
