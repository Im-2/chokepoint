"""The fixed catalogue of human-written tools. The model (or a REST button) picks a tool and
fills typed arguments; it never writes Cypher. Every tool returns the same envelope:

  {"outcome", "data", "paths", "trace", "notes"}

Every function takes an optional graph_name (default: the tenant graph "env:<tenant>").
Tests pass a "test:..." graph so they never touch the demo graph.
"""
import re
import time
import uuid
from datetime import datetime, timezone

from app import planner, queries
from app.db import get_client, tenant_graph_name

MAX_PATHS = 500  # hard cap on paths pulled from the graph in one query
NOT_MODELLED = ("This is not a statement that the asset is safe: the dependency may not be modelled "
                "in the graph.")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class ToolInputError(ValueError):
    """The caller sent a bad argument. Nothing was run."""


# ---------------------------------------------------------------- plumbing

class Run:
    """One tool call: holds the graph handle and records a trace of every query."""

    def __init__(self, tool: str, graph_name: str | None = None):
        self.tool = tool
        self.client = get_client()
        self.graph_name = graph_name or tenant_graph_name()
        self.graph = self.client.select_graph(self.graph_name)
        self.trace = []

    def _run(self, graph, query_name, cypher, params, read_only):
        start = time.perf_counter()
        result = (graph.ro_query if read_only else graph.query)(cypher, params or {})
        rows = result.result_set
        self.trace.append({"tool": self.tool, "query": query_name, "args": params or {},
                           "ms": round((time.perf_counter() - start) * 1000, 1), "rows": len(rows)})
        return result if not read_only else rows

    def read(self, query_name, cypher, params=None, graph=None):
        return self._run(graph or self.graph, query_name, cypher, params, True)

    def write(self, query_name, cypher, params=None, graph=None):
        return self._run(graph or self.graph, query_name, cypher, params, False)

    def envelope(self, outcome, data=None, paths=None, notes=""):
        return {"outcome": outcome, "data": data or {}, "paths": paths or [],
                "trace": self.trace, "notes": notes}


