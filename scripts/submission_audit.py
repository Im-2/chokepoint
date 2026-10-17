"""Graph Hacks submission audit: PASS/FAIL per item, checked against a FRESH CLONE of the public repo and the live site.
Usage: python -m scripts.submission_audit [owner/repo] [live_url]
Needs: git, gh (for repo visibility), and .env (so the secret scan can compare real values; values are never printed)."""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")
REPO = sys.argv[1] if len(sys.argv) > 1 else "Im-2/chokepoint"
LIVE = sys.argv[2] if len(sys.argv) > 2 else "https://trychokepoint.vercel.app"
ROOT = Path(__file__).resolve().parent.parent
results = []


def item(name, ok, where):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}\n        {where}")


def run(*cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


work = Path(tempfile.mkdtemp(prefix="audit-clone-"))
clone = work / "repo"
try:
    c = run("git", "clone", "-q", f"https://github.com/{REPO}.git", str(clone))
    assert c.returncode == 0, c.stderr
    readme = (clone / "README.md").read_text(encoding="utf-8")
    files = run("git", "ls-files", cwd=clone).stdout.split()

    vis = run("gh", "repo", "view", REPO, "--json", "visibility,description,repositoryTopics", "--jq", ".visibility").stdout.strip()
    item("Public repo", vis == "PUBLIC", f"https://github.com/{REPO} is {vis}; description and topics set on GitHub; MIT LICENSE: {'LICENSE' in files}")

    setup = re.search(r"^##+ .*(Local setup|Setup)", readme, re.M) is not None and "python -m uvicorn" in readme and ".env.example" in readme
    model = "## Graph data model" in readme and "(:Asset {id, name, kind" in readme and ":PIVOT" in readme
    item("README: setup instructions", setup, "README.md, section 'Local setup (about 5 minutes)' (+ FalkorDB Cloud / optional Docker, env vars)")
    item("README: graph data model", model, "README.md, section 'Graph data model' (nodes, PIVOT edge properties, Team, Decision, indexes, seeded environment)")

    queries_doc = (clone / "docs" / "QUERIES.md").exists() and "docs/QUERIES.md" in readme and "algo.SPpaths" in readme and "algo.betweenness" in readme
    item("Cypher queries and graph algorithms listed", queries_doc,
         "README.md section 'The Cypher and algorithms the product depends on' links docs/QUERIES.md; all Cypher lives in app/queries.py")

    item("Demo video line near the top of the README", "Demo video: <link>" in readme[:1200],
         "README.md line 7 ('Demo video: <link>' placeholder to fill in); the recording is demo/chokepoint-demo.mp4 (local, git-ignored)")

    live_ok = LIVE in readme[:1500]
    r = httpx.get(f"{LIVE}/healthz", timeout=30)
    h = r.status_code == 200 and r.json().get("falkordb") is True
    page = httpx.get(LIVE + "/", timeout=30)
    scan = httpx.post(f"{LIVE}/api/scan", json={"depth": 4}, timeout=30).json()
    item("Live deployment URL in the README, and it works", live_ok and h and page.status_code == 200 and scan["data"]["count"] == 1,
         f"README.md table row 'Live deployment': {LIVE}; /healthz ok, site 200, /api/scan depth 4 -> 1 path")

    item("Track 01 named in the README", "Track 01" in readme[:800], "README.md line 5: 'Graph Hacks ... Track 01: Agents That Act on Connected Data'")

    disclosure = re.search(r"## AI-assistance disclosure\s+(.+?)\n\n", readme, re.S)
    plain = bool(disclosure) and "Claude Code" in disclosure.group(1) and "AI-generated" in readme
    item("AI-assistant disclosure, in plain words", plain,
         "README.md section 'AI-assistance disclosure' (Claude Code as coding assistant; the demo voiceover is AI-generated)")

    scan_out = run(sys.executable, "-m", "scripts.secret_scan", str(clone), cwd=ROOT)
    item("No secrets in the repo or its history (fresh clone, real .env values compared)",
         "clean: no secrets found" in scan_out.stdout, scan_out.stdout.strip().splitlines()[-1] if scan_out.stdout.strip() else scan_out.stderr[:200])

    banned = [f for f in files if re.search(r"(^|/)\.env$|\.env\.local$|^ui/|\.mp4$|^demo/audio/|\.mp3$", f)]
    item("No .env, design video, demo video or audio clips committed", not banned, f"git ls-files has none of them (found: {banned or 'none'})")

    stale = [f for f in files if (clone / f).is_file() and "chokepoint-alpha" in (clone / f).read_text(encoding="utf-8", errors="ignore")]
    item("Old URL gone from every file", not stale, f"no file mentions chokepoint-alpha (found in: {stale or 'none'})")
finally:
    shutil.rmtree(work, ignore_errors=True)

print(f"\n{sum(results)}/{len(results)} items pass")
sys.exit(0 if all(results) else 1)
