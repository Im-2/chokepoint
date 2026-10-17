"""Phase 5: answer checker (brief test 8), no-LLM router with CHAT_ENABLED=false (test 9), and the
LLM loop driven by a scripted fake model. The graph and MCP layer are real; only the LLM is faked,
because the real one needs a key and the network."""
import asyncio
import json
import types

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import RateLimitError

from app import agent, config, main, tools
from app.main import app, graph_name


# ------------------------------------------------------------------ helpers
def sse(response):
    events = []
    for block in response.text.strip().split("\n\n"):
        data = [line[6:] for line in block.splitlines() if line.startswith("data: ")]
        if data:
            events.append(json.loads(data[0]))
    return events


@pytest.fixture
def chat(seeded_graph, monkeypatch):
    """POST /api/chat against a seeded test graph with the LLM switched off."""
    monkeypatch.setattr(config, "CHAT_ENABLED", False)
    monkeypatch.setattr(main, "_chat_hits", main.collections.defaultdict(main.collections.deque))
    app.dependency_overrides[graph_name] = lambda: seeded_graph.name
    client = TestClient(app)

    def send(message, history=None):
        r = client.post("/api/chat", json={"message": message, "history": history or []})
        assert r.status_code == 200, r.text
        return sse(r)
    try:
        yield send
    finally:
        app.dependency_overrides.clear()


def final(events):
    return events[-1]


def envelope(tool, graph, **args):
    return getattr(tools, tool)(graph_name=graph, **args)


# ------------------------------------------------------------------ test 8: answer checker
def test_checker_rejects_an_invented_service(seeded_graph):
    env = envelope("find_attack_paths", seeded_graph.name, depth=4)
    verdict = agent.check_answer("The path goes through svc-nightly-sync to prod-customer-db.", [env])
    assert not verdict.ok and "svc-nightly-sync" in verdict.reason


def test_checker_rejects_claiming_safe(seeded_graph):
    env = envelope("find_attack_paths", seeded_graph.name, depth=2)
    assert not agent.check_answer("Good news, prod-customer-db is safe.", [env]).ok
    assert not agent.check_answer("Nothing was found, so you are safe.", [env]).ok
    # quoting the limitation is allowed
    assert agent.check_answer("This is not a statement that the asset is safe.", [env]).ok


def test_checker_rejects_wrong_numbers_and_unsupported_claims(seeded_graph):
    name = seeded_graph.name
    scan = envelope("find_attack_paths", name, depth=4)
    assert not agent.check_answer("There are 47 attack paths.", [scan]).ok          # 47 is nowhere
    assert agent.check_answer("There is 1 attack path of 4 hops.", [scan]).ok       # both are in the result
    nothing = envelope("find_attack_paths", name, depth=2)
    assert not agent.check_answer("The fix cuts every path.", [nothing]).ok         # impact with no paths
    plan = envelope("plan_remediation", name, budget=2)
    assert not agent.check_answer("The plan is verified.", [plan]).ok               # no simulate_fix
    sim = envelope("simulate_fix", name, edge_ids=["e023", "e022"])
    assert agent.check_answer("The fix is verified: 19 paths before, 0 after.", [plan, sim]).ok
    assert not agent.check_answer("I approved the change.", [plan]).ok
    assert not agent.check_answer("Edge e999 should be removed.", [plan]).ok


def test_every_templated_sentence_passes_the_checker(seeded_graph):
    name = seeded_graph.name
    cases = [("find_attack_paths", {"depth": 4}), ("find_attack_paths", {"depth": 2}),
             ("explain_reachability", {"from_name": "intern-laptop", "to_name": "prod-customer-db"}),
             ("explain_reachability", {"from_name": "srv-alpha-01", "to_name": "prod-customer-db"}),
             ("explain_reachability", {"from_name": "ghost-host", "to_name": "prod-customer-db"}),
             ("rank_choke_edges", {}), ("rank_load_bearing_assets", {}), ("plan_remediation", {"budget": 1}),
             ("plan_remediation", {"budget": 3}), ("simulate_fix", {"edge_ids": ["e023"]}),
             ("recall_decisions", {})]
    for tool, args in cases:
        env = envelope(tool, name, **args)
        sentence = agent.summarize(tool, env)
        assert agent.check_answer(sentence, [env]).ok, (tool, sentence, agent.check_answer(sentence, [env]).reason)