def _int(name, value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ToolInputError(f"{name} must be an integer from {low} to {high}")
    return value


def _name(name, value):
    if not isinstance(value, str) or not 1 <= len(value) <= 100:
        raise ToolInputError(f"{name} must be a string of 1 to 100 characters")
    return value


def _edge_ids(value, max_items):
    if not isinstance(value, list) or not 1 <= len(value) <= max_items:
        raise ToolInputError(f"edge_ids must be a list of 1 to {max_items} edge ids")
    for v in value:
        if not isinstance(v, str) or not ID_PATTERN.match(v):
            raise ToolInputError("edge ids may only contain letters, digits, '-' and '_'")
    return list(dict.fromkeys(value))  # drop duplicates, keep order


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path_dicts(rows):
    """attack_paths rows -> [{"nodes": [...], "edges": [...]}] (columns 3 and 4)."""
    return [{"nodes": r[3], "edges": r[4]} for r in rows]


def _resolve(run, names):
    """Name resolution. Returns (resolved dict name->row, list of unknown names).
    This runs BEFORE any traversal, so an unknown name never reaches a path query."""
    found, unknown = {}, []
    for n in names:
        rows = run.read("resolve_asset", queries.RESOLVE_ASSET, {"name": n})
        if rows:
            found[n] = {"id": rows[0][0], "name": rows[0][1], "kind": rows[0][2]}
        else:
            unknown.append(n)
    return found, unknown


def _unknown_asset(run, unknown):
    return run.envelope("unknown_asset", {"unknown": unknown},
                        notes=f"No asset named {', '.join(repr(u) for u in unknown)} exists in the "
                              "graph. Nothing was searched.")


# ---------------------------------------------------------------- tools

def find_attack_paths(depth: int = 8, limit: int = 50, graph_name: str | None = None) -> dict:
    """Enumerate attack paths from entry points to crown jewels, up to `depth` hops."""
    depth = _int("depth", depth, 1, queries.MAX_DEPTH)
    limit = _int("limit", limit, 1, 50)
    run = Run("find_attack_paths", graph_name)
    rows = run.read("attack_paths", queries.attack_paths(depth), {"limit": limit})
    if not rows:
        return run.envelope("not_in_graph", {"depth": depth, "count": 0},
                            notes=f"No modelled attack path within {depth} hops. {NOT_MODELLED}")
    data = {"depth": depth, "count": len(rows), "shortest_hops": rows[0][2],
            "truncated": len(rows) == limit}
    return run.envelope("answered_with_path", data, _path_dicts(rows))


def explain_reachability(from_name: str, to_name: str, graph_name: str | None = None) -> dict:
    """Cheapest (lowest attacker cost) path between two named assets, using algo.SPpaths."""
    from_name, to_name = _name("from_name", from_name), _name("to_name", to_name)
    run = Run("explain_reachability", graph_name)
    _, unknown = _resolve(run, [from_name, to_name])
    if unknown:
        return _unknown_asset(run, unknown)
    rows = run.read("shortest_path", queries.SHORTEST_PATH, {"from": from_name, "to": to_name})
    if not rows:
        return run.envelope("not_in_graph", {"from": from_name, "to": to_name},
                            notes=f"No modelled path from {from_name} to {to_name}. {NOT_MODELLED}")
    nodes, edges, weight = rows[0]
    return run.envelope("answered_with_path",
                        {"from": from_name, "to": to_name, "hops": len(edges), "attacker_cost": weight},
                        [{"nodes": nodes, "edges": edges}])


def rank_choke_edges(depth: int = 8, limit: int = 15, graph_name: str | None = None) -> dict:
    """Edges ranked by paths cut per unit of disruption. Also shows the naive ranking
    (most paths first) so the decoy trap is visible."""
    depth = _int("depth", depth, 1, queries.MAX_DEPTH)
    limit = _int("limit", limit, 1, 15)
    run = Run("rank_choke_edges", graph_name)
    total = len(run.read("attack_paths", queries.attack_paths(depth), {"limit": MAX_PATHS}))
    if total == 0:
        return run.envelope("not_in_graph", {"depth": depth, "total_paths": 0},
                            notes=f"No modelled attack path within {depth} hops, so there is nothing "
                                  f"to rank. {NOT_MODELLED}")
    freq = run.read("choke_edge_frequency", queries.choke_edge_frequency(depth))
    edges = [{"edge_id": r[0], "kind": r[1], "disruption": r[2], "fix_text": r[3], "from": r[4],
              "to": r[5], "paths_through": r[6], "score": round(r[6] / r[2], 2)} for r in freq]
    by_score = sorted(edges, key=lambda e: (-e["score"], -e["paths_through"], e["edge_id"]))[:limit]
    naive_top = max(edges, key=lambda e: (e["paths_through"], e["edge_id"]))
    return run.envelope("answered_with_path",
                        {"depth": depth, "total_paths": total, "ranked": by_score,
                         "naive_most_paths": naive_top},
                        notes="Ranked by paths_through / disruption. 'naive_most_paths' is the edge a "
                              "plain most-paths ranking would pick.")


def rank_load_bearing_assets(limit: int = 20, graph_name: str | None = None) -> dict:
    """Assets many shortest paths flow through (betweenness centrality), flagged if they also
    sit on an attack path."""
    limit = _int("limit", limit, 1, 20)
    run = Run("rank_load_bearing_assets", graph_name)
    rows = run.read("load_bearing", queries.LOAD_BEARING, {"limit": limit})
    on_path = set()
    for r in run.read("attack_paths", queries.attack_paths(queries.MAX_DEPTH), {"limit": MAX_PATHS}):
        on_path.update(r[0])
    ranked = [{"name": r[0], "kind": r[1], "score": round(r[2], 1), "on_attack_path": r[0] in on_path}
              for r in rows]
    return run.envelope("answered_with_path", {"algorithm": "algo.betweenness", "ranked": ranked},
                        notes="Centrality is computed over the whole graph, so busy ordinary assets "
                              "rank high too; on_attack_path marks the ones that matter for attacks.")


def plan_remediation(budget: int = 3, graph_name: str | None = None) -> dict:
    """Pick up to `budget` edges to remove, maximising paths cut per disruption. Skips edges
    that humans rejected earlier (read from memory in the graph)."""
    budget = _int("budget", budget, 1, 3)
    run = Run("plan_remediation", graph_name)
    path_rows = run.read("attack_paths", queries.attack_paths(queries.MAX_DEPTH), {"limit": MAX_PATHS})
    if not path_rows:
        return run.envelope("not_in_graph", {"budget": budget, "paths_total": 0},
                            notes=f"No modelled attack path, so no plan is needed. {NOT_MODELLED}")
    freq = run.read("choke_edge_frequency", queries.choke_edge_frequency(queries.MAX_DEPTH))
    info = {r[0]: {"kind": r[1], "disruption": r[2], "fix_text": r[3], "from": r[4], "to": r[5]}
            for r in freq}
    rejected = run.read("rejected_edges", queries.REJECTED_EDGES)
    excluded = {r[0] for r in rejected}

    steps, remaining, note = planner.greedy_plan([r[1] for r in path_rows], info, budget, excluded)
    plan = [{"edge_id": s["edge_id"], "from": info[s["edge_id"]]["from"], "to": info[s["edge_id"]]["to"],
             "kind": info[s["edge_id"]]["kind"], "fix_text": info[s["edge_id"]]["fix_text"],
             "disruption": s["disruption"], "paths_cut": s["paths_cut"]} for s in steps]
    total = len(path_rows)
    data = {"budget": budget, "method": "greedy weighted set cover (not provably optimal)",
            "plan": plan, "paths_total": total, "paths_cut": total - len(remaining),
            "paths_remaining": len(remaining),
            "total_disruption": sum(s["disruption"] for s in steps),
            "excluded_by_memory": [{"edge_id": r[0], "reason": r[1], "at": r[2],
                                    "on_attack_path": r[0] in info} for r in rejected]}
    return run.envelope("answered_with_path", data, _path_dicts(path_rows), note)


def simulate_fix(edge_ids: list, graph_name: str | None = None) -> dict:
    """Prove a fix on a scratch copy: copy the graph, delete the edges there, re-run the path
    search, report before/after, and always delete the copy."""
    edge_ids = _edge_ids(edge_ids, 5)
    run = Run("simulate_fix", graph_name)
    existing = {r[0] for r in run.read("existing_edges", queries.EXISTING_EDGES, {"ids": edge_ids})}
    missing = [e for e in edge_ids if e not in existing]
    if missing:
        return run.envelope("not_in_graph", {"missing_edge_ids": missing},
                            notes=f"Edge id(s) not found: {', '.join(missing)}. Nothing was simulated.")

    before = run.read("attack_paths", queries.attack_paths(queries.MAX_DEPTH), {"limit": MAX_PATHS})
    scratch_name = f"sim:{uuid.uuid4().hex[:12]}"
    scratch = run.graph.copy(scratch_name)
    try:
        for edge_id in edge_ids:
            run.write("delete_edge_in_scratch", queries.DELETE_EDGE, {"id": edge_id}, graph=scratch)
        after = run.read("attack_paths_after_fix", queries.attack_paths(queries.MAX_DEPTH),
                         {"limit": MAX_PATHS}, graph=scratch)
    finally:
        scratch.delete()  # free-tier memory is small: the scratch graph never outlives the call
    scratch_deleted = scratch_name not in run.client.list_graphs()

    data = {"edge_ids": edge_ids, "paths_before": len(before), "paths_after": len(after),
            "paths_cut": len(before) - len(after), "fully_cut": len(after) == 0,
            "remaining_via": [r[0] for r in after], "scratch_graph": scratch_name,
            "scratch_deleted": scratch_deleted}
    note = ("Verified on a scratch copy of the graph at depth 8: no modelled attack path remains."
            if not after else
            f"Verified on a scratch copy at depth 8: {len(after)} of {len(before)} paths remain. "
            "Not a complete fix on its own.")
    return run.envelope("verified_fix", data, _path_dicts(after), note)


def propose_change(edge_ids: list, plan_note: str | None = None, graph_name: str | None = None) -> dict:
    """Write a change proposal (one Decision per edge, status proposed), find the owning team
    by traversal, and produce a ticket and a config diff."""
    edge_ids = _edge_ids(edge_ids, 5)
    if plan_note is not None and (not isinstance(plan_note, str) or len(plan_note) > 500):
        raise ToolInputError("plan_note must be a string of at most 500 characters")
    run = Run("propose_change", graph_name)
    details = []
    for edge_id in edge_ids:
        rows = run.read("edge_details", queries.EDGE_DETAILS, {"id": edge_id})
        if not rows:
            return run.envelope("not_in_graph", {"missing_edge_ids": [edge_id]},
                                notes=f"Edge id {edge_id} not found. No proposal was written.")
        keys = ["edge_id", "kind", "disruption", "fix_kind", "fix_text", "src_id", "dst_id", "src",
                "dst", "owner_team", "owner_lead", "source_team"]
        details.append(dict(zip(keys, rows[0])))

    run_id, now = f"r-{uuid.uuid4().hex[:8]}", _now()
    decisions = []
    for d in details:
        decision_id = f"d-{uuid.uuid4().hex[:8]}"
        run.write("create_decision", queries.CREATE_DECISION,
                  {"src_id": d["src_id"], "dst_id": d["dst_id"], "id": decision_id,
                   "edge_id": d["edge_id"], "reason": plan_note or "", "at": now, "run": run_id})
        decisions.append({"decision_id": decision_id, "edge_id": d["edge_id"]})

    owners = sorted({d["owner_team"] for d in details if d["owner_team"]})
    lines = [f"# Change request {run_id}: cut attack paths to crown-jewel data", "",
             f"**Owning team(s):** {', '.join(owners) or 'unknown'}",
             "**Status:** proposed (needs human approval)", ""]
    if plan_note:
        lines += [f"**Note:** {plan_note}", ""]
    lines += ["| Edge | Change | Disruption (1-10) |", "|---|---|---|"]
    lines += [f"| {d['edge_id']} | {d['fix_text']} | {d['disruption']} |" for d in details]
    diff = ["--- current", "+++ proposed"]
    for d in details:
        diff += [f"# {d['fix_text']}  (edge {d['edge_id']}, owner {d['owner_team']})",
                 f"- {d['kind']}: {d['src']} -> {d['dst']}"]
    data = {"run": run_id, "decisions": decisions, "status": "proposed", "owner_teams": owners,
            "owners": [{"edge_id": d["edge_id"], "team": d["owner_team"], "lead": d["owner_lead"]}
                       for d in details],
            "ticket_markdown": "\n".join(lines), "config_diff": "\n".join(diff)}
    return run.envelope("proposed", data, notes="Proposal recorded in the graph. A human must approve "
                                                "or reject it.")


def record_decision(decision_id: str, action: str, reason: str | None = None,
                    graph_name: str | None = None) -> dict:
    """A human approves or rejects. decision_id may be one decision id or a run id (all edges
    of one proposal). Rejections must carry a reason: it becomes memory."""
    decision_id = _name("decision_id", decision_id)
    if action not in ("approve", "reject"):
        raise ToolInputError("action must be 'approve' or 'reject'")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 300):
        raise ToolInputError("reason must be a string of at most 300 characters")
    if action == "reject" and not (reason and reason.strip()):
        raise ToolInputError("a rejection needs a reason, so the planner can learn from it")
    status = "approved" if action == "approve" else "rejected"
    run = Run("record_decision", graph_name)
    rows = run.write("update_decision", queries.UPDATE_DECISION,
                     {"id": decision_id, "status": status, "reason": reason or "", "at": _now()}).result_set
    if not rows:
        return run.envelope("not_in_graph", {"decision_id": decision_id},
                            notes="No still-proposed decision has that id, so nothing was changed.")
    return run.envelope("recorded", {"status": status, "reason": reason or "",
                                     "decided": [{"decision_id": r[0], "edge_id": r[1]} for r in rows]})


