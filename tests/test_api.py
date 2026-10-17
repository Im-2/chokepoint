"""Phase 3: the REST layer, run end to end against a seeded 'test:' graph.
The graph_name dependency is overridden, so these tests can never touch env:acme."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import get_client
from app.main import app, graph_name
from app.seed import seed_graph


@pytest.fixture(scope="module")
def client():
    name = f"test:api-{uuid.uuid4().hex[:8]}"
    assert name.startswith("test:")
    seed_graph(name)
    app.dependency_overrides[graph_name] = lambda: name
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        try:
            get_client().select_graph(name).delete()
        except Exception:
            pass


def post(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_docs(client):
    assert client.get("/healthz").json() == {"status": "ok", "falkordb": True}
    assert client.get("/docs").status_code == 200


def test_graph_endpoint_has_what_a_frontend_needs(client):
    g = client.get("/api/graph").json()
    assert len(g["nodes"]) == 130 and len(g["edges"]) == 322 and g["trace"]
    node = next(n for n in g["nodes"] if n["name"] == "prod-customer-db")
    assert node["crown"] is True and node["owner_team"] == "data-eng"
    assert {"id", "source", "target", "kind", "cost", "disruption"} <= set(g["edges"][0])


def test_every_envelope_carries_a_trace(client):
    for path, body in [("/api/scan", {"depth": 4}), ("/api/choke", {}), ("/api/plan", {"budget": 2}),
                       ("/api/reach", {"from_name": "intern-laptop", "to_name": "prod-customer-db"})]:
        env = post(client, path, body)
        assert env["trace"] and {"tool", "query", "args", "ms", "rows"} <= set(env["trace"][0])


def test_validation_errors_are_422(client):
    assert client.post("/api/scan", json={"depth": 9}).status_code == 422
    assert client.post("/api/plan", json={"budget": 9}).status_code == 422
    assert client.post("/api/simulate", json={"edge_ids": []}).status_code == 422


def test_reject_without_reason_is_422(client):
    r = client.post("/api/decision", json={"decision_id": "d-x", "action": "reject"})
    assert r.status_code == 422 and "reason" in r.json()["detail"]


def test_unknown_asset_and_no_path_over_rest(client):
    unknown = post(client, "/api/reach", {"from_name": "ghost-host", "to_name": "prod-customer-db"})
    assert unknown["outcome"] == "unknown_asset" and {t["query"] for t in unknown["trace"]} == {"resolve_asset"}
    nopath = post(client, "/api/reach", {"from_name": "srv-alpha-01", "to_name": "prod-customer-db"})
    assert nopath["outcome"] == "not_in_graph" and "not a statement that the asset is safe" in nopath["notes"]


def test_reset_is_idempotent_and_restores_memory(client):
    first = post(client, "/api/reset", {})
    second = post(client, "/api/reset", {})
    assert first["data"] == second["data"] and first["data"]["assets"] == 130
    assert post(client, "/api/scan", {"depth": 8})["data"]["count"] == 19


def test_full_demo_story_over_rest(client):
    post(client, "/api/reset", {})
    assert post(client, "/api/scan", {"depth": 2})["outcome"] == "not_in_graph"
    assert post(client, "/api/scan", {"depth": 4})["data"]["count"] == 1
    plan = post(client, "/api/plan", {"budget": 3})
    first_edge = plan["data"]["plan"][0]["edge_id"]
    sim = post(client, "/api/simulate", {"edge_ids": [s["edge_id"] for s in plan["data"]["plan"]]})
    assert sim["outcome"] == "verified_fix" and sim["data"]["paths_after"] == 0
    proposal = post(client, "/api/propose", {"edge_ids": [first_edge], "plan_note": "from plan"})
    assert proposal["outcome"] == "proposed"
    decided = post(client, "/api/decision", {"decision_id": proposal["data"]["run"], "action": "reject",
                                             "reason": "breaks nightly ETL"})
    assert decided["outcome"] == "recorded"
    replan = post(client, "/api/plan", {"budget": 3})
    assert first_edge not in [s["edge_id"] for s in replan["data"]["plan"]]
    memory = client.get("/api/decisions").json()
    assert any(d["reason"] == "breaks nightly ETL" for d in memory["data"]["decisions"])
