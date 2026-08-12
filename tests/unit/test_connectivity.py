"""The schedule-graph diagnostics that are the weeks 1-4 product.

These are graph facts, so they are tested on graphs whose answers are known by
inspection rather than on a season, which keeps the failure messages readable and
keeps the test suite offline.
"""

from __future__ import annotations

import polars as pl

from cfbpoll.model import connectivity as conn


def _games(pairs: list[tuple[str, str]], week: int = 1) -> pl.DataFrame:
    """A minimal completed-game frame: only the columns build_graph reads."""
    return pl.DataFrame(
        {
            "game_id": list(range(1, len(pairs) + 1)),
            "week": [week] * len(pairs),
            "home_team": [h for h, _ in pairs],
            "away_team": [a for _, a in pairs],
            "home_class": ["fbs"] * len(pairs),
            "away_class": ["fbs"] * len(pairs),
        },
        schema={
            "game_id": pl.Int64,
            "week": pl.Int32,
            "home_team": pl.Utf8,
            "away_team": pl.Utf8,
            "home_class": pl.Utf8,
            "away_class": pl.Utf8,
        },
    )


class TestBuildGraph:
    def test_teams_are_sorted_and_deduplicated(self) -> None:
        graph = conn.build_graph(_games([("B", "A"), ("A", "C")]))
        assert graph.teams == ("A", "B", "C")
        assert graph.n == 3

    def test_edges_follow_game_id_order(self) -> None:
        """Determinism: the edge list, and therefore every layout coordinate and
        every published diagnostic, must be a pure function of the data."""
        frame = _games([("A", "B"), ("C", "D")])
        shuffled = frame.reverse()
        assert conn.build_graph(frame).edges == conn.build_graph(shuffled).edges

    def test_classification_prefers_the_highest_division_seen(self) -> None:
        frame = _games([("A", "B")]).with_columns(away_class=pl.lit("fcs"))
        graph = conn.build_graph(frame)
        assert graph.classification["A"] == "fbs"
        assert graph.classification["B"] == "fcs"


class TestComponents:
    def test_a_connected_graph_is_one_component(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("B", "C"), ("C", "D")]))
        assert conn.components(graph) == [0, 0, 0, 0]

    def test_component_ids_are_assigned_largest_first(self) -> None:
        """The site colours by component id, so id 0 must always be the largest."""
        graph = conn.build_graph(_games([("Y", "Z"), ("A", "B"), ("B", "C")]))
        comp = dict(zip(graph.teams, conn.components(graph), strict=True))
        assert comp["A"] == comp["B"] == comp["C"] == 0
        assert comp["Y"] == comp["Z"] == 1

    def test_disconnected_pairs_are_separate(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("C", "D"), ("E", "F")]))
        assert len(set(conn.components(graph))) == 3


class TestBridges:
    def test_every_edge_of_a_path_is_a_bridge(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("B", "C"), ("C", "D")]))
        assert conn.bridges(graph) == {0, 1, 2}

    def test_no_edge_of_a_cycle_is_a_bridge(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("B", "C"), ("C", "A")]))
        assert conn.bridges(graph) == set()

    def test_the_link_between_two_cycles_is_the_only_bridge(self) -> None:
        graph = conn.build_graph(
            _games(
                [
                    ("A", "B"),
                    ("B", "C"),
                    ("C", "A"),
                    ("C", "D"),  # the bridge
                    ("D", "E"),
                    ("E", "F"),
                    ("F", "D"),
                ]
            )
        )
        assert conn.bridges(graph) == {3}

    def test_a_rematch_is_never_a_bridge(self) -> None:
        """Two teams that played twice are not held together by one result, and
        the diagnostic must not claim they are."""
        graph = conn.build_graph(_games([("A", "B"), ("A", "B")]))
        assert conn.bridges(graph) == set()

    def test_a_long_chain_does_not_blow_the_recursion_limit(self) -> None:
        pairs = [(f"T{i:04d}", f"T{i + 1:04d}") for i in range(3000)]
        graph = conn.build_graph(_games(pairs))
        assert len(conn.bridges(graph)) == 3000


class TestComponentSplit:
    def test_a_bridge_reports_both_halves(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("B", "C"), ("C", "D")]))
        assert conn.component_split(graph, 1) == (2, 2)

    def test_a_non_bridge_reports_nothing(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("B", "C"), ("C", "A")]))
        assert conn.component_split(graph, 0) == (0, 0)


