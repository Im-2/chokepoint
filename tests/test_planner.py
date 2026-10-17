"""The greedy planner is pure Python, so these tests need no database."""
from app.planner import greedy_plan

INFO = {"a": {"disruption": 2}, "b": {"disruption": 1}, "c": {"disruption": 9}, "z": {"disruption": 1}}


def test_prefers_paths_cut_per_disruption_over_raw_count():
    paths = [["a", "c"], ["b", "c"], ["c"]]  # c is on all 3 paths but costs 9
    steps, remaining, _ = greedy_plan(paths, INFO, budget=3)
    assert steps[0]["edge_id"] != "c"        # a=1/2, b=1/1 beat c=3/9
    assert remaining == []


def test_stops_as_soon_as_nothing_remains_and_says_so():
    steps, remaining, note = greedy_plan([["a"]], INFO, budget=3)
    assert [s["edge_id"] for s in steps] == ["a"]
    assert remaining == [] and "1 of 3" in note


def test_never_picks_an_edge_that_cuts_nothing():
    steps, _, _ = greedy_plan([["a"]], INFO, budget=3)
    assert "z" not in [s["edge_id"] for s in steps]   # z is on no path


def test_excluded_edges_are_skipped_and_leftover_is_reported():
    steps, remaining, note = greedy_plan([["a"]], INFO, budget=3, excluded={"a"})
    assert steps == [] and remaining == [["a"]]
    assert "no remaining edge" in note


def test_budget_limits_the_plan_and_reports_residual():
    steps, remaining, note = greedy_plan([["a"], ["b"]], INFO, budget=1)
    assert len(steps) == 1 and len(remaining) == 1 and "remain" in note
