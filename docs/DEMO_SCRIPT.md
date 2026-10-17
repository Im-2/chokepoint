# Demo script (3 minutes)

Numbers below come from the seeded graph `env:acme` and were produced by `python -m scripts.demo_run`
against FalkorDB Cloud. They are deterministic (seed 7), so they will match on your run.
Each step is one API call. When the frontend exists, each step is one button; the calls are the same.

**Setup (before recording):** server running (`python -m uvicorn app.main:app --port 8000`) and the
graph freshly reset:

```bash
BASE=http://127.0.0.1:8000
curl -s -X POST $BASE/api/reset -H "X-Reset-Token: $RESET_TOKEN"     # 130 assets, 322 PIVOT edges
```

Optional for a clean take: `python -m scripts.demo_run` runs the whole story below in the terminal.

| Time | Say | Call | What you see |
|---|---|---|---|
| 0:00 | "Chokepoint is an agent over a FalkorDB graph of a company's cloud. It finds how an attacker gets from the internet to the crown jewels, and the cheapest way to cut those paths." Show the graph in the Browser/`/api/graph`: 130 assets, 3 entry points, 2 crown jewels. | `GET /api/graph` | nodes + edges |
| 0:20 | **Depth contrast.** "Scan two hops: nothing. But that is not 'safe', it is 'not modelled within 2 hops'." | `POST /api/scan {"depth":2}` | `not_in_graph`, note says not a statement the asset is safe |
| 0:35 | "Four hops: a hidden path through `svc-legacy-etl`, a forgotten service account." | `POST /api/scan {"depth":4}` | 1 path, 4 hops: `ci-leaked-token -> svc-legacy-etl -> role-ci-deployer -> role-prod-admin -> prod-customer-db` |
| 0:50 | "Depth 8: the full picture, 19 attack paths." | `POST /api/scan {"depth":8}` | 19 paths (1 of 4 hops, 13 of 5, 5 of 6) |
| 1:00 | **Ask a question.** "Can the intern's laptop reach the customer database? Why?" | `POST /api/reach {"from_name":"intern-laptop","to_name":"prod-customer-db"}` | yes, 5 hops via `grp-interns`, `grp-platform-eng`, `role-ci-deployer`, `role-prod-admin`; attacker cost 8; the path comes back with the answer |
| 1:15 | **Plan.** "Which edge do we cut? Ranking by most paths picks the wrong one." | `POST /api/choke {}` | most paths: `e026` 15 paths but disruption 9 (a decoy). Best ratio: `e023` 11 paths, disruption 2 (score 5.5) |
| 1:30 | "The planner picks by paths cut per disruption." | `POST /api/plan {"budget":3}` | `e023` (cuts 11) + `e022` jump-host trust (cuts 8) = 19 of 19, total disruption 5, uses 2 of 3 budget |
| 1:40 | "With a budget of one, it would cut 11 of 19 and say 8 remain." | `POST /api/plan {"budget":1}` | cut 11/19, 8 remain |
| 1:50 | **Simulate.** "Prove it: copy the graph, apply the fix on the copy, re-run the path search." | `POST /api/simulate {"edge_ids":["e023","e022"]}` | 19 paths before, **0 after**; scratch graph deleted. (Only `e023`: 19 -> 8) |
| 2:05 | **Propose.** "File the change for the owning team." | `POST /api/propose {"edge_ids":["e023"],"plan_note":"Top edge of the greedy plan"}` | owner `platform-eng` (found by traversal), ticket markdown, config diff, status `proposed` (note the `run` id) |
| 2:15 | **Human rejects with a reason.** | `POST /api/decision {"decision_id":"<run id>","action":"reject","reason":"CI needs prod-admin during releases"}` | `recorded` |
| 2:25 | **Re-plan.** "The agent reads the rejection from the graph and chooses another route." | `POST /api/plan {"budget":3}` | excludes `e023`; picks `e013` (`svc-legacy-etl` trust, disruption 1), `e022` (3), `e015` (`svc-backup-agent` trust, 2): cuts 15 of 19, total disruption 6, **4 remain** (reported honestly). The decoy is not used. |
| 2:40 | "Memory is in the graph, so it survives restarts." | `GET /api/decisions` | the new rejection dated today, plus the seeded history (`e029` rejected, `e040` approved) |
| 2:45 | **Honesty.** | `POST /api/reach {"from_name":"ghost-host-99","to_name":"prod-customer-db"}` | `unknown_asset`, only `resolve_asset` ran, nothing was searched |
| 2:52 | | `POST /api/reach {"from_name":"srv-alpha-01","to_name":"prod-customer-db"}` | `not_in_graph`: "no modelled path ... not a statement that the asset is safe" |
| 2:57 | "The tools are also an MCP server at `/mcp`, and the chat works with a free model or none." | `python -m scripts.chat_run "Simulate the plan and tell me whether the fix is verified"` | the model calls `plan_remediation` then `simulate_fix`; answer is checked against the tool results |

**Close (3:00):** "FalkorDB does the work: path enumeration, choke ranking, shortest path,
scratch-graph simulation and decision memory. Take it away and none of this exists."

## Optional chat segment (if time)
```bash
curl -N -X POST $BASE/api/chat -H "Content-Type: application/json" \
     -d '{"message":"Can intern-laptop reach prod-customer-db? Why?"}'
```
Streams `tool_call`, `tool_result` (with the path and trace) and `final {text, checked}`.

## After recording
Reset so the next take starts clean: `curl -s -X POST $BASE/api/reset -H "X-Reset-Token: $RESET_TOKEN"`.
Keep the narration to what the calls return; every number above is real.
