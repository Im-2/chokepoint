"""'Is X safe?' must never be answered with a yes or no: only a path, or 'no modelled path'
with the plain statement that this is not a claim of safety. Real FalkorDB; fake LLM only."""
import asyncio

import pytest

from app import agent, config, tools
from test_agent import FakeLLM, final, message, run_llm


def test_reachability_from_one_asset_checks_every_crown_jewel(seeded_graph):
    name = seeded_graph.name
    nothing = tools.explain_reachability("srv-alpha-01", graph_name=name)
    assert nothing["outcome"] == "not_in_graph"
    assert nothing["data"]["crown_jewels"] == ["payments-signing-key", "prod-customer-db"]
    assert "any crown jewel" in nothing["notes"] and "not a statement that the asset is safe" in nothing["notes"]
    assert [t["query"] for t in nothing["trace"]].count("shortest_path") == 2   # both crown jewels were tried

    found = tools.explain_reachability("intern-laptop", graph_name=name)
    assert found["outcome"] == "answered_with_path"
    assert found["data"]["to"] == "payments-signing-key, prod-customer-db"
    assert len(found["paths"]) == 2


def test_unknown_asset_still_runs_no_traversal(seeded_graph):
    env = tools.explain_reachability("ghost-host-99", graph_name=seeded_graph.name)
    assert env["outcome"] == "unknown_asset"
    assert {t["query"] for t in env["trace"]} == {"resolve_asset"}


def test_router_understands_is_it_safe():
    assert agent.parse_request("Is srv-alpha-01 safe?") == {"kind": "exposure", "from_name": "srv-alpha-01"}
    assert agent.parse_request("how exposed is jump-host-01")["kind"] == "exposure"
    assert agent.parse_request("Can intern-laptop reach prod-customer-db?")["kind"] == "reach"


def test_router_answer_is_honest(seeded_graph, monkeypatch):
    monkeypatch.setattr(config, "CHAT_ENABLED", False)
    events = asyncio.run(_collect("Is srv-alpha-01 safe?", seeded_graph.name))
    text = final(events)["text"]
    assert [e["tool"] for e in events if e["event"] == "tool_call"] == ["explain_reachability"]
    assert "No modelled path" in text and "not a statement that the asset is safe" in text
    assert final(events)["mode"] == "router" and final(events)["checked"] is True


async def _collect(question, graph):
    return [e async for e in agent.run_chat(question, graph_name=graph)]


def test_model_that_picks_the_wrong_tool_is_overruled(seeded_graph):
    """Seen live: the model called find_attack_paths and answered just 'no modelled path'."""
    llm = FakeLLM(message(calls=[("find_attack_paths", {"depth": 2})]), message("No modelled path."))
    events = run_llm(seeded_graph.name, [("primary", llm, "m")], "Is srv-alpha-01 safe?")
    assert final(events)["mode"] == "router"
    assert "not a statement that the asset is safe" in final(events)["text"]
    assert "explain_reachability" in [e["tool"] for e in events if e["event"] == "tool_call"]


def test_model_that_uses_the_right_tool_is_accepted(seeded_graph):
    llm = FakeLLM(message(calls=[("explain_reachability", {"from_name": "srv-alpha-01"})]),
                  message("There is no modelled path from srv-alpha-01 to any crown jewel, and that is not a statement that it is safe."))
    events = run_llm(seeded_graph.name, [("primary", llm, "m")], "Is srv-alpha-01 safe?")
    assert final(events)["mode"] == "llm-primary" and final(events)["checked"] is True


def test_checker_rejects_no_path_claim_when_paths_were_returned(seeded_graph):
    env = tools.find_attack_paths(depth=4, graph_name=seeded_graph.name)
    verdict = agent.check_answer("No modelled path.", [env])
    assert not verdict.ok and "did not report" in verdict.reason
    nothing = tools.find_attack_paths(depth=2, graph_name=seeded_graph.name)
    assert agent.check_answer("There is no modelled path within 2 hops.", [nothing]).ok


@pytest.mark.parametrize("question", ["Is srv-alpha-01 safe?", "Can intern-laptop reach prod-customer-db?"])
def test_demo_questions_have_templates_that_pass_the_checker(seeded_graph, monkeypatch, question):
    monkeypatch.setattr(config, "CHAT_ENABLED", False)
    events = asyncio.run(_collect(question, seeded_graph.name))
    result = [e for e in events if e["event"] == "tool_result"][-1]["envelope"]
    assert agent.check_answer(final(events)["text"], [result]).ok


def test_checker_rejects_not_in_the_graph_for_an_existing_asset(seeded_graph):
    env = tools.explain_reachability("srv-alpha-01", graph_name=seeded_graph.name)
    assert env["outcome"] == "not_in_graph"
    assert not agent.check_answer("srv-alpha-01 is not in the graph.", [env]).ok
    assert agent.check_answer("There is no modelled path from srv-alpha-01 to any crown jewel.", [env]).ok
    ghost = tools.explain_reachability("ghost-host-99", graph_name=seeded_graph.name)
    assert agent.check_answer("ghost-host-99 is not in the graph.", [ghost]).ok   # truly unknown: allowed


def test_model_sees_a_plain_outcome_name_for_no_path(seeded_graph):
    env = tools.explain_reachability("srv-alpha-01", graph_name=seeded_graph.name)
    shown = agent.compact(env)
    assert "no_modelled_path" in shown and "not_in_graph" not in shown
