"""ALL Cypher lives here, named and documented. (Started in Phase 1; Phase 2 adds the rest.)

Rules:
  * Names, ids and other values are ALWAYS query parameters.
  * Exception: FalkorDB rejects a parameter as a variable-length bound (*1..$depth),
    so `depth` is validated as an int 1..MAX_DEPTH and written into the query text.
    Only that checked int is ever inlined, never user or model text.
"""

MAX_DEPTH = 8


def checked_depth(depth) -> int:
    """Return depth as a plain int in 1..MAX_DEPTH, or raise ValueError."""
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= MAX_DEPTH:
        raise ValueError(f"depth must be an integer from 1 to {MAX_DEPTH}")
    return depth


def attack_paths(depth: int) -> str:
    """Every path from an entry point to a crown jewel, up to `depth` hops, shortest first.
    Used by: find_attack_paths, plan_remediation, simulate_fix."""
    d = checked_depth(depth)
    return (
        f"MATCH p = (e:Asset {{entry:true}})-[:PIVOT*1..{d}]->(t:Asset {{crown:true}}) "
        "RETURN [n IN nodes(p) | n.name] AS via, "
        "[r IN relationships(p) | r.id] AS edge_ids, "
        "length(p) AS hops "
        "ORDER BY hops"
    )


def choke_edge_frequency(depth: int) -> str:
    """For each edge: how many distinct attack paths go through it.
    Used by: rank_choke_edges."""
    d = checked_depth(depth)
    return (
        f"MATCH p = (e:Asset {{entry:true}})-[:PIVOT*1..{d}]->(t:Asset {{crown:true}}) "
        "UNWIND relationships(p) AS r "
        "RETURN r.id AS edge_id, r.kind AS kind, r.disruption AS disruption, "
        "r.fix_text AS fix_text, count(DISTINCT p) AS paths_through "
        "ORDER BY paths_through DESC"
    )