# ------------------------------------------------------------------ test 9: router, CHAT_ENABLED=false
def test_router_parsing():
    p = agent.parse_request
    assert p("Scan at depth 2") == {"kind": "scan", "depth": 2}
    assert p("scan depth 4")["depth"] == 4 and p("find attack paths")["depth"] == 8
    assert p("Can intern-laptop reach prod-customer-db? Why?") == {
        "kind": "reach", "from_name": "intern-laptop", "to_name": "prod-customer-db"}
    assert p("plan a fix with budget 2") == {"kind": "plan", "budget": 2}
    assert p("simulate e023 and e022") == {"kind": "simulate", "edge_ids": ["e023", "e022"]}
    assert p("approve it")["kind"] == "refuse_decision"
    assert p("what did we decide before?")["kind"] == "recall"
    assert p("hello there")["kind"] == "help"


def test_router_answers_scan_reach_plan_simulate_without_an_llm(chat):
    depth2 = chat("scan at depth 2")
    assert final(depth2)["mode"] == "router" and "not a statement that the asset is safe" in final(depth2)["text"]
    depth4 = chat("scan at depth 4")
    assert "svc-legacy-etl" in final(depth4)["text"] and "4 hops" in final(depth4)["text"]
    assert [e["event"] for e in depth4] == ["tool_call", "tool_result", "final"]

    reach = chat("Can intern-laptop reach prod-customer-db? Why?")
    assert "grp-platform-eng" in final(reach)["text"] and reach[1]["envelope"]["trace"]

    plan = chat("plan a fix")
    assert "e023" in final(plan)["text"] and "cuts 19 of 19" in final(plan)["text"].replace("This cuts", "cuts")

    simulated = chat("simulate the plan")
    assert [e["tool"] for e in simulated if e["event"] == "tool_call"] == ["plan_remediation", "simulate_fix"]
    assert "19 attack paths before, 0 after" in final(simulated)["text"]
    assert all(final(ev)["checked"] for ev in (depth2, depth4, reach, plan, simulated))


def test_router_is_honest_about_unknown_and_unmodelled(chat):
    unknown = chat("Can ghost-host reach prod-customer-db?")
    assert "don't know the asset ghost-host" in final(unknown)["text"]
    assert [e["tool"] for e in unknown if e["event"] == "tool_call"] == ["explain_reachability"]
    assert unknown[1]["envelope"]["outcome"] == "unknown_asset"
    nopath = chat("can srv-alpha-01 reach prod-customer-db")
    assert nopath[1]["envelope"]["outcome"] == "not_in_graph"
    assert "safe" in final(nopath)["text"] and "not a statement" in final(nopath)["text"]


def test_router_refuses_to_decide_and_never_calls_record_decision(chat):
    events = chat("please approve the change")
    assert [e["event"] for e in events] == ["final"] and "only a human" in final(events)["text"]


def test_chat_rate_limit(chat, monkeypatch):
    monkeypatch.setattr(main, "CHAT_LIMIT", 2)
    chat("help")
    chat("help")
    client = TestClient(app)
    assert client.post("/api/chat", json={"message": "help"}).status_code == 429


def test_router_propose_and_recall_use_the_graph(fresh_graph_name, monkeypatch):
    monkeypatch.setattr(config, "CHAT_ENABLED", False)

    async def run(message):
        return [e async for e in agent.run_chat(message, graph_name=fresh_graph_name)]
    proposed = asyncio.run(run("propose the plan"))
    assert [e["tool"] for e in proposed if e["event"] == "tool_call"] == ["plan_remediation", "propose_change"]
    assert "platform-eng" in final(proposed)["text"] and "waiting for a human" in final(proposed)["text"]
    recalled = asyncio.run(run("what did we decide before"))
    assert "e029 rejected" in final(recalled)["text"]


