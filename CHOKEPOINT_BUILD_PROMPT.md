# CHOKEPOINT — Build Brief for Claude Code

You are building **Chokepoint**, a hackathon project, with a human developer who must be able to explain every part of it. Read this whole file before writing code. Work in the phases in section 13. **Backend first. The frontend comes later from the human's own design and is NOT part of Phases 0–6.**

---

## 0. Context and hard constraints

**Event:** Graph Hacks: Context for AI Agents (WeMakeDevs x FalkorDB). **Track 01 — Agents That Act on Connected Data.**
**Deadline:** Oct 18, 2026, 11:59 PM IST (= 7:29 PM WAT). Internal target: submitted by 3 PM WAT on Oct 18.

Rules that decide whether we are disqualified or ignored:

1. **FalkorDB must be the primary database and the product must not work without it.** The graph must do the work: path enumeration, choke-edge ranking, shortest path, centrality, scratch-graph simulation, and decision memory all run in FalkorDB. If a feature could be done equally well with Postgres, redesign it.
2. **Data must be synthetic** (we generate it). No real credentials, no real infrastructure data, ever.
3. **Required deliverables:** public repo; README with setup + the graph data model; the Cypher queries / algorithms the product depends on; a demo video; live deployment (or complete local setup instructions); the track named (Track 01).
4. **AI assistant use must be disclosed** (README section, see 12). The human must be able to explain the graph model, queries, architecture and decisions, and "entirely AI-generated with no human understanding" can be rejected. So: **keep code simple, comment decision points, avoid clever abstractions, and produce `docs/WALKTHROUGH.md`** (section 12).
5. All implementation is new work created during the event.

What the sponsor has said they reward (from their own blog): the graph doing work a database join could not; multi-hop answers where depth matters; a **fixed catalogue of human-written, parameterised tools exposed over MCP** (the model never writes Cypher); **names resolved against the graph before anything runs**; the **path returned with every answer**; and **honest "not in the graph"** answers instead of confident guesses. Build to that.

**Cost constraint:** the human will not pay for any LLM/agent API. Everything LLM-related must work on free tiers, and **the whole product must also work with no LLM at all** (section 7).

---

## 1. The product

**One line:** An agent that finds the attack paths from the internet to a company's crown-jewel data in its cloud environment graph, picks the smallest, least disruptive set of changes that cuts them, proves the fix on a scratch copy of the graph, and files a change for human approval, remembering what humans approve or reject.

**Demo story (this order; design everything so each step is one API call):**

1. **Depth contrast.** Scan at depth 2 -> "no modelled path within 2 hops" (explicitly NOT "safe"). Scan at depth 4+ -> N attack paths, including a hidden 4-hop one through a forgotten service account (`svc-legacy-etl`). The path is returned hop by hop.
2. **Ask a question.** "Can `intern-laptop` reach `prod-customer-db`? Why?" -> answer with the path, produced by a shortest-path tool.
3. **Plan.** The agent ranks choke edges and selects a fix: "cuts X of N paths at disruption D".
4. **Simulate.** Copy the graph to a scratch graph, apply the fix there, re-run the path search, return before/after (N -> 0, or N -> residual with a second fix). Delete the scratch graph.
5. **Propose.** Create a change record: owning team (found by traversal), a ticket body, a config diff. Status = proposed.
6. **Human rejects with a reason** ("breaks nightly ETL"). **Re-plan**: the agent reads past decisions from the graph, excludes the rejected edge, and chooses an alternative. Memory persists across sessions because it lives in the graph.
7. **Honesty checks.** Unknown asset name -> `unknown_asset`, no query runs. Asset with no path -> "no modelled path", not "safe".

---

## 2. Architecture (must be Vercel-compatible from day one)

Deployment target is **Vercel** (done at the end, Phase 8). Serverless imposes rules that must shape the code NOW:

