"""Brief test 10: MCP lists the catalogue, and an MCP call matches the REST result.
In-memory transport for parity (bound to a test: graph); one real HTTP check of /mcp."""
import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app import tools
from app.db import get_client
from app.main import app, graph_name
from app.mcp_server import build_server
from app.seed import seed_graph


@pytest.fixture(scope="module")
def graph():
    name = f"test:mcp-{uuid.uuid4().hex[:8]}"
    assert name.startswith("test:")
    seed_graph(name)
    try:
        yield name
    finally:
        get_client().select_graph(name).delete()


def mcp_call(graph, tool, args):
    async def go():
        async with Client(build_server(graph)) as c:
            return await c.call_tool(tool, args)
    return asyncio.run(go())


def comparable(env):
    """Everything except timings, which differ between any two runs."""
    return {k: env[k] for k in ("outcome", "data", "paths", "notes")}


def test_list_tools_returns_the_catalogue(graph):
    async def go():
        async with Client(build_server(graph)) as c:
            return await c.list_tools()
    listing = asyncio.run(go())
    names = {t.name for t in listing.tools}
    assert names == set(tools.TOOLS)
    assert len(names) == 9
    simulate = next(t for t in listing.tools if t.name == "simulate_fix")
    assert simulate.input_schema["properties"]["edge_ids"]["type"] == "array"


def test_mcp_result_matches_rest_result(graph):
    app.dependency_overrides[graph_name] = lambda: graph
    try:
        rest = TestClient(app)
        for tool, path, body in [("find_attack_paths", "/api/scan", {"depth": 4}),
                                 ("plan_remediation", "/api/plan", {"budget": 2}),
                                 ("rank_choke_edges", "/api/choke", {"depth": 8, "limit": 15}),
                                 ("explain_reachability", "/api/reach",
                                  {"from_name": "intern-laptop", "to_name": "prod-customer-db"})]:
            via_rest = rest.post(path, json=body).json()
            via_mcp = mcp_call(graph, tool, body).structured_content
            assert comparable(via_mcp) == comparable(via_rest), tool
    finally:
        app.dependency_overrides.clear()


def test_unknown_asset_over_mcp_is_honest(graph):
    env = mcp_call(graph, "explain_reachability", {"from_name": "ghost-host", "to_name": "prod-customer-db"})
    assert env.structured_content["outcome"] == "unknown_asset"


def test_bad_arguments_are_an_mcp_error(graph):
    result = mcp_call(graph, "find_attack_paths", {"depth": 99})
    assert result.is_error


def test_real_http_endpoint_is_stateless_and_lists_tools():
    """POST JSON-RPC to /mcp on the real FastAPI app (lifespan started by the context manager)."""
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(app) as http:
        for request_id in (1, 2):  # two independent requests: no session id is needed or issued
            r = http.post("/mcp", headers=headers,
                          json={"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}})
            assert r.status_code == 200, r.text
            assert "mcp-session-id" not in {k.lower() for k in r.headers}
            assert len(json.loads(r.text)["result"]["tools"]) == 9
