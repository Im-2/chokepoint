"""ALL Cypher lives here, named and documented.

Rules:
  * Names, ids and other values are ALWAYS query parameters.
  * Exception: FalkorDB rejects a parameter as a variable-length bound (*1..$depth),
    so `depth` is validated as an int 1..MAX_DEPTH and written into the query text.
    Only that checked int is ever inlined, never user or model text.
  * Read queries are run with ro_query. Only the write queries at the bottom change data.
"""

MAX_DEPTH = 8


def checked_depth(depth) -> int:
    """Return depth as a plain int in 1..MAX_DEPTH, or raise ValueError."""
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= MAX_DEPTH:
        raise ValueError(f"depth must be an integer from 1 to {MAX_DEPTH}")
    return depth


# ---------------------------------------------------------------- reads

# Name resolution. Runs before every tool that takes an asset name.
RESOLVE_ASSET = "MATCH (a:Asset {name:$name}) RETURN a.id AS id, a.name AS name, a.kind AS kind"


def attack_paths(depth: int) -> str:
    """Every path from an entry asset (entry:true) to a crown jewel (crown:true) following
    PIVOT edges up to `depth` hops, shortest first. Parameter: $limit.
    Columns: names, edge ids, hop count, then node and edge details for drawing the path.
    Used by: find_attack_paths, plan_remediation, simulate_fix, rank_load_bearing_assets."""
    d = checked_depth(depth)
    return (
        f"MATCH p = (e:Asset {{entry:true}})-[:PIVOT*1..{d}]->(t:Asset {{crown:true}}) "
        "RETURN [n IN nodes(p) | n.name] AS via, "
        "[r IN relationships(p) | r.id] AS edge_ids, "
        "length(p) AS hops, "
        "[n IN nodes(p) | {id:n.id, name:n.name, kind:n.kind}] AS nodes, "
        "[r IN relationships(p) | {id:r.id, kind:r.kind}] AS edges "
        "ORDER BY hops LIMIT $limit"
    )


def choke_edge_frequency(depth: int) -> str:
    """For every edge that sits on at least one attack path: how many DISTINCT paths go
    through it (paths_through), plus its disruption, fix text and end points.
    Used by: rank_choke_edges, plan_remediation."""
    d = checked_depth(depth)
    return (
        f"MATCH p = (e:Asset {{entry:true}})-[:PIVOT*1..{d}]->(t:Asset {{crown:true}}) "
        "UNWIND relationships(p) AS r "
        "RETURN r.id AS edge_id, r.kind AS kind, r.disruption AS disruption, r.fix_text AS fix_text, "
        "startNode(r).name AS src, endNode(r).name AS dst, count(DISTINCT p) AS paths_through "
        "ORDER BY paths_through DESC, edge_id"
    )


# Shortest path by attacker cost, via FalkorDB's algo.SPpaths. Parameters: $from, $to.
SHORTEST_PATH = (
    "MATCH (a:Asset {name:$from}), (b:Asset {name:$to}) "
    "CALL algo.SPpaths({sourceNode:a, targetNode:b, relTypes:['PIVOT'], relDirection:'outgoing', "
    "weightProp:'cost', pathCount:1}) YIELD path, pathWeight "
    "RETURN [n IN nodes(path) | {id:n.id, name:n.name, kind:n.kind}] AS nodes, "
    "[r IN relationships(path) | {id:r.id, kind:r.kind}] AS edges, pathWeight"
)

# Betweenness centrality over PIVOT edges. samplingSize above the node count and a fixed
# seed make the "approximate" algorithm repeatable here.
LOAD_BEARING = (
    "CALL algo.betweenness({nodeLabels:['Asset'], relationshipTypes:['PIVOT'], "
    "samplingSize:200, samplingSeed:7}) YIELD node, score "
    "RETURN node.name AS name, node.kind AS kind, score ORDER BY score DESC LIMIT $limit"
)

# Do these edges exist? Parameter: $ids (list of edge ids).
EXISTING_EDGES = "MATCH ()-[r:PIVOT]->() WHERE r.id IN $ids RETURN r.id AS edge_id"

# Edge details for tickets. Owner = the team that owns the DESTINATION asset (the thing being
# protected; for a trust or permission change that is where the change is made).
EDGE_DETAILS = (
    "MATCH (a:Asset)-[r:PIVOT {id:$id}]->(b:Asset) "
    "OPTIONAL MATCH (t:Team)-[:OWNS]->(b) "
    "OPTIONAL MATCH (s:Team)-[:OWNS]->(a) "
    "RETURN r.id AS edge_id, r.kind AS kind, r.disruption AS disruption, r.fix_kind AS fix_kind, "
    "r.fix_text AS fix_text, a.id AS src_id, b.id AS dst_id, a.name AS src, b.name AS dst, "
    "t.name AS owner_team, t.lead AS owner_lead, s.name AS source_team"
)

# Memory: edges humans rejected, so the planner never picks them again.
REJECTED_EDGES = ("MATCH (d:Decision {status:'rejected'}) "
                  "RETURN d.edge_id AS edge_id, d.reason AS reason, d.at AS at ORDER BY d.at")

# Memory: past decisions, newest first. Optional filter by asset name via RECALL_FOR_ASSET.
RECALL_ALL = (
    "MATCH (d:Decision) OPTIONAL MATCH (d)-[:ABOUT]->(a:Asset) "
    "RETURN d.id AS id, d.edge_id AS edge_id, d.status AS status, d.reason AS reason, "
    "d.at AS at, d.run AS run, collect(a.name) AS assets ORDER BY at DESC, id"
)
RECALL_FOR_ASSET = (
    "MATCH (d:Decision)-[:ABOUT]->(:Asset {name:$name}) "
    "OPTIONAL MATCH (d)-[:ABOUT]->(a:Asset) "
    "RETURN d.id AS id, d.edge_id AS edge_id, d.status AS status, d.reason AS reason, "
    "d.at AS at, d.run AS run, collect(a.name) AS assets ORDER BY at DESC, id"
)

# Whole graph for the UI (/api/graph).
GRAPH_NODES = ("MATCH (a:Asset) RETURN a.id AS id, a.name AS name, a.kind AS kind, a.entry AS entry, "
               "a.crown AS crown, a.owner_team AS owner_team ORDER BY a.id")
GRAPH_EDGES = ("MATCH (a:Asset)-[r:PIVOT]->(b:Asset) RETURN r.id AS id, a.id AS source, b.id AS target, "
               "r.kind AS kind, r.cost AS cost, r.disruption AS disruption ORDER BY r.id")

# ---------------------------------------------------------------- writes

# Simulation: remove one edge from a SCRATCH graph (never run on the tenant graph).
DELETE_EDGE = "MATCH ()-[r:PIVOT {id:$id}]->() DELETE r"

# Memory write: a proposed change about one edge, linked to both end points.
CREATE_DECISION = (
    "MATCH (a:Asset {id:$src_id}), (b:Asset {id:$dst_id}) "
    "CREATE (d:Decision {id:$id, edge_id:$edge_id, status:'proposed', reason:$reason, at:$at, run:$run}) "
    "CREATE (d)-[:ABOUT]->(a), (d)-[:ABOUT]->(b)"
)

# Memory write: a human approves or rejects. $id may be a decision id OR a run id (all edges of one
# proposal). Only still-proposed decisions can be decided.
UPDATE_DECISION = (
    "MATCH (d:Decision) WHERE (d.id = $id OR d.run = $id) AND d.status = 'proposed' "
    "SET d.status = $status, d.reason = $reason, d.at = $at "
    "RETURN d.id AS id, d.edge_id AS edge_id"
)