- **Python 3.12, FastAPI.** Entry point `api/index.py` exporting the ASGI `app`. `requirements.txt` (not poetry) for Vercel compatibility. Verify current Vercel Python runtime support, bundle-size and function-duration limits in the Vercel docs and keep within them.
- **Stateless.** No local disk state, no background threads, no in-process caches that matter, no long-lived subprocesses. **Do NOT use stdio MCP subprocesses.**
- **FalkorDB lives outside Vercel:** FalkorDB Cloud (free instance) for deployment; Docker (`falkordb/falkordb:latest`, ports 6379 and 3000 for the Browser UI) for local development. Connection by env vars; the same code must run on both.
- **MCP server** built with the official Python MCP SDK (FastMCP), exposed as **stateless streamable HTTP mounted at `/mcp`** inside the FastAPI app. The same tool functions back the REST endpoints, the MCP server and the agent.
- **Agent loop discovers tools through MCP**, not through a private list. Preferred: use the SDK's in-memory client<->server transport so no network hop is needed. Fallback (only if it costs >1 hour): loopback HTTP to `/mcp`. Last resort: shared tool registry, and say so honestly in the README.
- **Every API response carries its own `trace`** (tool, args, duration ms, row count) so no server-side trace storage is needed.
- **CORS enabled** (configurable origins) because the frontend will be built separately.
- Every endpoint idempotent where possible; `/api/reset` reseeds the demo environment.

Layout:

```
api/index.py            # Vercel entrypoint
app/main.py             # FastAPI app, routes, CORS
app/config.py           # env vars
app/db.py               # FalkorDB connection + graph selection
app/seed.py             # deterministic synthetic environment generator
app/queries.py          # ALL Cypher lives here, named + documented
app/tools.py            # tool functions, argument validation, registry
app/planner.py          # greedy remediation planner (pure Python over graph results)
app/mcp_server.py       # FastMCP wrapper over tools.py
app/agent.py            # LLM loop, no-LLM router, answer checker
app/models.py           # pydantic models = the API contract
tests/                  # pytest, run against a real FalkorDB
docs/                   # WALKTHROUGH.md, DEMO_SCRIPT.md, QUERIES.md, ARCHITECTURE.md
docker-compose.yml  vercel.json  requirements.txt  .env.example  README.md
```

---

## 3. Graph data model

Graph name: `env:{tenant}` (default tenant `acme`). Scratch graphs: `sim:{uuid}`. Memory lives in the same tenant graph.

**Design decision (explain it in the README):** all attack-relevant edges use ONE relationship type, `PIVOT`, with a `kind` property. This keeps variable-length patterns and the algorithms simple. Verify that the multi-label and property-filter patterns below work in FalkorDB before relying on them; adapt and note any change.

```
(:Asset {id, name, kind, env, entry, crown, owner_team})
    kind: user | service_account | role | group | host | secret | datastore | vault
    entry: bool   -> attacker can start here (internet-facing host, phishable user, leaked CI token)
    crown: bool   -> crown-jewel target (customer DB, payment signing key)
(:Asset)-[:PIVOT {id, kind, cost, disruption, fix_kind, fix_text}]->(:Asset)
    kind: assume_role | network | holds_secret | secret_grants | permission | membership | runs_as
    cost: int 1-5          difficulty for an attacker (used as shortest-path weight)
    disruption: int 1-10   how much fixing (removing) this edge disrupts the business
    fix_kind: remove_trust | revoke_permission | segment_network | rotate_secret | remove_membership
    fix_text: human-readable change, e.g. "Remove sts:AssumeRole trust for svc-legacy-etl on role ci-deployer"
(:Team {id, name, lead})-[:OWNS]->(:Asset)
(:Decision {id, edge_id, status, reason, at, run})-[:ABOUT]->(:Asset)     // memory; status: proposed|approved|rejected
```

Indexes: `Asset(id)`, `Asset(name)`.

---

## 4. Seed data (`app/seed.py`)

