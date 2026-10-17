"""Brief tests 2-7 (+ argument validation), against a real FalkorDB. Test graphs only."""
import pytest

from app import tools
from app.db import get_client

DECOY, CHOKE = "e026", "e023"


def ran(env, query):
    return any(t["query"] == query for t in env["trace"])


# --- test 2: the depth contrast -------------------------------------------------
def test_depth_2_and_3_find_nothing_and_do_not_say_safe(seeded_graph):
    name = seeded_graph.name
    for depth in (2, 3):
        env = tools.find_attack_paths(depth=depth, graph_name=name)
        assert env["outcome"] == "not_in_graph"
        assert "not a statement that the asset is safe" in env["notes"]


def test_depth_4_finds_the_hidden_path(seeded_graph):
    env = tools.find_attack_paths(depth=4, graph_name=seeded_graph.name)
    assert env["outcome"] == "answered_with_path"
    names = [[n["name"] for n in p["nodes"]] for p in env["paths"]]
    assert any("svc-legacy-etl" in p for p in names)
    assert all(len(p["edges"]) == 4 for p in env["paths"])


def test_reach_returns_path_and_no_path_is_not_safe(seeded_graph):
    name = seeded_graph.name
    env = tools.explain_reachability("intern-laptop", "prod-customer-db", graph_name=name)
    assert env["outcome"] == "answered_with_path"
    assert env["paths"][0]["nodes"][0]["name"] == "intern-laptop"
    nothing = tools.explain_reachability("srv-alpha-01", "prod-customer-db", graph_name=name)
    assert nothing["outcome"] == "not_in_graph"
    assert "not a statement that the asset is safe" in nothing["notes"]


# --- test 3: decoy has the most paths but is not chosen --------------------------
def test_decoy_tops_naive_ranking_but_planner_avoids_it(seeded_graph):
    name = seeded_graph.name
    rank = tools.rank_choke_edges(graph_name=name)
    assert rank["data"]["naive_most_paths"]["edge_id"] == DECOY
    assert rank["data"]["ranked"][0]["edge_id"] == CHOKE
    plan = tools.plan_remediation(3, graph_name=name)
    assert DECOY not in [s["edge_id"] for s in plan["data"]["plan"]]


# --- test 4: plan then simulate; scratch graph is gone ---------------------------
def test_plan_then_simulate_cuts_everything_and_cleans_up(seeded_graph):
    name = seeded_graph.name
    plan = tools.plan_remediation(2, graph_name=name)
    ids = [s["edge_id"] for s in plan["data"]["plan"]]
    sim = tools.simulate_fix(ids, graph_name=name)
    assert sim["outcome"] == "verified_fix"
    assert sim["data"]["paths_before"] == 19 and sim["data"]["paths_after"] == 0
    assert sim["data"]["scratch_deleted"] is True
    assert sim["data"]["scratch_graph"] not in get_client().list_graphs()
    assert not [g for g in get_client().list_graphs() if g.startswith("sim:")]
    # the real graph was not changed by the simulation
    assert tools.find_attack_paths(graph_name=name)["data"]["count"] == 19


def test_budget_1_leaves_a_stated_residual(seeded_graph):
    name = seeded_graph.name
    plan = tools.plan_remediation(1, graph_name=name)
    assert plan["data"]["paths_cut"] == 11 and plan["data"]["paths_remaining"] == 8
    sim = tools.simulate_fix([plan["data"]["plan"][0]["edge_id"]], graph_name=name)
    assert (sim["data"]["paths_before"], sim["data"]["paths_after"]) == (19, 8)
    assert sim["data"]["fully_cut"] is False and "Not a complete fix" in sim["notes"]


def test_simulate_unknown_edge_makes_no_copy(seeded_graph):
    env = tools.simulate_fix(["e999"], graph_name=seeded_graph.name)
    assert env["outcome"] == "not_in_graph" and not ran(env, "delete_edge_in_scratch")


