"""Run the whole demo story over HTTP and print the real numbers.
Usage: python -m scripts.demo_run [base_url]      (default http://127.0.0.1:8000)
It starts with /api/reset and ends with /api/reset, so the demo graph is left clean."""
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
http = httpx.Client(base_url=BASE, timeout=120, headers={"X-Reset-Token": os.getenv("RESET_TOKEN", "")})


def call(method, path, body=None, params=None):
    r = http.request(method, path, json=body, params=params)
    r.raise_for_status()
    return r.json()


def line(title, env, extra=""):
    queries = ", ".join(f"{t['query']}({t['ms']:.0f}ms/{t['rows']}r)" for t in env["trace"])
    print(f"\n[{title}] outcome={env['outcome']} {extra}\n   notes: {env['notes'] or '-'}\n   trace: {queries}")


def route(p):
    return " -> ".join(n["name"] for n in p["nodes"])


def show_plan(title, env):
    d = env["data"]
    line(title, env, f"cut {d['paths_cut']}/{d['paths_total']}, remaining {d['paths_remaining']}, "
                     f"total disruption {d['total_disruption']}")
    for s in d["plan"]:
        print(f"   {s['edge_id']}  disruption={s['disruption']}  cuts={s['paths_cut']}  {s['fix_text']}")
    if d["excluded_by_memory"]:
        print("   excluded by memory:", [(e["edge_id"], e["reason"]) for e in d["excluded_by_memory"]])


print("reset:", call("POST", "/api/reset")["data"])

for depth in (2, 4):
    env = call("POST", "/api/scan", {"depth": depth})
    line(f"scan depth {depth}", env, f"paths={env['data'].get('count', 0)}")
    for p in env["paths"]:
        print("   ", len(p["edges"]), "hops:", route(p))

for src in ("intern-laptop", "ci-leaked-token"):
    env = call("POST", "/api/reach", {"from_name": src, "to_name": "prod-customer-db"})
    line(f"reach {src} -> prod-customer-db", env,
         f"hops={env['data']['hops']} attacker_cost={env['data']['attacker_cost']}")
    print("   ", route(env["paths"][0]))

choke = call("POST", "/api/choke", {})
d = choke["data"]
line("choke ranking", choke, f"total_paths={d['total_paths']}")
print("   naive most-paths:", d["naive_most_paths"]["edge_id"], "paths", d["naive_most_paths"]["paths_through"],
      "disruption", d["naive_most_paths"]["disruption"])
for e in d["ranked"][:3]:
    print(f"   ranked {e['edge_id']} paths={e['paths_through']} disruption={e['disruption']} score={e['score']}")

plan = call("POST", "/api/plan", {"budget": 3})
show_plan("plan budget=3", plan)
edge_ids = [s["edge_id"] for s in plan["data"]["plan"]]
show_plan("plan budget=1", call("POST", "/api/plan", {"budget": 1}))

sim = call("POST", "/api/simulate", {"edge_ids": edge_ids})
s = sim["data"]
line("simulate full plan", sim, f"before={s['paths_before']} after={s['paths_after']} "
                                f"scratch_deleted={s['scratch_deleted']}")
sim1 = call("POST", "/api/simulate", {"edge_ids": edge_ids[:1]})
line("simulate first edge only", sim1, f"before={sim1['data']['paths_before']} after={sim1['data']['paths_after']} "
                                       f"scratch_deleted={sim1['data']['scratch_deleted']}")

prop = call("POST", "/api/propose", {"edge_ids": edge_ids[:1], "plan_note": "Top edge of the greedy plan"})
p = prop["data"]
line("propose", prop, f"run={p['run']} owner_teams={p['owner_teams']} status={p['status']}")
print("   ticket:\n      " + p["ticket_markdown"].replace("\n", "\n      "))
print("   diff:\n      " + p["config_diff"].replace("\n", "\n      "))

rej = call("POST", "/api/decision", {"decision_id": p["run"], "action": "reject",
                                     "reason": "CI needs prod-admin during releases"})
line("reject", rej, f"status={rej['data']['status']} decided={rej['data']['decided']}")

show_plan("re-plan budget=3 after reject", call("POST", "/api/plan", {"budget": 3}))

mem = call("GET", "/api/decisions")
line("memory", mem, f"{len(mem['data']['decisions'])} decisions")
for dd in mem["data"]["decisions"]:
    print(f"   {dd['at']}  {dd['status']:<9} {dd['edge_id']}  {dd['reason']}")

unk = call("POST", "/api/reach", {"from_name": "ghost-host-99", "to_name": "prod-customer-db"})
line("unknown asset", unk, f"unknown={unk['data'].get('unknown')} queries_run={[t['query'] for t in unk['trace']]}")
nop = call("POST", "/api/reach", {"from_name": "srv-alpha-01", "to_name": "prod-customer-db"})
line("no-path asset", nop)

print("\nreset (leave demo graph clean):", call("POST", "/api/reset")["data"])