Deterministic (`random.Random(7)`), idempotent (drop and rebuild the tenant graph), 120-200 assets, 300-500 edges, mostly benign noise. Plant:

- **3 entry points:** an internet-facing web host, a phishable `intern-laptop` user, a leaked CI token.
- **2 crown jewels:** `prod-customer-db`, `payments-signing-key`.
- **The hidden path:** a stale service account `svc-legacy-etl` that can assume a deploy role, giving a path of exactly **4 hops** from an entry point to a crown jewel. The **shortest** entry->crown path in the whole graph must be exactly 4 hops, so depth 2 and 3 find nothing and depth 4 finds paths (the demo contrast).
- **One true choke edge** that sits on most paths with low disruption (the right answer).
- **One decoy edge** that is on the most paths but has high disruption (9): a naive "most paths" ranking picks it; the cost-aware ranking should not.
- **Redundancy** so that one fix may not cut everything and the planner needs 2 edges.
- **Noise must not create runaway path counts.** Target roughly 10-30 total attack paths at depth cap 8. Tune, then **print the real numbers** and use those in the docs. Do not hardcode numbers in the README that the code does not produce.
- Names kebab-case (`[a-z0-9]+(-[a-z0-9]+)+`) so the answer checker (section 7) can validate them.
- Teams own assets so owners can be found by traversal.
- Pre-seed one or two historical `Decision` nodes (e.g. an old rejected edge with a reason) so memory is visible from the first run.

---

## 5. Reference Cypher (put in `queries.py`; verify every item against docs.falkordb.com before relying on it)

All attack paths (depth is a parameter; cap it):
```
MATCH p = (e:Asset {entry:true})-[:PIVOT*1..$depth]->(t:Asset {crown:true})
RETURN [n IN nodes(p) | n.name] AS via,
       [r IN relationships(p) | r.id] AS edge_ids,
       length(p) AS hops
ORDER BY hops
LIMIT $limit
```

Choke-edge frequency (try in Cypher; if `count(DISTINCT p)` or path aggregation misbehaves, return `edge_ids` per path and count in Python — enumeration remains graph work):
```
MATCH p = (e:Asset {entry:true})-[:PIVOT*1..$depth]->(t:Asset {crown:true})
UNWIND relationships(p) AS r
RETURN r.id AS edge_id, r.kind AS kind, r.disruption AS disruption,
       r.fix_text AS fix_text, count(DISTINCT p) AS paths_through
ORDER BY paths_through DESC
```