# --- test 5: unknown asset -> no traversal ---------------------------------------
def test_unknown_asset_runs_no_traversal(seeded_graph):
    env = tools.explain_reachability("no-such-box", "prod-customer-db", graph_name=seeded_graph.name)
    assert env["outcome"] == "unknown_asset" and env["data"]["unknown"] == ["no-such-box"]
    assert {t["query"] for t in env["trace"]} == {"resolve_asset"}


# --- test 6: injection safety -----------------------------------------------------
EVIL_NAMES = ["x'}) MATCH (n) DETACH DELETE n //", 'a" OR 1=1 //', "} RETURN 1 //"]


@pytest.mark.parametrize("evil", EVIL_NAMES)
def test_names_are_data_not_cypher(seeded_graph, evil):
    name = seeded_graph.name
    before = seeded_graph.ro_query("MATCH (n) RETURN count(n)").result_set
    assert tools.explain_reachability(evil, "prod-customer-db", graph_name=name)["outcome"] == "unknown_asset"
    assert tools.recall_decisions(evil, graph_name=name)["outcome"] == "unknown_asset"
    assert seeded_graph.ro_query("MATCH (n) RETURN count(n)").result_set == before


def test_bad_arguments_are_rejected_before_any_query():
    bad_calls = [
        lambda: tools.find_attack_paths(depth=9),
        lambda: tools.find_attack_paths(depth=True),
        lambda: tools.find_attack_paths(depth="2) MATCH (n) DELETE n //"),
        lambda: tools.plan_remediation(4),
        lambda: tools.simulate_fix([]),
        lambda: tools.simulate_fix(["e1", "e2", "e3", "e4", "e5", "e6"]),
        lambda: tools.simulate_fix(["e1'}) DELETE"]),
        lambda: tools.record_decision("d", "maybe"),
    ]
    for call in bad_calls:
        with pytest.raises(tools.ToolInputError):
            call()


# --- test 7: reject then re-plan --------------------------------------------------
def test_reject_then_replan_excludes_edge_and_picks_cheaper_alternative(fresh_graph_name):
    name = fresh_graph_name
    first = tools.plan_remediation(3, graph_name=name)
    assert first["data"]["plan"][0]["edge_id"] == CHOKE

    proposal = tools.propose_change([CHOKE], "cut shared deploy trust", graph_name=name)
    assert proposal["outcome"] == "proposed" and proposal["data"]["owner_teams"] == ["platform-eng"]
    assert CHOKE in proposal["data"]["ticket_markdown"]
    assert "role-ci-deployer" in proposal["data"]["config_diff"]

    with pytest.raises(tools.ToolInputError):  # a rejection must carry a reason
        tools.record_decision(proposal["data"]["run"], "reject", graph_name=name)
    done = tools.record_decision(proposal["data"]["run"], "reject", "CI needs prod-admin during releases",
                                 graph_name=name)
    assert done["outcome"] == "recorded"

    second = tools.plan_remediation(3, graph_name=name)
    edges = [s["edge_id"] for s in second["data"]["plan"]]
    assert CHOKE not in edges and DECOY not in edges
    assert edges != [s["edge_id"] for s in first["data"]["plan"]]
    assert second["data"]["total_disruption"] <= 6          # a cheap alternative, not the decoy
    assert second["data"]["paths_cut"] == 15 and second["data"]["paths_remaining"] == 4
    assert any(e["edge_id"] == CHOKE and e["on_attack_path"] for e in second["data"]["excluded_by_memory"])
    # deciding twice does nothing
    again = tools.record_decision(proposal["data"]["run"], "approve", graph_name=name)
    assert again["outcome"] == "not_in_graph"


def test_memory_is_readable_with_dates(fresh_graph_name):
    env = tools.recall_decisions(graph_name=fresh_graph_name)
    assert env["outcome"] == "answered_from_memory"
    assert {d["status"] for d in env["data"]["decisions"]} == {"rejected", "approved"}
    assert all(d["at"].startswith("2026-") for d in env["data"]["decisions"])


def test_load_bearing_ranking_runs(seeded_graph):
    env = tools.rank_load_bearing_assets(limit=20, graph_name=seeded_graph.name)
    assert env["outcome"] == "answered_with_path" and len(env["data"]["ranked"]) == 20
