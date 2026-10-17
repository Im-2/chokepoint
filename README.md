# Chokepoint

Agent that finds attack paths to crown-jewel data in a cloud-environment graph, picks the smallest
least-disruptive fix, proves it on a scratch copy, and files a change for human approval.
**Graph Hacks: Context for AI Agents, Track 01 — Agents That Act on Connected Data.**
Full README is written in Phase 6; this is the Phase 1 stub.

## Setup
1. `python -m venv .venv` and `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and fill in your FalkorDB host, port, username and password.
   FalkorDB Cloud (free instance) is what we develop and deploy against.
3. Seed the demo graph: `python -m app.seed`  (writes `env:acme`).
4. Tests: `python -m pytest` (they only touch graphs named `test:*`).

### Optional: local FalkorDB with Docker
`docker-compose.yml` starts FalkorDB with the Browser UI on port 3000.
**Status: untested.** It was not run during development (no Docker on the dev machine); the
project was developed and verified against FalkorDB Cloud only.
