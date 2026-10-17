# Graph Hacks rules checklist (Track 01)

Status: ✅ done · 🟡 partial / planned · ⬜ not started. Re-checked before every phase commit; full audit at the end.

| # | Rule | Where this repo satisfies it | Status |
|---|------|------------------------------|--------|
| 1 | FalkorDB central and essential | Path enumeration, choke ranking, shortest path, centrality, scratch-graph simulation and decision memory all run in FalkorDB (`app/queries.py`, `app/tools.py`). README table "Why FalkorDB can't be removed". | ⬜ (Phase 2, 6) |
| 2 | Synthetic data only | `app/seed.py` generates everything from `random.Random(7)`; no real credentials or infrastructure. `.env` is git-ignored. | ⬜ (Phase 1) |
| 3 | README with setup + graph data model | `README.md` (data model, setup, Cloud and Docker options) | ⬜ (Phase 6) |
| 4 | Cypher queries / algorithms list | `app/queries.py` (all Cypher) + `docs/QUERIES.md` | ⬜ (Phase 2, 6) |
| 5 | Demo video | Script in `docs/DEMO_SCRIPT.md`; video link in README | ⬜ (Phase 6, human records) |
| 6 | Deployment or local setup instructions | README: FalkorDB Cloud + `docker-compose.yml` (optional local); Vercel in Phase 8 | 🟡 compose file exists |
| 7 | AI-assistance disclosure | README section; `docs/WALKTHROUGH.md` shows the human can explain the design | ⬜ (Phase 6) |
| 8 | Track 01 named | README top section | ⬜ (Phase 6) |
| 9 | Public repo, no secrets | `.gitignore` excludes `.env`; only `.env.example` committed; secret scan before each commit | ✅ so far |
| 10 | Work created during the event | Repo started during the event; single history in git | ✅ so far |

## Safety rules for the dev database
- Tests only use graphs named `test:<random>` and delete them in `finally`.
- Tests never touch `env:acme`; the demo graph is only written by `/api/reset` / the seed script.
- Simulation scratch graphs `sim:<uuid>` are always deleted in a `finally` (free Cloud memory is limited).

## Pre-commit check
1. `git status` shows no `.env` or key material; grep staged diff for key patterns.
2. Tests pass.
3. No row above has regressed.
