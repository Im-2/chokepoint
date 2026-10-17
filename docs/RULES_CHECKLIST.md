# Graph Hacks rules checklist (Track 01)

Status: ✅ done · 🟡 partial / planned · ⬜ not started. Re-checked before every phase commit; full audit at the end.

| # | Rule | Where this repo satisfies it | Status |
|---|------|------------------------------|--------|
| 1 | FalkorDB central and essential | Path enumeration, choke ranking, shortest path, centrality, scratch-graph simulation and decision memory all run in FalkorDB (`app/queries.py`, `app/tools.py`). README table "Why FalkorDB can't be removed". | ✅ README table "Why FalkorDB can't be removed"; tools, REST, MCP and agent all call the graph |
| 2 | Synthetic data only | `app/seed.py` generates everything from `random.Random(7)`; no real credentials or infrastructure. `.env` is git-ignored. | ✅ seed built (Phase 1) |
| 3 | README with setup + graph data model | `README.md` (data model, setup, Cloud and Docker options) | ✅ README has setup and the graph data model |
| 4 | Cypher queries / algorithms list | `app/queries.py` (all Cypher) + `docs/QUERIES.md` | ✅ all current queries documented in docs/QUERIES.md |
| 5 | Demo video | Script in `docs/DEMO_SCRIPT.md`; video link in README | 🟡 script ready (docs/DEMO_SCRIPT.md); the video itself is for the developer to record, link goes in the README |
| 6 | Deployment or local setup instructions | README: FalkorDB Cloud + `docker-compose.yml` (optional local); live on Vercel | ✅ live at https://chokepoint-alpha.vercel.app, verified; local setup documented; compose file untested and marked so |
| 7 | AI-assistance disclosure | README section; `docs/WALKTHROUGH.md` shows the human can explain the design | ✅ README section "AI-assistance disclosure"; study guide docs/WALKTHROUGH.md |
| 8 | Track 01 named | README top section | ✅ README section "AI-assistance disclosure"; study guide docs/WALKTHROUGH.md |
| 9 | Public repo, no secrets | `.gitignore` excludes `.env`; only `.env.example` committed; secret scan before each commit | ✅ public repo https://github.com/Im-2/chokepoint; history scrubbed and scanned |
| 10 | Work created during the event | Repo started during the event; single history in git | ✅ public repo https://github.com/Im-2/chokepoint; history scrubbed and scanned |

## Safety rules for the dev database
- Tests only use graphs named `test:<random>` and delete them in `finally`.
- Tests never touch `env:acme`; the demo graph is only written by `/api/reset` / the seed script.
- Simulation scratch graphs `sim:<uuid>` are always deleted in a `finally` (free Cloud memory is limited).

## Pre-commit check
1. `git status` shows no `.env` or key material; grep staged diff for key patterns.
2. Tests pass.
3. No row above has regressed.

## Audit after Phase 6 (2026-10-17)
Met: FalkorDB is essential (README table); synthetic data only; README with setup and graph data
model; Cypher/algorithms list (README + docs/QUERIES.md); AI disclosure; Track 01 named; public repo
with MIT license; history scrubbed and scanned clean (a fresh clone of the remote was scanned against
the real `.env` values); local setup instructions; `.env` never committed.

Still missing or open (be honest in the submission):
- **Demo video:** not recorded (the developer records it; script is ready). Add the link to the README.
- **Live deployment:** done in Phase 8 (https://chokepoint-alpha.vercel.app). Keep it working until judging.
- **Frontend:** not built (Phase 7, waits for the developer's design). `/docs` is the only UI.
- **Untested:** `docker-compose.yml` (no Docker on the dev machine) and the Gemini fallback settings.
- **Not done on purpose:** authentication on write tools other than `/api/reset`.
