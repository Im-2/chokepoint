# Queries and algorithms

Every Cypher string lives in `app/queries.py`. This page explains each one in plain English.
(Phase 1 has the first two; later phases add the rest.)

## Rule: parameters, except `depth`

All names, ids and other values are passed as **query parameters**, never concatenated.

One deliberate exception, verified on FalkorDB Cloud: **FalkorDB rejects a parameter as a
variable-length bound.** `-[:PIVOT*1..$depth]->` fails with *"Encountered unhandled type in inlined
properties"*. So `depth` is validated in Python as an **integer from 1 to 8** (`checked_depth`) and
written into the query text. Only that checked integer is ever inlined. Asset names and ids remain
parameters, so a model or user cannot inject Cypher through them.

## `attack_paths(depth)`
Finds every path from an entry asset (`entry:true`) to a crown jewel (`crown:true`) following
`PIVOT` edges up to `depth` hops, shortest first. Returns the asset names, the edge ids and the hop
count. Used by `find_attack_paths`, the planner and `simulate_fix`.

## `choke_edge_frequency(depth)`
Runs the same path search, unwinds each path into its edges, and counts `DISTINCT` paths per edge
(`paths_through`). An edge with a high count is a candidate choke point. Used by `rank_choke_edges`.
Verified: `count(DISTINCT p)` after `UNWIND relationships(p)` works on FalkorDB Cloud.

## Verified algorithms (on FalkorDB Cloud)
- `algo.SPpaths({sourceNode, targetNode, relTypes, relDirection, weightProp, pathCount})`: shortest weighted path.
- `algo.pageRank('Asset','PIVOT')`: load-bearing assets.
- `algo.betweenness({nodeLabels, relationshipTypes, samplingSize})`: approximate (samples source nodes).
- `GRAPH.COPY` via the client's `graph.copy(name)` and `graph.delete()`: scratch-graph simulation.