class TestDistanceFrom:
    def test_hop_counts_and_unreachability(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("B", "C"), ("C", "D"), ("Y", "Z")]))
        dist = conn.distance_from(graph, ["A"])
        assert dist["A"] == 0
        assert dist["B"] == 1
        assert dist["C"] == 2  # shares an opponent with A
        assert dist["D"] == 3
        assert dist["Y"] == -1  # no chain at all


class TestWouldConnect:
    def test_only_cross_component_games_are_reported(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("C", "D")]))
        comp = conn.components(graph)
        upcoming = pl.DataFrame(
            {
                "game_id": [10, 11],
                "week": [2, 2],
                "home_team": ["A", "A"],
                "away_team": ["B", "C"],  # A-B is intra-component and must be dropped
            }
        )
        found = conn.would_connect(graph, upcoming, comp)
        assert [g["game_id"] for g in found] == [11]

    def test_a_team_the_graph_has_never_seen_is_not_a_connector(self) -> None:
        graph = conn.build_graph(_games([("A", "B")]))
        comp = conn.components(graph)
        upcoming = pl.DataFrame(
            {"game_id": [10], "week": [2], "home_team": ["A"], "away_team": ["NEW"]}
        )
        assert conn.would_connect(graph, upcoming, comp) == []

    def test_one_game_per_component_pair(self) -> None:
        """Three games between the same two clusters is one story, not three."""
        graph = conn.build_graph(_games([("A", "B"), ("C", "D")]))
        comp = conn.components(graph)
        upcoming = pl.DataFrame(
            {
                "game_id": [10, 11, 12],
                "week": [2, 2, 2],
                "home_team": ["A", "B", "A"],
                "away_team": ["C", "D", "D"],
            }
        )
        assert len(conn.would_connect(graph, upcoming, comp)) == 1

    def test_biggest_stranded_cluster_ranks_first(self) -> None:
        graph = conn.build_graph(
            _games([("A", "B"), ("B", "C"), ("C", "D"), ("X", "Y"), ("P", "Q")])
        )
        comp = conn.components(graph)
        upcoming = pl.DataFrame(
            {
                "game_id": [20, 21],
                "week": [2, 2],
                "home_team": ["A", "A"],
                "away_team": ["P", "X"],
            }
        )
        found = conn.would_connect(graph, upcoming, comp)
        assert min(found[0]["home_component_size"], found[0]["away_component_size"]) == 2


class TestLayout:
    def test_coordinates_are_normalised(self) -> None:
        graph = conn.build_graph(_games([("A", "B"), ("B", "C"), ("X", "Y")]))
        out = conn.layout(graph, conn.components(graph))
        assert len(out.x) == len(out.y) == graph.n
        assert all(0.0 <= v <= 1.0 for v in out.x)
        assert all(0.0 <= v <= 1.0 for v in out.y)

    def test_layout_is_deterministic(self) -> None:
        """A published picture that changes between runs is a published number
        that changes between runs."""
        graph = conn.build_graph(_games([("A", "B"), ("B", "C"), ("C", "D"), ("X", "Y")]))
        comp = conn.components(graph)
        assert conn.layout(graph, comp) == conn.layout(graph, comp)

    def test_components_do_not_overlap(self) -> None:
        graph = conn.build_graph(
            _games([("A", "B"), ("B", "C"), ("C", "A"), ("X", "Y"), ("Y", "Z"), ("Z", "X")])
        )
        comp = conn.components(graph)
        out = conn.layout(graph, comp)

        def box(cid: int) -> tuple[float, float, float, float]:
            xs = [out.x[i] for i in range(graph.n) if comp[i] == cid]
            ys = [out.y[i] for i in range(graph.n) if comp[i] == cid]
            return min(xs), max(xs), min(ys), max(ys)

        ax0, ax1, ay0, ay1 = box(0)
        bx0, bx1, by0, by1 = box(1)
        # Separated on at least one axis — the packer may shelve rings side by
        # side or stack them, and either reads as two distinct islands.
        assert ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0

    def test_an_empty_graph_lays_out_to_nothing(self) -> None:
        """Week 0 has no games. That must be an empty picture, not a crash."""
        graph = conn.build_graph(_games([]))
        out = conn.layout(graph, [])
        assert out.x == () and out.y == ()