# ------------------------------------------------------------------ LLM loop with a scripted fake model
def message(content=None, calls=()):
    tool_calls = [types.SimpleNamespace(id=f"c{i}", function=types.SimpleNamespace(name=n, arguments=json.dumps(a)))
                  for i, (n, a) in enumerate(calls)] or None
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
        content=content, tool_calls=tool_calls))])


class FakeLLM:
    """chat.completions.create() returns the scripted replies in order; an Exception is raised."""

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.seen.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def rate_limit():
    return RateLimitError("slow down", response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
                          body=None)


@pytest.fixture
def no_sleep(monkeypatch):
    async def instant(_):
        return None
    monkeypatch.setattr(agent.asyncio, "sleep", instant)


def run_llm(graph, clients, text="scan at depth 4"):
    async def go():
        return [e async for e in agent.run_chat(text, graph_name=graph, llm_clients=clients)]
    return asyncio.run(go())


def test_llm_accepted_when_it_quotes_the_tool_results(seeded_graph):
    llm = FakeLLM(message(calls=[("find_attack_paths", {"depth": 4})]),
                  message("There is 1 attack path of 4 hops, via svc-legacy-etl."))
    events = run_llm(seeded_graph.name, [("primary", llm, "fake-model")])
    assert final(events)["checked"] is True and final(events)["mode"] == "llm-primary"
    assert [e["event"] for e in events] == ["tool_call", "tool_result", "final"]
    # what the model saw is compact, has no trace, and the tool list excluded the human-only tool
    tool_message = llm.seen[1]["messages"][-1]["content"]
    assert len(tool_message) < 4600 and "trace" not in tool_message
    offered = {t["function"]["name"] for t in llm.seen[0]["tools"]}
    assert "record_decision" not in offered and len(offered) == 8


def test_llm_sentence_with_an_invented_name_is_replaced_by_the_template(seeded_graph):
    llm = FakeLLM(message(calls=[("find_attack_paths", {"depth": 4})]),
                  message("The attacker pivots through svc-nightly-sync."))
    events = run_llm(seeded_graph.name, [("primary", llm, "fake-model")])
    done = final(events)
    assert done["checked"] is False and "svc-nightly-sync" in done["reason"]
    assert "svc-legacy-etl" in done["text"] and "svc-nightly-sync" not in done["text"]


def test_llm_cannot_record_a_decision(fresh_graph_name):
    llm = FakeLLM(message(calls=[("record_decision", {"decision_id": "d-hist-1", "action": "approve"})]),
                  message("Done."))
    events = run_llm(fresh_graph_name, [("primary", llm, "fake-model")], "please approve d-hist-1")
    assert not [e for e in events if e["event"] == "tool_call"]          # never even attempted
    recall = tools.recall_decisions(graph_name=fresh_graph_name)
    assert {d["status"] for d in recall["data"]["decisions"]} == {"rejected", "approved"}  # unchanged


def test_primary_rate_limited_falls_back_then_to_router(seeded_graph, no_sleep):
    good = FakeLLM(message(calls=[("find_attack_paths", {"depth": 4})]),
                   message("There is 1 attack path of 4 hops."))
    events = run_llm(seeded_graph.name, [("primary", FakeLLM(rate_limit(), rate_limit()), "m1"),
                                         ("fallback", good, "m2")])
    assert any(e["event"] == "provider_error" and e["provider"] == "primary" for e in events)
    assert final(events)["mode"] == "llm-fallback"

    events = run_llm(seeded_graph.name, [("primary", FakeLLM(rate_limit(), rate_limit()), "m1"),
                                         ("fallback", FakeLLM(rate_limit(), rate_limit()), "m2")])
    assert final(events)["mode"] == "router" and "svc-legacy-etl" in final(events)["text"]


