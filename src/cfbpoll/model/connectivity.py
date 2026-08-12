"""Schedule-graph diagnostics — the weeks 1-4 product.

Report 02 §4 recommendation item 3 names the measures this module has to
produce, and report 05 §9.1 makes them the launch product rather than a
footnote: before `headline_start_week` the site publishes *what is not yet
knowable*, drawn, instead of a ranking nobody should trust.

    number of components
    largest-component share
    the fitted lambda at this week
    median rank-interval width
    count of teams whose interval spans effectively the whole league
    count of teams with no FBS opponent in common with the top group

Two things here are not in that list and both earn their place:

BRIDGE GAMES are the cut edges of the played graph — the single games whose
removal would split a component in two. They are the honest answer to "how much
of this ranking rests on one result", and in week 2 there are dozens of them.
Tarjan's algorithm, iterative because a 300-node chain would otherwise be a
recursion-depth bug waiting for the one season that has a long one.

WHAT WOULD HAVE TO BE TRUE is the forward-looking half: scheduled-but-unplayed
games that would weld two currently-separate components together. Report 05 §9.1
item 4 wants this as standing weekly content — "Saturday's X-Y is worth more to
this poll than its TV slot suggests" — and it is one pass over the games the
archive already has and the model has not yet seen.

THE LAYOUT IS COMPUTED HERE, not in the browser. Report 03 §7.2 says the site
never computes; report 05 §8 says charts are hand-rolled SVG with no charting
library. Both are satisfied by shipping (x, y) in [0, 1] per node from a
deterministic packing, so the Next.js surface and the static build draw
identical pictures from identical numbers. The layout is component-clustered on
purpose: in week 1 the reader sees forty separate rings and in week 5 one, and
watching that happen IS the content.

Nothing in this module is a model input. It reads the same game frame the fit
reads and reports properties of it.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import polars as pl

__all__ = [
    "Graph",
    "GraphLayout",
    "bridges",
    "build_graph",
    "components",
    "distance_from",
    "layout",
    "would_connect",
]


@dataclass(frozen=True)
class Graph:
    """The played schedule as an undirected multigraph, keyed by team name.

    `edges` is parallel to `game_ids`: edge i is game_ids[i]. Parallel edges (two
    teams that met twice — a regular-season game and a conference championship)
    are kept, because they are exactly what makes a link NOT a bridge, and
    collapsing them would over-report fragility.
    """

    teams: tuple[str, ...]
    index: dict[str, int]
    edges: tuple[tuple[int, int], ...]
    game_ids: tuple[int, ...]
    weeks: tuple[int, ...]
    classification: dict[str, str]

    @property
    def n(self) -> int:
        return len(self.teams)

    def adjacency(self) -> list[list[tuple[int, int]]]:
        """(neighbour, edge_index) per node. Sorted, so every traversal is stable."""
        adj: list[list[tuple[int, int]]] = [[] for _ in range(self.n)]
        for ei, (a, b) in enumerate(self.edges):
            adj[a].append((b, ei))
            adj[b].append((a, ei))
        for row in adj:
            row.sort()
        return adj

    def degrees(self) -> list[int]:
        deg = [0] * self.n
        for a, b in self.edges:
            deg[a] += 1
            deg[b] += 1
        return deg


def build_graph(games: pl.DataFrame, classes: dict[str, str] | None = None) -> Graph:
    """The schedule graph of a completed-game frame. Deterministic team order."""
    home = games["home_team"].to_list()
    away = games["away_team"].to_list()
    teams = tuple(sorted(set(home) | set(away)))
    index = {t: i for i, t in enumerate(teams)}

    home_class = games["home_class"].to_list()
    away_class = games["away_class"].to_list()
    known: dict[str, str] = dict(classes or {})
    order = {"fbs": 0, "fcs": 1, "ii": 2, "iii": 3, "unknown": 4}
    for team, klass in [*zip(home, home_class, strict=True), *zip(away, away_class, strict=True)]:
        if team not in known or order.get(klass, 4) < order.get(known[team], 4):
            known[team] = klass

    # Sorted by game_id so the edge list — and therefore every traversal order,
    # every layout coordinate and every published diagnostic — is a pure
    # function of the data (report 03 §9.3).
    rows = sorted(
        zip(
            games["game_id"].to_list(),
            games["week"].to_list(),
            home,
            away,
            strict=True,
        )
    )
    edges = tuple((index[h], index[a]) for _, _, h, a in rows)
    return Graph(
        teams=teams,
        index=index,
        edges=edges,
        game_ids=tuple(int(g) for g, _, _, _ in rows),
        weeks=tuple(int(w) for _, w, _, _ in rows),
        classification={t: known.get(t, "unknown") for t in teams},
    )


def components(graph: Graph) -> list[int]:
    """Component id per node. Ids are assigned by DESCENDING component size, so
    component 0 is always the largest and the site can colour by id directly."""
    parent = list(range(graph.n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in graph.edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    members: dict[int, list[int]] = {}
    for i in range(graph.n):
        members.setdefault(find(i), []).append(i)
    # Size descending, then by the smallest team index inside, so ties are stable.
    ordered = sorted(members.values(), key=lambda m: (-len(m), m[0]))
    out = [0] * graph.n
    for cid, member in enumerate(ordered):
        for i in member:
            out[i] = cid
    return out


def bridges(graph: Graph) -> set[int]:
    """Edge indices that are cut edges. Tarjan's low-link, iterated not recursed.

    A parallel edge is never a bridge, which falls out for free: the second edge
    between the same pair provides the back-edge that lowers the low-link. That
    is the correct answer — two teams that played twice are not held together by
    one result.
    """
    adj = graph.adjacency()
    disc = [-1] * graph.n
    low = [0] * graph.n
    found: set[int] = set()
    timer = 0

    for root in range(graph.n):
        if disc[root] != -1:
            continue
        # (node, parent_edge, iterator position into adj[node])
        stack: list[list[int]] = [[root, -1, 0]]
        disc[root] = low[root] = timer
        timer += 1
        while stack:
            frame = stack[-1]
            node, parent_edge, pos = frame
            if pos < len(adj[node]):
                frame[2] += 1
                nxt, ei = adj[node][pos]
                if ei == parent_edge:
                    continue
                if disc[nxt] == -1:
                    disc[nxt] = low[nxt] = timer
                    timer += 1
                    stack.append([nxt, ei, 0])
                elif disc[nxt] < low[node]:
                    low[node] = disc[nxt]
            else:
                stack.pop()
                if stack:
                    up = stack[-1][0]
                    if low[node] < low[up]:
                        low[up] = low[node]
                    if low[node] > disc[up]:
                        found.add(parent_edge)
    return found


def component_split(graph: Graph, edge_index: int) -> tuple[int, int]:
    """Sizes of the two halves a cut edge holds together. (0, 0) if not a bridge."""
    a, b = graph.edges[edge_index]
    adj = graph.adjacency()
    seen = {a}
    queue = deque([a])
    while queue:
        node = queue.popleft()
        for nxt, ei in adj[node]:
            if ei == edge_index or nxt in seen:
                continue
            seen.add(nxt)
            queue.append(nxt)
    if b in seen:
        return (0, 0)
    # The far half is everything reachable from b under the same removal, which
    # is its whole component minus the near half.
    far = {b}
    queue = deque([b])
    while queue:
        node = queue.popleft()
        for nxt, ei in adj[node]:
            if ei == edge_index or nxt in far:
                continue
            far.add(nxt)
            queue.append(nxt)
    return (len(seen), len(far))


def distance_from(graph: Graph, sources: list[str]) -> dict[str, int]:
    """Hop distance from a set of teams. Unreachable teams get -1.

    Distance 1 is "played them", distance 2 is "shares an opponent with them".
    The §4 diagnostic "teams with no FBS opponent in common with the top group"
    is therefore `distance > 2 or unreachable`, which is the definition this
    module publishes and the site prints.
    """
    dist = {t: -1 for t in graph.teams}
    adj = graph.adjacency()
    queue: deque[int] = deque()
    for team in sources:
        if team in graph.index:
            dist[team] = 0
            queue.append(graph.index[team])
    while queue:
        node = queue.popleft()
        here = dist[graph.teams[node]]
        for nxt, _ in adj[node]:
            if dist[graph.teams[nxt]] == -1:
                dist[graph.teams[nxt]] = here + 1
                queue.append(nxt)
    return dist


def would_connect(
    graph: Graph,
    upcoming: pl.DataFrame,
    comp: list[int],
) -> list[dict[str, Any]]:
    """Scheduled games that would weld two currently-separate components.

    `upcoming` is a canonical game frame of games NOT in the fit — typically the
    next week's slate. Games between two teams already in the same component are
    dropped, because they are not the story; so are games involving a team the
    graph has never seen, whose component is a singleton and which would connect
    by definition.

    Ties are broken by the size of the smaller side descending — the most
    valuable connector is the one that brings in the biggest stranded cluster,
    which is precisely the editorial claim report 05 §9.1 item 4 wants to make.
    """
    sizes: dict[int, int] = {}
    for cid in comp:
        sizes[cid] = sizes.get(cid, 0) + 1

    out: list[dict[str, Any]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for row in upcoming.iter_rows(named=True):
        home, away = row["home_team"], row["away_team"]
        hi = graph.index.get(home)
        ai = graph.index.get(away)
        # A team with no games yet is its own island; "this game connects it" is
        # true and uninteresting, so both sides must already be in the graph.
        if hi is None or ai is None:
            continue
        hc, ac = comp[hi], comp[ai]
        if hc == ac:
            continue
        pair = (min(hc, ac), max(hc, ac))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        out.append(
            {
                "game_id": int(row["game_id"]),
                "week": int(row["week"]),
                "home": home,
                "away": away,
                "home_component_size": sizes[hc],
                "away_component_size": sizes[ac],
            }
        )
    out.sort(
        key=lambda g: (
            -min(g["home_component_size"], g["away_component_size"]),
            -max(g["home_component_size"], g["away_component_size"]),
            g["game_id"],
        )
    )
    return out


@dataclass(frozen=True)
class GraphLayout:
    """Normalised node positions in [0, 1]. Deterministic given the graph."""

    x: tuple[float, ...]
    y: tuple[float, ...]


def layout(graph: Graph, comp: list[int], aspect: float = 1.9) -> GraphLayout:
    """Component-clustered radial packing.

    Each component becomes a ring whose radius grows as sqrt(size); the rings are
    shelf-packed left to right, largest first, into a box of the given aspect
    ratio. Node order inside a ring is a BFS from its highest-degree member, which
    keeps most edges short without any iterative force simulation — force layouts
    are non-deterministic in practice and a published picture that changes
    between runs is a published number that changes between runs.

    Singletons (a team whose only games are outside the fit universe) still get a
    ring of radius 0 and a position, because a team the graph cannot see is
    exactly what the reader should be able to count in week 1.
    """
    deg = graph.degrees()
    members: dict[int, list[int]] = {}
    for i, cid in enumerate(comp):
        members.setdefault(cid, []).append(i)
    if not members:
        return GraphLayout(x=(), y=())

    placed: list[tuple[float, float]] = [(0.0, 0.0)] * graph.n
    adj = graph.adjacency()

    # Shelf-pack the rings. Component 0 is the largest by construction.
    cursor_x = 0.0
    shelf_y = 0.0
    shelf_h = 0.0
    width_budget = sum(2.0 * _radius(len(m)) for m in members.values())
    biggest = _radius(max(len(m) for m in members.values()))
    # A row about `aspect` times as wide as it is tall, given the total ring width.
    row_width = max(math.sqrt(width_budget * aspect * biggest), 2.0 * biggest, 1e-9)

    for cid in sorted(members):
        member = members[cid]
        r = _radius(len(member))
        if cursor_x > 0.0 and cursor_x + 2.0 * r > row_width:
            cursor_x = 0.0
            shelf_y += shelf_h + _GAP
            shelf_h = 0.0
        cx = cursor_x + r
        cy = shelf_y + r
        for k, node in enumerate(_ring_order(member, adj, deg)):
            if len(member) == 1:
                placed[node] = (cx, cy)
                continue
            theta = 2.0 * math.pi * k / len(member) - math.pi / 2.0
            placed[node] = (cx + r * math.cos(theta), cy + r * math.sin(theta))
        cursor_x += 2.0 * r + _GAP
        shelf_h = max(shelf_h, 2.0 * r)

    return _normalise(placed)


_GAP = 0.6


def _radius(size: int) -> float:
    """Ring radius for a component of `size` nodes. sqrt so area tracks size."""
    if size <= 1:
        return 0.0
    return math.sqrt(size) * 0.42


def _ring_order(member: list[int], adj: list[list[tuple[int, int]]], deg: list[int]) -> list[int]:
    """BFS from the highest-degree member. Deterministic, and keeps edges short."""
    start = min(member, key=lambda i: (-deg[i], i))
    inside = set(member)
    seen = {start}
    order = [start]
    queue: deque[int] = deque([start])
    while queue:
        node = queue.popleft()
        for nxt, _ in sorted(adj[node], key=lambda p: (-deg[p[0]], p[0])):
            if nxt in inside and nxt not in seen:
                seen.add(nxt)
                order.append(nxt)
                queue.append(nxt)
    order.extend(sorted(i for i in member if i not in seen))
    return order


def _normalise(points: list[tuple[float, float]]) -> GraphLayout:
    """Scale into [0, 1]^2, preserving aspect so rings stay circular."""
    if not points:
        return GraphLayout(x=(), y=())
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    lo_x, hi_x = min(xs), max(xs)
    lo_y, hi_y = min(ys), max(ys)
    span = max(hi_x - lo_x, hi_y - lo_y, 1e-9)
    # Centre the shorter axis rather than stretching it.
    pad_x = (span - (hi_x - lo_x)) / 2.0
    pad_y = (span - (hi_y - lo_y)) / 2.0
    return GraphLayout(
        x=tuple(round((p[0] - lo_x + pad_x) / span, 6) for p in points),
        y=tuple(round((p[1] - lo_y + pad_y) / span, 6) for p in points),
    )