Shortest weighted path (from the sponsor's published example; verify argument names):
```
MATCH (a:Asset {name:$from}), (b:Asset {name:$to})
CALL algo.SPpaths({sourceNode:a, targetNode:b, relTypes:['PIVOT'],
                   relDirection:'outgoing', weightProp:'cost', pathCount:1})
YIELD path, pathWeight
RETURN [n IN nodes(path) | n.name] AS hops,
       [r IN relationships(path) | r.id] AS edge_ids, pathWeight
```

Load-bearing assets: `CALL algo.pageRank('Asset','PIVOT') YIELD node, score` and, if its signature checks out in the docs, `algo.betweenness`. Use whichever works and say which in the README.

Name resolution (runs before every tool that takes a name): `MATCH (a:Asset {name:$name}) RETURN a.id AS id, a.name AS name`.

Simulation: copy the tenant graph to `sim:{uuid}` (verify the `GRAPH.COPY` / client `copy()` API; fallback: export and rebuild), delete the chosen edges there (`MATCH ()-[r:PIVOT {id:$id}]->() DELETE r`), re-run the path query on the scratch graph, **always delete the scratch graph in a `finally`**.

Memory write / read: `CREATE (d:Decision {...})` linked with `[:ABOUT]` to the from/to assets; read rejected edge ids and reasons for the planner; look up the owner team with `MATCH (t:Team)-[:OWNS]->(a:Asset {id:$id}) RETURN t.name, t.lead`.

**Rules for all queries:** parameterised only (never string-concatenate model or user input); `ro_query` for reads; depth capped (<= 8) and result limits enforced; read-only except the explicit write tools.

---

## 6. Tool catalogue (human-written; exposed over MCP; also REST)

The model chooses a tool and fills typed arguments. **It never writes Cypher.** Every `asset_name` argument is resolved against the graph first; unresolved -> outcome `unknown_asset`, nothing else runs.

| Tool | Args | What it does |
|---|---|---|
| `find_attack_paths` | `depth<=8`, `limit<=50` | Enumerate entry->crown paths. |
| `explain_reachability` | `from_name`, `to_name` | Shortest weighted path (algo.SPpaths); "not in graph" if none. |
| `rank_choke_edges` | `depth<=8`, `limit<=15` | Edges ranked by paths cut per disruption. Shows the decoy trap. |
| `rank_load_bearing_assets` | `limit<=20` | PageRank / betweenness. |
| `plan_remediation` | `budget<=3` | Greedy set-cover over graph-enumerated paths, maximising paths cut per disruption; **excludes edges rejected in memory**. Label honestly as greedy, not provably optimal. |
| `simulate_fix` | `edge_ids[]` (<=5) | Scratch graph, apply, re-run paths, return before/after, delete scratch. |
| `propose_change` | `edge_ids[]`, `plan_note?` | Write `Decision(status=proposed)`; find owner team; return ticket markdown + config diff text from `fix_text`. |
| `record_decision` | `decision_id`, `approve|reject`, `reason?` | Write the outcome to the graph. |
| `recall_decisions` | `asset_name?` | Read past decisions (outcome `answered_from_memory`, with dates). |

**Response envelope for every tool and endpoint:**
```
{ "outcome": "answered_with_path | answered_from_memory | not_in_graph | unknown_asset | verified_fix | proposed | recorded",
  "data": {...}, "paths": [{"nodes":[{id,name,kind}], "edges":[{id,kind}]}], "trace": [{tool,args,ms,rows}], "notes": "" }
```
**"No path found" must always be `not_in_graph` with a note that the dependency may not be modelled. It must never be phrased as safe.**

**Token discipline (free LLM tiers allow only ~6,000 tokens/minute):** tool outputs fed back to the model must be compact (names and ids, max ~1,500 tokens), schemas short, system prompt under ~500 tokens. Full detail goes in the HTTP response, not into the model's context.

---

## 7. Agent behaviour (`app/agent.py`) — free LLMs only

**Provider-agnostic via the OpenAI-compatible API** (`openai` Python SDK with a configurable `base_url`):

- Primary: **Groq free tier** (no card needed), model `llama-3.3-70b-versatile` (reliable tool calls). Base URL `https://api.groq.com/openai/v1`.
- Fallback: **Google Gemini free tier** (Flash / Flash-Lite via its OpenAI-compatible endpoint). Free-tier availability depends on country, and inputs may be used by Google; fine because our data is synthetic.
- Configure with `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, and `LLM_FALLBACK_*`. Free-tier models, limits and names change; confirm current ones in provider docs. On 429/5xx try the fallback, then go to router mode. Keep a small retry/backoff.
- Loop: max 6 tool calls per turn; model picks MCP tools; results appended compactly; model writes ONE short summary sentence plus is told to quote numbers verbatim from tool results.

**No-LLM router mode (required):** a deterministic intent router (keyword/regex -> tool + args) that answers common questions ("scan", "can X reach Y", "plan", "simulate", "why") with templated sentences built from tool rows. Used when no key is set, when rate-limited, and for every REST button. **The product must be fully demoable with `CHAT_ENABLED=false`.**

**Answer checker (run on every LLM sentence):** every kebab-case name in the sentence must appear in the tool results; every integer must appear in the result JSON (small integers 0-10 allowed); if the tool returned no paths, the sentence must not claim impact; the word "safe" must not appear unless quoting a limitation. On failure, discard it and return the templated sentence instead. Return `checked: true/false` and the reason.

**Never:** invent asset names, write Cypher, claim "safe", claim a fix is verified without a `simulate_fix` result, or approve/reject on the human's behalf.

---

## 8. REST contract (this is what the human's frontend will consume)

Define in `app/models.py` with pydantic; auto-document at `/docs`.

```
GET  /healthz
GET  /api/graph            -> {nodes:[{id,name,kind,entry,crown,owner_team}], edges:[{id,source,target,kind,cost,disruption}]}
POST /api/scan             {depth}                  -> envelope (paths)
POST /api/reach            {from_name,to_name}      -> envelope (path)
POST /api/choke            {depth,limit}            -> envelope (ranked edges)
POST /api/plan             {budget}                 -> envelope (plan)
POST /api/simulate         {edge_ids}               -> envelope (before/after, remaining paths)
POST /api/propose          {edge_ids,plan_note?}    -> envelope (decision_id, ticket, diff, owner)
POST /api/decision         {decision_id,action,reason?} -> envelope
GET  /api/decisions        ?asset_name=             -> envelope (memory)
POST /api/chat             {message, history?}      -> SSE stream: tool_call, tool_result, final {text, checked}
POST /api/reset            -> reseed demo env
ANY  /mcp                  -> MCP server (streamable HTTP, stateless)
```
Non-chat endpoints call the tool functions directly (no LLM). Add best-effort rate limiting on `/api/chat` and a `CHAT_ENABLED` flag.

---

## 9. Frontend (LATER — do not build in Phases 0-6)

The human will provide their own design. In Phase 7 you will build it against section 8. Until then, do not create UI beyond a plain `/docs` page. Make sure `/api/graph` and the `paths[]` shape are sufficient to draw the graph, highlight attack paths, mark removed edges, and show a before/after toggle and a trace panel.

---

## 10. Tests (`pytest`, against a real FalkorDB; no mocks for the graph)

1. Seed produces the expected asset/edge counts; shortest entry->crown path is exactly 4 hops.
2. `find_attack_paths(depth=2)` and `depth=3` return `not_in_graph`; `depth=4` returns the planted hidden path including `svc-legacy-etl`.
3. `rank_choke_edges`: the decoy edge has the most `paths_through`, but is NOT chosen by `plan_remediation`.
4. `plan_remediation` then `simulate_fix` reduces the path count to 0 (or to a stated residual with `budget=1`), and **the scratch graph no longer exists afterwards**.
5. Unknown asset name -> `unknown_asset`, and a trace proving no traversal query ran.
6. Injection safety: asset names containing quotes/Cypher fragments are treated as data.
7. Reject-then-replan: after `record_decision(reject)` on the top edge, `plan_remediation` excludes it and returns a different plan.
8. Answer checker rejects a sentence naming a non-existent service and one claiming "safe".
9. The no-LLM router handles scan / reach / plan / simulate with `CHAT_ENABLED=false`.
10. MCP: list tools returns the catalogue; calling `find_attack_paths` through MCP matches the REST result.

---

## 11. Environment variables (`.env.example`)

`FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD` (and SSL if FalkorDB Cloud needs it; check their docs), `TENANT_DEFAULT=acme`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_BASE_URL`, `LLM_FALLBACK_API_KEY`, `LLM_FALLBACK_MODEL`, `CHAT_ENABLED=true`, `ALLOWED_ORIGINS=*`. Never commit secrets.

---

## 12. Documentation deliverables (write as you go, not at the end)

- **README.md:** pitch; **Track 01** stated explicitly; architecture diagram (mermaid); **graph data model**; **"Why FalkorDB can't be removed"** table (each feature -> the graph capability it uses); the exact Cypher/algorithms list; local setup in under 5 minutes (docker compose); deployment notes; free-LLM setup; limitations (greedy not optimal; synthetic data; "no path" means not modelled); and an **AI-assistance disclosure** section: "Built with Claude Code as a coding assistant under the developer's direction; the developer reviewed and can explain the graph model, queries and architecture." The human will edit the wording.
- **docs/QUERIES.md:** every named query in `queries.py` with a plain-English explanation and which tool uses it.
- **docs/WALKTHROUGH.md:** the human's study guide. Each query, each tool, each design decision and why (single `PIVOT` type, fixed tool catalogue, scratch-graph simulation, greedy planner, answer checker, serverless constraints), plus **15 likely judge questions with short answers**.
- **docs/DEMO_SCRIPT.md:** a timed 3-minute video script following the section 1 story, with exact API calls or UI actions and the real numbers from the seeded data.
- **docs/ARCHITECTURE.md:** one page.

---

## 13. Build order, checkpoints, cut line

Work in this order. After each phase: run tests, commit with a clear message, and tell the human in 2-3 lines what works.

- **Phase 0 — Setup (30 min):** repo, `docker-compose.yml` (FalkorDB + Browser), venv, deps, `.env.example`, connection test, and a short list of any FalkorDB features from section 5 you could not verify.
- **Phase 1 — Seed + model (1.5 h):** schema, indexes, deterministic seed, print real stats; confirm the shortest-path-is-4 property in FalkorDB Browser.
- **Phase 2 — Queries + tools (2.5 h):** `queries.py`, `tools.py` with validation and the envelope, `planner.py`; tests 1-7.
- **Phase 3 — REST API (1 h):** all non-chat endpoints; trace on every response; `/docs` works.
- **Phase 4 — MCP (1 h):** FastMCP server at `/mcp`; test 10.
- **Phase 5 — Agent (1.5 h):** router mode first, then the free-LLM loop through MCP, then the answer checker; tests 8-9; SSE chat endpoint.
- **Phase 6 — Docs pass (1 h):** README, QUERIES, WALKTHROUGH, DEMO_SCRIPT with real numbers. **Backend complete here.**
- **Phase 7 — Frontend (human supplies design):** build it against the REST contract only.
- **Phase 8 — Deploy to Vercel:** FalkorDB Cloud instance seeded via `/api/reset` or a script; env vars set; `vercel.json`; verify `/healthz`, `/api/scan`, `/mcp`, SSE chat on the deployed URL; record the live URL in the README.
- **Phase 9 — Stretch:** blog post draft (best-blog side prize), `algo.maxFlow` cross-check of the greedy plan, per-tenant second graph to show isolation.

**Cut line if time runs short (cut in this order):** blog post -> maxFlow cross-check -> LLM chat polish (keep router mode) -> MCP-through-agent (keep the MCP endpoint) -> second fix / residual story. **Never cut:** seeded hidden path, depth contrast, plan, scratch-graph simulation with before/after, memory (reject-then-replan), unknown-asset honesty, README + data model + queries list, demo script.

---

## 14. Working rules for you, Claude Code

- Start with Phase 0 now. Ask the human only for things only they can provide (FalkorDB Cloud credentials, free LLM key, the frontend design later). Do not ask about decisions already made in this file.
- **Verify FalkorDB behaviour against docs.falkordb.com** instead of assuming. List of things to confirm early: variable-length bound as a parameter, multi-label/property-filtered start nodes, `count(DISTINCT p)`, `algo.SPpaths` / `algo.pageRank` / `algo.betweenness` signatures, graph copy and delete, Cloud connection options. Report any deviation from this brief.
- Never claim something works that you have not run. If a test fails, fix it or say so; do not weaken the test.
- Keep the code boring and readable. The human has to explain it to judges.
- Commit often. No secrets in git. Keep the repo public-ready (clear README, license).
- If the plan and reality disagree, tell the human what you changed and why, in two lines.

**Start now: Phase 0.**