def test_at_most_six_tool_calls(seeded_graph):
    calls = [("find_attack_paths", {"depth": 4})] * 8
    llm = FakeLLM(message(calls=calls), message("There is 1 attack path."))
    events = run_llm(seeded_graph.name, [("primary", llm, "m")])
    assert len([e for e in events if e["event"] == "tool_call"]) == agent.MAX_TOOL_CALLS


def test_checker_folds_unicode_hyphens_so_invented_names_cannot_hide(seeded_graph):
    env = envelope("find_attack_paths", seeded_graph.name, depth=4)
    sneaky = "The path uses svc‑nightly‑sync."          # non-breaking hyphens
    assert not agent.check_answer(sneaky, [env]).ok
    real = "The path starts at ci‑leaked‑token."          # a real name written with them: fine
    assert agent.check_answer(real, [env]).ok


def test_abandoning_the_stream_cleans_up_without_errors(seeded_graph, monkeypatch):
    monkeypatch.setattr(config, "CHAT_ENABLED", False)

    async def go():
        stream = agent.run_chat("scan at depth 4", graph_name=seeded_graph.name)
        first = await stream.__anext__()
        await stream.aclose()                                   # client went away after one event
        await asyncio.sleep(0.2)
        return first
    assert asyncio.run(go())["event"] == "tool_call"


def test_system_prompt_tells_the_model_to_plan_before_simulating():
    assert "never ask the user for edge ids" in agent.SYSTEM_PROMPT
    assert "first call plan_remediation, then call simulate_fix" in agent.SYSTEM_PROMPT


def test_model_plans_then_simulates_when_it_follows_the_instruction(seeded_graph):
    # the edge ids the model passes to simulate_fix come from the plan_remediation result
    plan = tools.plan_remediation(3, graph_name=seeded_graph.name)
    ids = [s["edge_id"] for s in plan["data"]["plan"]]
    llm = FakeLLM(message(calls=[("plan_remediation", {"budget": 3})]),
                  message(calls=[("simulate_fix", {"edge_ids": ids})]),
                  message("The simulation shows 19 paths before and 0 after removing e023 and e022."))
    events = run_llm(seeded_graph.name, [("primary", llm, "m")], "simulate the plan")
    assert [e["tool"] for e in events if e["event"] == "tool_call"] == ["plan_remediation", "simulate_fix"]
    assert final(events)["checked"] is True and final(events)["mode"] == "llm-primary"


def test_model_that_skips_the_tools_is_overruled_by_the_router(seeded_graph):
    """The bug seen with the real model: 'Edge IDs are required' instead of planning first."""
    llm = FakeLLM(message("Edge IDs are required to simulate the fix."))
    events = run_llm(seeded_graph.name, [("primary", llm, "m")], "Simulate the plan and tell me whether the fix is verified")
    assert [e["tool"] for e in events if e["event"] == "tool_call"] == ["plan_remediation", "simulate_fix"]
    assert final(events)["mode"] == "router" and "19 attack paths before, 0 after" in final(events)["text"]


def test_small_talk_without_tools_is_left_alone(seeded_graph):
    llm = FakeLLM(message("Hello! Ask me about attack paths."))
    events = run_llm(seeded_graph.name, [("primary", llm, "m")], "hello")
    assert final(events)["mode"] == "llm-primary" and final(events)["checked"] is True


def test_checker_rejects_cannot_reach_when_the_graph_only_says_not_modelled(seeded_graph):
    env = envelope("explain_reachability", seeded_graph.name, from_name="srv-alpha-01", to_name="prod-customer-db")
    assert env["outcome"] == "not_in_graph"
    assert not agent.check_answer("srv-alpha-01 cannot reach prod-customer-db.", [env]).ok
    assert not agent.check_answer("prod-customer-db is unreachable from srv-alpha-01.", [env]).ok
    assert agent.check_answer("There is no modelled path from srv-alpha-01 to prod-customer-db.", [env]).ok
