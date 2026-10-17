"""The API contract (pydantic). The frontend is built against exactly these shapes;
FastAPI turns them into the /docs page."""
from typing import Any, Literal

from pydantic import BaseModel, Field

Outcome = Literal["answered_with_path", "answered_from_memory", "not_in_graph", "unknown_asset",
                  "verified_fix", "proposed", "recorded"]


# ---- requests (limits mirror the tool validation, which is the real guard) ----
class ScanRequest(BaseModel):
    depth: int = Field(8, ge=1, le=8, description="Maximum hops from an entry point")


class ReachRequest(BaseModel):
    from_name: str = Field(..., min_length=1, max_length=100)
    to_name: str = Field(..., min_length=1, max_length=100)


class ChokeRequest(BaseModel):
    depth: int = Field(8, ge=1, le=8)
    limit: int = Field(15, ge=1, le=15)


class PlanRequest(BaseModel):
    budget: int = Field(3, ge=1, le=3, description="Maximum number of edges to remove")


class SimulateRequest(BaseModel):
    edge_ids: list[str] = Field(..., min_length=1, max_length=5)


class ProposeRequest(BaseModel):
    edge_ids: list[str] = Field(..., min_length=1, max_length=5)
    plan_note: str | None = Field(None, max_length=500)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)


class DecisionRequest(BaseModel):
    decision_id: str = Field(..., min_length=1, max_length=100,
                             description="A decision id, or the run id of a whole proposal")
    action: Literal["approve", "reject"]
    reason: str | None = Field(None, max_length=300, description="Required when rejecting")


# ---- responses ----
class Node(BaseModel):
    id: str
    name: str
    kind: str


class Edge(BaseModel):
    id: str
    kind: str


class Path(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


class TraceEntry(BaseModel):
    tool: str
    query: str
    args: dict[str, Any]
    ms: float
    rows: int


class Envelope(BaseModel):
    outcome: Outcome
    data: dict[str, Any]
    paths: list[Path]
    trace: list[TraceEntry]
    notes: str


class GraphNode(BaseModel):
    id: str
    name: str
    kind: str
    entry: bool
    crown: bool
    owner_team: str


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str
    cost: int
    disruption: int


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    trace: list[TraceEntry]
