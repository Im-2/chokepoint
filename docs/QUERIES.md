# Queries and algorithms

Every Cypher string lives in `app/queries.py`. This page explains each one in plain English and
names the tool that uses it. Read queries run with `ro_query`; only the three write queries at the
bottom of `queries.py` change data.

## Rule: parameters, except `depth`

All names, ids and other values are passed as **query parameters**, never concatenated.

One deliberate exception, verified on FalkorDB Cloud: **FalkorDB rejects a parameter as a
variable-length bound.** `-[:PIVOT*1..$depth]->` fails with *"Encountered unhandled type in inlined
properties"*. So `depth` is validated in Python as an **integer from 1 to 8** (`checked_depth`) and
written into the query text. Only that checked integer is ever inlined. Asset names and ids remain
parameters, so a model or user cannot inject Cypher through them (tested in `tests/test_tools.py`).

## Reads

| Query | What it does | Used by |
|---|---|---|
| `RESOLVE_ASSET` | Looks an asset up by exact name. Runs before any tool that takes a name; no match means `unknown_asset` and no traversal runs. | explain_reachability, recall_decisions |
| `attack_paths(depth)` | Every path from an `entry:true` asset to a `crown:true` asset along `PIVOT` edges, up to `depth` hops, shortest first, with node and edge details. `LIMIT $limit`. | find_attack_paths, plan_remediation, simulate_fix, rank_choke_edges, rank_load_bearing_assets |
| `choke_edge_frequency(depth)` | Runs the same search, `UNWIND`s each path into its edges and counts `DISTINCT` paths per edge (`paths_through`), with disruption, fix text and end points. | rank_choke_edges, plan_remediation |
| `SHORTEST_PATH` | `algo.SPpaths` weighted by the edge `cost` property: the cheapest route for an attacker between two named assets. | explain_reachability |
| `LOAD_BEARING` | `algo.betweenness` over `PIVOT`; sampling size above the node count and a fixed seed make it repeatable. | rank_load_bearing_assets |
| `CROWN_JEWELS` | Names of every crown jewel (`crown:true`), so a question about one asset can be checked against all of them. | explain_reachability (without `to_name`) |
| `EXISTING_EDGES` | Which of these edge ids exist? | simulate_fix |
| `EDGE_DETAILS` | One edge with its end points and the **owner team of the destination asset** (found by traversing `OWNS`). | propose_change |
| `REJECTED_EDGES` | Edge ids humans rejected, with reasons. This is the planner's memory. | plan_remediation |
| `RECALL_ALL`, `RECALL_FOR_ASSET` | Past decisions, newest first, with the assets they are about. | recall_decisions |
| `GRAPH_NODES`, `GRAPH_EDGES` | The whole graph for drawing. | GET /api/graph |

## Writes

| Query | What it does | Used by |
|---|---|---|
| `DELETE_EDGE` | Removes one `PIVOT` edge. **Only ever run on a scratch `sim:` graph.** | simulate_fix |
| `CREATE_DECISION` | Writes a `Decision` (status `proposed`) linked with `ABOUT` to both end points. | propose_change |
| `UPDATE_DECISION` | Sets a proposed decision (or all decisions of one proposal run) to approved or rejected, with the reason and time. | record_decision |

## Scratch-graph simulation (not a Cypher string)
`simulate_fix` uses the client's `graph.copy("sim:<uuid>")` (FalkorDB `GRAPH.COPY`), deletes the
chosen edges in the copy, re-runs `attack_paths`, then `graph.delete()` in a `finally` block and
checks the copy is gone. The free Cloud instance has little memory, so a scratch graph never
outlives the call.

## Verified on FalkorDB Cloud
`algo.SPpaths` (argument names as in the brief), `algo.pageRank('Asset','PIVOT')`,
`algo.betweenness({nodeLabels, relationshipTypes, samplingSize, samplingSeed})`, `count(DISTINCT p)`
after `UNWIND relationships(p)`, map projections in list comprehensions, `startNode(r)`/`endNode(r)`,
`graph.copy()`, `graph.delete()`, parameter maps on `ro_query`, and `CREATE INDEX` on `Asset(id)` and
`Asset(name)`. `algo.pageRank` works but is not used: betweenness better matches "load-bearing".
