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

### MCP: the same tools, discovered not hard-coded
`app/mcp_server.py` wraps the nine tools with typed arguments using the official Python MCP SDK
(v2.x, where FastMCP is now called `MCPServer`). It is mounted at `/mcp` as **stateless streamable
HTTP** (every request is independent, no session ids), which is what serverless needs. The agent
does not keep a private tool list: it connects to the same server over the SDK's in-memory
transport, lists the tools and gives them to the model. REST, MCP and the agent all call the same
functions, and a test checks that an MCP result equals the REST result.
DNS-rebinding protection is switched off on purpose (it protects a developer's localhost; this is a
public API on a real hostname). The write tools (`propose_change`, `record_decision`) are exposed on
`/mcp` like on REST, with no authentication; only `/api/reset` has a token.

### Two ways to answer: router and LLM, one safety net
`CHAT_ENABLED=false`, no API key, a rate limit or any LLM error all lead to the **router**: regex
rules pick a tool and a template writes one sentence from the tool rows. With a free LLM (Groq
first, Gemini second) the model picks tools (at most 6 calls) and writes one sentence. The
**answer checker** then runs on that sentence: every asset name and edge id must appear in the tool
results, every number must appear there too (0 to 10 are always allowed), "safe" is rejected unless
negated, no claims of impact when nothing was found, "verified" only after `simulate_fix`, and the
agent can never claim to approve or reject. If the checker rejects it, the templated sentence is
returned with `checked: false` and the reason. Unicode dashes are folded to `-` first, so a name
written with a non-breaking hyphen cannot slip past. The checker treats any hyphenated word as a
name, so ordinary hyphenated words get rejected too: that errs on the safe side, and the system
prompt asks the model to avoid them.
The model never sees `record_decision`: it is not offered and, if the model asks for it anyway, it
is refused. Only humans decide.

### Free-tier limits shaped the design
Tool results are compacted before the model sees them (names and numbers, no trace, at most 4,500
characters), the system prompt is short, and tool descriptions are trimmed, because free tiers allow
only about 6,000 tokens a minute. Full detail goes to the HTTP response (the frontend), not the model.

## Judge questions (15 likely, with short answers)

1. **What does FalkorDB do here that Postgres could not?**
   Variable-length path enumeration, per-edge path counts, weighted shortest path, betweenness, and
   `GRAPH.COPY` for scratch-graph simulation. In SQL these are recursive CTEs with no built-in
   algorithms, and a copy-edit-requery simulation would mean copying tables.
2. **Why one relationship type, `PIVOT`?**
   Path patterns and the algorithms take a relationship type. One type with a `kind` property keeps
   `*1..N` patterns and `algo.SPpaths` simple.
3. **Why does the model never write Cypher?**
   Safety and reliability. A fixed catalogue of nine human-written, parameterised tools means the
   model can only choose a tool and fill typed arguments. Names are resolved against the graph first.
4. **How do you stop injection?**
   Names and ids are always query parameters. The only inlined value is `depth`, validated as an
   integer 1 to 8 (FalkorDB rejects a parameter in `*1..$depth`, which we tested). Tests throw quotes
   and Cypher fragments at the name arguments and check the graph is unchanged.
5. **What is the decoy edge and why does it matter?**
   `role-prod-admin -> prod-customer-db` is on 15 of 19 paths but disruption 9. Ranking by raw path
   count picks it; paths cut per disruption picks `role-ci-deployer -> role-prod-admin` (11 paths,
   disruption 2). It shows why the planner is cost-aware.
6. **Is the plan optimal?**
   No. It is weighted set cover (NP-hard), solved greedily, and every plan says so. It stops when no
   paths remain and never picks an edge that cuts nothing.
7. **How do you prove a fix works?**
   Copy the graph to `sim:<uuid>`, delete the edges there, re-run the same path query, report
   before and after (19 -> 0), then delete the copy in a `finally`. The real graph is never touched,
   and the agent may only say "verified" if `simulate_fix` ran.
8. **How does memory work, and why in the graph?**
   A proposal creates `Decision` nodes linked to the assets. A rejection (with a reason) is read by
   the planner next time and that edge is excluded. Because it is in the graph, it survives restarts
   and any server instance sees it.
9. **What if the LLM lies?**
   The answer checker verifies every model sentence: names, edge ids and numbers must appear in the
   tool results; no "safe"; no impact claims when nothing was found; no "verified" without
   `simulate_fix`; no "cannot reach" for an unmodelled path. On failure the templated sentence is
   returned with `checked: false`.
10. **Does it work without an LLM?**
    Yes. A deterministic router maps keywords to tools and templates the sentence. `CHAT_ENABLED=false`
    forces it, and it is also the fallback on rate limits or errors. All buttons use it too.
11. **Why MCP, and how is the agent connected to it?**
    MCP gives any client the same nine tools. The agent lists the tools over the SDK's in-memory
    transport rather than keeping a private list, and a test checks the MCP result equals the REST result.
12. **Why is the MCP server stateless, and what does that cost?**
    Serverless functions cannot hold sessions. Stateless streamable HTTP treats every request alone,
    so server-initiated features are unavailable, which we do not need.
13. **What does "no path" mean?**
    "Not modelled", never "safe". Depth 2 returns nothing because the shortest path is 4 hops, and the
    note says the dependency may not be modelled.
14. **What are the weaknesses?**
    Synthetic and small data, greedy plan, depth cap of 8, open write tools except reset, strict
    answer checker, Cloud latency of about 130 to 250 ms per query, and Docker/Gemini paths untested.
15. **What did the AI do, and what did you do?**
    Claude Code wrote code under direction; the developer reviewed the model, the queries and the
    design decisions in this file and can explain each one. One example found by testing rather than
    assuming: FalkorDB rejects a parameter as a path-depth bound, a fact that changed the design.
