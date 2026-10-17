# Walkthrough (study guide)

This file grows each phase. Everything here should be something you can explain out loud.

## Design decisions

### One relationship type, `PIVOT`, with a `kind` property
Every attack-relevant edge is `PIVOT`. Variable-length patterns (`-[:PIVOT*1..4]->`) and the
algorithms (`SPpaths`, `pageRank`) take a relationship type, so one type keeps all of them simple.
The `kind` (assume_role, network, ...) says what the hop means.

### Why `depth` is inlined but names are not
FalkorDB rejects a parameter as a variable-length bound, so `*1..$depth` does not work (we tested it
on Cloud). `depth` is validated as an integer from 1 to 8 and written into the query text. This is
safe because only a checked integer can get there. Asset names and ids are always parameters.
Test 6 (injection safety) proves names are treated as data.

### Synthetic seed: a small core plus a large noise region
`app/seed.py` has ~19 hand-written "core" assets where all attack paths live, and ~110 generated
"noise" assets. Noise edges only go noise to noise or core to noise, and crown jewels have no
outgoing edges, so noise adds realism but can never create a path to a crown jewel. That is why the
path count is controlled and the numbers are stable. The generator is seeded (`random.Random(7)`).
The planted traps: a hidden 4-hop route through the forgotten `svc-legacy-etl`; a cheap choke edge
(`role-ci-deployer -> role-prod-admin`, disruption 2); a decoy (`role-prod-admin -> prod-customer-db`,
on the most paths but disruption 9); and a bypass through `jump-host-01` so one fix is not enough.

### A fixed tool catalogue and one response envelope
`app/tools.py` has nine human-written tools. A model or a REST button picks one and fills typed
arguments; nobody but us writes Cypher. Every tool validates its arguments first, resolves asset
names against the graph (unknown name: `unknown_asset`, and the trace proves no traversal ran), and
returns `{outcome, data, paths, trace, notes}`. "No path" is always `not_in_graph` with a note that
the dependency may not be modelled, never "safe". The trace (query name, arguments, ms, row count) is
built per call, so the server stores nothing.

### Greedy planner
The graph enumerates every attack path (path search is the graph's job). `app/planner.py` then
solves "pick few edges to cut them all": weighted set cover, which is NP-hard, so we use the standard
greedy rule: repeatedly take the edge with the best (new paths cut / disruption). It stops as soon as
no paths remain, never picks an edge that cuts nothing, skips edges humans rejected, and says plainly
when budget is left over or paths remain. It is a heuristic, not provably optimal, and every plan says so.

### The decoy and why cost-aware ranking matters
`role-prod-admin -> prod-customer-db` is on the most paths (15 of 19) but has disruption 9. A
"most paths" ranking picks it. `role-ci-deployer -> role-prod-admin` is on 11 and has disruption 2,
so paths-per-disruption picks that. `rank_choke_edges` returns both so the trap is visible.

### Scratch-graph simulation
`simulate_fix` copies the tenant graph (`GRAPH.COPY`) to `sim:<uuid>`, deletes the chosen edges
there, re-runs the same path search and reports before/after, then deletes the copy in a `finally`.
The real graph is never touched, and a fix is only called "verified" when this ran.

### Memory lives in the graph
A proposal writes one `Decision` per edge (status `proposed`, linked with `ABOUT` to both ends). A
human approves or rejects (a rejection needs a reason). The planner reads rejected edges from the
graph before choosing, so memory survives across sessions and servers.
Reject-and-replan on the seed: reject `role-ci-deployer -> role-prod-admin` ("CI needs prod-admin
during releases") and the budget-3 plan becomes `svc-legacy-etl` trust (disruption 1), `jump-host-01`
trust (3) and `svc-backup-agent` trust (2): 15 of 19 paths cut at total disruption 6, with 4 paths
honestly left over. The decoy is not used.

### Owner team
`propose_change` finds the team that owns the edge's **destination** asset by traversing `OWNS`
(the change is made on the protected resource, e.g. the role's trust policy).

## Judge questions
(Filled in at Phase 6.)
