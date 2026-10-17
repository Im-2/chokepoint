"""FastAPI app. Every non-chat endpoint calls a tool function directly (no LLM involved)."""
import collections
import contextlib
import hmac
import json
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app import agent, config, queries, tools
from app.db import get_client, tenant_graph_name
from app.models import (ChatRequest, ChokeRequest, DecisionRequest, Envelope, GraphResponse, PlanRequest,
                        ProposeRequest, ReachRequest, ScanRequest, SimulateRequest)
from app.mcp_server import mcp_asgi_app, mcp_server
from app.seed import seed_graph


@contextlib.asynccontextmanager
async def lifespan(_app):
    # A mounted sub-app's own lifespan never runs, so the MCP session manager is started here.
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan, title="Chokepoint", version="0.1.0",
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
def reset(g: str = Depends(graph_name), x_reset_token: str | None = Header(None)):
    """Drop and rebuild the demo environment (idempotent). Needs the X-Reset-Token header
    to match the RESET_TOKEN env var; if RESET_TOKEN is empty, reset is disabled."""
    if not config.RESET_TOKEN:
        raise HTTPException(status_code=403, detail="Reset is disabled: RESET_TOKEN is not set on the server")
    if not x_reset_token or not hmac.compare_digest(x_reset_token, config.RESET_TOKEN):
        raise HTTPException(status_code=401, detail="Missing or wrong X-Reset-Token header")
    start = time.perf_counter()
    summary = seed_graph(g)
    ms = round((time.perf_counter() - start) * 1000, 1)
    trace = [{"tool": "reset", "query": "seed_graph", "args": {"graph": g}, "ms": ms,
              "rows": summary["assets"] + summary["pivot_edges"]}]
    return {"outcome": "recorded", "data": summary, "paths": [], "trace": trace,
            "notes": "Demo environment reseeded from the deterministic generator."}


# Best-effort rate limit for /api/chat. Each serverless instance counts separately, so this only
# slows down casual abuse; it is not a security boundary.
CHAT_LIMIT, CHAT_WINDOW_S = 20, 60
_chat_hits: dict[str, collections.deque] = collections.defaultdict(collections.deque)


def _rate_limited(client_id: str) -> bool:
    now, hits = time.monotonic(), _chat_hits[client_id]
    while hits and now - hits[0] > CHAT_WINDOW_S:
        hits.popleft()
    if len(hits) >= CHAT_LIMIT:
        return True
    hits.append(now)
    return False


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request, g: str = Depends(graph_name)):
    """Server-sent events: tool_call, tool_result, final {text, checked}. Uses a free LLM when one
    is configured and CHAT_ENABLED is true; otherwise (or on any LLM failure) the no-LLM router."""
    if _rate_limited(request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="Too many chat requests; try again in a minute")

    async def stream():
        async for ev in agent.run_chat(body.message, [h.model_dump() for h in body.history], g):
            yield f"event: {ev['event']}\ndata: {json.dumps(ev)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# MCP over stateless streamable HTTP at /mcp. Mounted last so every /api route wins first.
app.mount("/", mcp_asgi_app)
