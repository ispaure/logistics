"""Small lane-layout model for a topologically ordered, paginated commit DAG.

Each row retains incoming/outgoing lane segments. Parents outside the loaded page
continue off its bottom. Active lanes keep their columns; shared parents end
lanes without shifting unrelated branches. Empty columns are reused.
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

    def allocate(oid):
        if None in lanes:
            lane = lanes.index(None)
            lanes[lane] = oid
        else:
            lane = len(lanes)
            lanes.append(oid)
        return lane

    for commit in commits:
        incoming_lanes = list(lanes)
        if commit.oid not in lanes:
            allocate(commit.oid)
        node = lanes.index(commit.oid)
        old = list(lanes)
        lanes[node] = None
        for offset, parent in enumerate(commit.parents):
            if parent not in lanes:
                if offset == 0:
                    lanes[node] = parent
                else:
                    allocate(parent)
        incoming = tuple((i, i) for i, oid in enumerate(incoming_lanes) if oid is not None)
        outgoing = [(i, i) for i, oid in enumerate(old)
                    if i != node and oid is not None]
        outgoing += [(node, lanes.index(parent)) for parent in commit.parents]
        rows.append(GraphRow(node, incoming, tuple(outgoing), max(len(old), len(lanes), 1)))
        while lanes and lanes[-1] is None:
            lanes.pop()
    return rows