def recall_decisions(asset_name: str | None = None, graph_name: str | None = None) -> dict:
    """Read past decisions from memory (newest first), optionally about one asset."""
    run = Run("recall_decisions", graph_name)
    if asset_name is None:
        rows = run.read("recall_all", queries.RECALL_ALL)
    else:
        asset_name = _name("asset_name", asset_name)
        _, unknown = _resolve(run, [asset_name])
        if unknown:
            return _unknown_asset(run, unknown)
        rows = run.read("recall_for_asset", queries.RECALL_FOR_ASSET, {"name": asset_name})
    decisions = [{"decision_id": r[0], "edge_id": r[1], "status": r[2], "reason": r[3], "at": r[4],
                  "run": r[5], "assets": r[6]} for r in rows]
    if not decisions:
        return run.envelope("not_in_graph", {"decisions": []},
                            notes="No decisions are recorded" + (f" about {asset_name}." if asset_name else "."))
    return run.envelope("answered_from_memory", {"decisions": decisions})


# Name -> (function, description). The MCP server and the router read this one registry.
TOOLS = {
    "find_attack_paths": (find_attack_paths, "Enumerate attack paths from entry points to crown jewels up to a depth (max 8)."),
    "explain_reachability": (explain_reachability, "Cheapest path between two named assets, or 'not in graph'."),
    "rank_choke_edges": (rank_choke_edges, "Rank edges by attack paths cut per unit of business disruption."),
    "rank_load_bearing_assets": (rank_load_bearing_assets, "Rank assets by betweenness centrality."),
    "plan_remediation": (plan_remediation, "Choose up to 3 edges to remove (greedy), skipping edges humans rejected before."),
    "simulate_fix": (simulate_fix, "Prove a fix on a scratch copy of the graph: paths before and after."),
    "propose_change": (propose_change, "Record a change proposal with owner, ticket and config diff."),
    "record_decision": (record_decision, "Record a human's approve or reject (reject needs a reason)."),
    "recall_decisions": (recall_decisions, "Read past decisions from memory."),
}
