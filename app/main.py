"""FastAPI app. Every non-chat endpoint calls a tool function directly (no LLM involved)."""
import time

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config, queries, tools
from app.db import get_client, tenant_graph_name
from app.models import (ChokeRequest, DecisionRequest, Envelope, GraphResponse, PlanRequest,
                        ProposeRequest, ReachRequest, ScanRequest, SimulateRequest)
from app.seed import seed_graph

app = FastAPI(title="Chokepoint", version="0.1.0",
              description="Attack-path agent over a FalkorDB graph. Graph Hacks, Track 01.")

app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["*"],
                   allow_headers=["*"])


@app.exception_handler(tools.ToolInputError)
async def bad_input(_request, exc: tools.ToolInputError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def graph_name() -> str:
    """Which graph this request works on. Tests override this dependency with a test: graph."""
    return tenant_graph_name()


@app.get("/healthz")
def healthz():
    try:
        get_client().list_graphs()
        return {"status": "ok", "falkordb": True}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "falkordb": False})


@app.get("/api/graph", response_model=GraphResponse)
def get_graph(g: str = Depends(graph_name)):
    run = tools.Run("get_graph", g)
    nodes = run.read("graph_nodes", queries.GRAPH_NODES)
    edges = run.read("graph_edges", queries.GRAPH_EDGES)
    return {"nodes": [dict(zip(["id", "name", "kind", "entry", "crown", "owner_team"], r)) for r in nodes],
            "edges": [dict(zip(["id", "source", "target", "kind", "cost", "disruption"], r)) for r in edges],
            "trace": run.trace}


@app.post("/api/scan", response_model=Envelope)
def scan(body: ScanRequest, g: str = Depends(graph_name)):
    return tools.find_attack_paths(depth=body.depth, limit=50, graph_name=g)


@app.post("/api/reach", response_model=Envelope)
def reach(body: ReachRequest, g: str = Depends(graph_name)):
    return tools.explain_reachability(body.from_name, body.to_name, graph_name=g)


@app.post("/api/choke", response_model=Envelope)
def choke(body: ChokeRequest, g: str = Depends(graph_name)):
    return tools.rank_choke_edges(depth=body.depth, limit=body.limit, graph_name=g)


@app.post("/api/plan", response_model=Envelope)
def plan(body: PlanRequest, g: str = Depends(graph_name)):
    return tools.plan_remediation(budget=body.budget, graph_name=g)


@app.post("/api/simulate", response_model=Envelope)
def simulate(body: SimulateRequest, g: str = Depends(graph_name)):
    return tools.simulate_fix(body.edge_ids, graph_name=g)


@app.post("/api/propose", response_model=Envelope)
def propose(body: ProposeRequest, g: str = Depends(graph_name)):
    return tools.propose_change(body.edge_ids, body.plan_note, graph_name=g)


@app.post("/api/decision", response_model=Envelope)
def decision(body: DecisionRequest, g: str = Depends(graph_name)):
    return tools.record_decision(body.decision_id, body.action, body.reason, graph_name=g)


@app.get("/api/decisions", response_model=Envelope)
def decisions(asset_name: str | None = Query(None, max_length=100), g: str = Depends(graph_name)):
    return tools.recall_decisions(asset_name, graph_name=g)


@app.post("/api/reset", response_model=Envelope)
def reset(g: str = Depends(graph_name)):
    """Drop and rebuild the demo environment (idempotent)."""
    start = time.perf_counter()
    summary = seed_graph(g)
    ms = round((time.perf_counter() - start) * 1000, 1)
    trace = [{"tool": "reset", "query": "seed_graph", "args": {"graph": g}, "ms": ms,
              "rows": summary["assets"] + summary["pivot_edges"]}]
    return {"outcome": "recorded", "data": summary, "paths": [], "trace": trace,
            "notes": "Demo environment reseeded from the deterministic generator."}
