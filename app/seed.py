"""Deterministic synthetic environment generator (Phase 1).

Everything here is invented. Same seed (7) -> same graph, every time.

Shape of the graph (see docs/WALKTHROUGH.md for the story):

  CORE   ~19 hand-written assets. This is the only place attack paths exist.
  NOISE  ~110 generated assets. Edges only go noise->noise or core->noise, never
         noise->core, and crown jewels have no outgoing edges. So noise can add
         realism and load on the graph, but can never create a path to a crown jewel.

Core routes (D = role-ci-deployer, X = role-ops-admin, P = role-prod-admin):

  entries -> footholds -> D --(CHOKE edge, disruption 2)--> P --(DECOY edge, disruption 9)--> prod-customer-db
  entries -> jump-host-01 -> X -> P -> prod-customer-db        (bypass of D, so one fix is not enough)
  entries -> jump-host-01 -> X -> Q -> payments-signing-key
"""
import random
import re

from app import config
from app.db import get_client

SEED = 7
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)+$")

TEAMS = [
    ("platform-eng", "Priya Nair"),
    ("data-eng", "Tunde Bello"),
    ("payments", "Chidi Okoro"),
    ("security", "Sara Lindqvist"),
    ("it-ops", "Marcus Webb"),
    ("app-dev", "Lena Fischer"),
]

# (name, kind, entry, crown, team)
CORE_ASSETS = [
    ("web-frontend-01", "host", True, False, "app-dev"),
    ("intern-laptop", "user", True, False, "it-ops"),
    ("ci-leaked-token", "secret", True, False, "platform-eng"),
    ("app-server-02", "host", False, False, "app-dev"),
    ("batch-runner-01", "host", False, False, "data-eng"),
    ("svc-report-sync", "service_account", False, False, "data-eng"),
    ("svc-backup-agent", "service_account", False, False, "it-ops"),
    ("svc-legacy-etl", "service_account", False, False, "data-eng"),  # the forgotten one
    ("secret-etl-creds", "secret", False, False, "data-eng"),
    ("grp-interns", "group", False, False, "it-ops"),
    ("grp-platform-eng", "group", False, False, "platform-eng"),
    ("vpn-gateway-01", "host", False, False, "it-ops"),
    ("jump-host-01", "host", False, False, "security"),
    ("role-ci-deployer", "role", False, False, "platform-eng"),  # D
    ("role-ops-admin", "role", False, False, "it-ops"),  # X
    ("role-prod-admin", "role", False, False, "platform-eng"),  # P
    ("role-payments-admin", "role", False, False, "payments"),  # Q
    ("prod-customer-db", "datastore", False, True, "data-eng"),
    ("payments-signing-key", "vault", False, True, "payments"),
]

# (src, dst, kind, cost, disruption)
CORE_EDGES = [
    ("ci-leaked-token", "svc-legacy-etl", "secret_grants", 1, 3),
    ("ci-leaked-token", "batch-runner-01", "secret_grants", 2, 3),
    ("web-frontend-01", "app-server-02", "network", 2, 4),
    ("web-frontend-01", "batch-runner-01", "network", 3, 3),
    ("app-server-02", "svc-report-sync", "runs_as", 1, 5),
    ("app-server-02", "svc-backup-agent", "runs_as", 1, 4),
    ("app-server-02", "secret-etl-creds", "holds_secret", 2, 2),
    ("batch-runner-01", "svc-report-sync", "runs_as", 2, 5),
    ("batch-runner-01", "svc-backup-agent", "runs_as", 2, 4),
    ("batch-runner-01", "secret-etl-creds", "holds_secret", 1, 2),
    ("batch-runner-01", "jump-host-01", "network", 3, 3),
    ("secret-etl-creds", "svc-legacy-etl", "secret_grants", 1, 2),
    ("svc-legacy-etl", "role-ci-deployer", "assume_role", 2, 1),
    ("svc-report-sync", "role-ci-deployer", "assume_role", 3, 3),
    ("svc-backup-agent", "role-ci-deployer", "assume_role", 3, 2),
    ("grp-platform-eng", "role-ci-deployer", "permission", 2, 5),
    ("grp-platform-eng", "jump-host-01", "permission", 2, 3),
    ("intern-laptop", "grp-interns", "membership", 1, 2),
    ("grp-interns", "grp-platform-eng", "membership", 2, 3),
    ("intern-laptop", "vpn-gateway-01", "network", 2, 2),
    ("vpn-gateway-01", "jump-host-01", "network", 2, 3),
    ("jump-host-01", "role-ops-admin", "assume_role", 3, 3),
    ("role-ci-deployer", "role-prod-admin", "assume_role", 2, 2),  # THE CHOKE EDGE
    ("role-ops-admin", "role-prod-admin", "assume_role", 3, 2),
    ("role-ops-admin", "role-payments-admin", "assume_role", 3, 3),
    ("role-prod-admin", "prod-customer-db", "permission", 1, 9),  # THE DECOY EDGE
    ("role-payments-admin", "payments-signing-key", "permission", 1, 6),
]
CHOKE_EDGE = ("role-ci-deployer", "role-prod-admin")
DECOY_EDGE = ("role-prod-admin", "prod-customer-db")

# Noise assets: kind -> (prefix, how many, name words)
WORDS = ["alpha", "bravo", "cedar", "delta", "ember", "falcon", "garnet", "harbor", "indigo",
         "juniper", "kestrel", "lotus", "maple", "nimbus", "onyx", "pebble", "quartz", "raven",
         "sable", "tundra", "umber", "violet", "willow", "xenon", "yarrow", "zephyr"]
NOISE_KINDS = {
    "user": ("emp", 30),
    "group": ("grp", 8),
    "host": ("srv", 28),
    "service_account": ("svc", 12),
    "role": ("role", 12),
    "secret": ("secret", 12),
    "datastore": ("db", 8),
    "vault": ("vault", 1),
}
# Plausible (src kind, dst kind, edge kind) combinations for noise edges.
NOISE_RULES = [
    ("user", "group", "membership"),
    ("user", "host", "network"),
    ("group", "role", "permission"),
    ("role", "datastore", "permission"),
    ("role", "vault", "permission"),
    ("host", "secret", "holds_secret"),
    ("secret", "service_account", "secret_grants"),
    ("service_account", "role", "assume_role"),
    ("host", "service_account", "runs_as"),
    ("host", "host", "network"),
    ("host", "datastore", "network"),
]
NOISE_EDGE_TARGET = 270  # plus the core edges -> roughly 300 PIVOT edges in total
CORE_TO_NOISE_EDGES = 25  # core hosts/users also talk to ordinary machines

FIX_KIND = {
    "assume_role": "remove_trust",
    "permission": "revoke_permission",
    "runs_as": "revoke_permission",
    "network": "segment_network",
    "holds_secret": "rotate_secret",
    "secret_grants": "rotate_secret",
    "membership": "remove_membership",
}
FIX_TEXT = {
    "assume_role": "Remove sts:AssumeRole trust for {src} on {dst}",
    "permission": "Revoke the permission {src} holds on {dst}",
    "runs_as": "Stop {src} running as {dst}",
    "network": "Block the network route from {src} to {dst}",
    "holds_secret": "Rotate the secret {dst} stored on {src} and remove it from the host",
    "secret_grants": "Rotate {src} so it no longer grants access as {dst}",
    "membership": "Remove {src} from {dst}",
}


def build_environment() -> dict:
    """Pure Python: returns assets, edges, teams and decisions. No database involved."""
    rng = random.Random(SEED)

    assets = []  # dicts: id, name, kind, env, entry, crown, owner_team
    by_name = {}

    def add_asset(name, kind, entry, crown, team, env):
        assert KEBAB.match(name), name
        assert name not in by_name, name
        a = {"id": f"a{len(assets) + 1:03d}", "name": name, "kind": kind, "env": env,
             "entry": entry, "crown": crown, "owner_team": team}
        assets.append(a)
        by_name[name] = a
        return a

    for name, kind, entry, crown, team in CORE_ASSETS:
        add_asset(name, kind, entry, crown, team, "prod")

    noise_by_kind = {k: [] for k in NOISE_KINDS}
    team_names = [t[0] for t in TEAMS]
    for kind, (prefix, count) in NOISE_KINDS.items():
        for i in range(count):
            word = WORDS[i % len(WORDS)]
            name = f"{prefix}-{word}-{i + 1:02d}"
            a = add_asset(name, kind, False, False, rng.choice(team_names),
                          rng.choice(["prod", "staging", "corp"]))
            noise_by_kind[kind].append(a)

    edges = []
    seen_pairs = set()

    def add_edge(src, dst, kind, cost, disruption):
        pair = (src, dst)
        if src == dst or pair in seen_pairs:
            return False
        seen_pairs.add(pair)
        edges.append({
            "id": f"e{len(edges) + 1:03d}", "src": by_name[src]["id"], "dst": by_name[dst]["id"],
            "src_name": src, "dst_name": dst, "kind": kind, "cost": cost, "disruption": disruption,
            "fix_kind": FIX_KIND[kind], "fix_text": FIX_TEXT[kind].format(src=src, dst=dst),
        })
        return True

    for src, dst, kind, cost, disruption in CORE_EDGES:
        add_edge(src, dst, kind, cost, disruption)

    # Noise -> noise edges (never into core, never out of a crown jewel).
    while len(edges) < len(CORE_EDGES) + NOISE_EDGE_TARGET:
        src_kind, dst_kind, kind = rng.choice(NOISE_RULES)
        src = rng.choice(noise_by_kind[src_kind])["name"]
        dst = rng.choice(noise_by_kind[dst_kind])["name"]
        add_edge(src, dst, kind, rng.randint(1, 5), rng.randint(1, 10))

    # Core hosts/users -> ordinary noise machines (still can never reach a crown jewel).
    added = 0
    core_sources = [("web-frontend-01", "host"), ("app-server-02", "host"), ("batch-runner-01", "host"),
                    ("jump-host-01", "host"), ("vpn-gateway-01", "host"), ("intern-laptop", "user")]
    while added < CORE_TO_NOISE_EDGES:
        src, _ = rng.choice(core_sources)
        dst = rng.choice(noise_by_kind["host"])["name"]
        if add_edge(src, dst, "network", rng.randint(1, 5), rng.randint(1, 10)):
            added += 1

    teams = [{"id": f"t-{name}", "name": name, "lead": lead} for name, lead in TEAMS]
    owns = [{"team": f"t-{a['owner_team']}", "asset": a["id"]} for a in assets]

    # Memory that exists before the first run (so recall_decisions has something to show).
    # Both are about ordinary noise edges so they do not bias the demo plan.
    noise_network = [e for e in edges[len(CORE_EDGES):] if e["kind"] == "network"]
    noise_secret = [e for e in edges[len(CORE_EDGES):] if e["kind"] == "holds_secret"]
    decisions = [
        {"id": "d-hist-1", "edge": noise_network[0], "status": "rejected", "run": "seed",
         "reason": "Breaks the nightly payroll batch; segment it in Q4 instead",
         "at": "2026-08-14T10:20:00Z"},
        {"id": "d-hist-2", "edge": noise_secret[0], "status": "approved", "run": "seed",
         "reason": "Secret was stale; rotation done", "at": "2026-09-02T15:05:00Z"},
    ]
    return {"assets": assets, "edges": edges, "teams": teams, "owns": owns, "decisions": decisions}


def _batches(rows, size=100):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def seed_graph(graph_name: str) -> dict:
    """Drop and rebuild one graph. Idempotent. The caller chooses the graph name
    (tests pass 'test:...'; the reset endpoint passes 'env:<tenant>')."""
    env = build_environment()
    client = get_client()
    if graph_name in client.list_graphs():
        client.select_graph(graph_name).delete()
    g = client.select_graph(graph_name)

    # Indexes first, so the MATCH-by-id lookups below stay fast.
    g.query("CREATE INDEX FOR (a:Asset) ON (a.id)")
    g.query("CREATE INDEX FOR (a:Asset) ON (a.name)")

    for rows in _batches(env["assets"]):
        g.query("UNWIND $rows AS r CREATE (:Asset {id:r.id, name:r.name, kind:r.kind, env:r.env, "
                "entry:r.entry, crown:r.crown, owner_team:r.owner_team})", {"rows": rows})
    g.query("UNWIND $rows AS r CREATE (:Team {id:r.id, name:r.name, lead:r.lead})", {"rows": env["teams"]})
    for rows in _batches(env["owns"]):
        g.query("UNWIND $rows AS r MATCH (t:Team {id:r.team}), (a:Asset {id:r.asset}) "
                "CREATE (t)-[:OWNS]->(a)", {"rows": rows})
    for rows in _batches(env["edges"]):
        g.query("UNWIND $rows AS r MATCH (a:Asset {id:r.src}), (b:Asset {id:r.dst}) "
                "CREATE (a)-[:PIVOT {id:r.id, kind:r.kind, cost:r.cost, disruption:r.disruption, "
                "fix_kind:r.fix_kind, fix_text:r.fix_text}]->(b)", {"rows": rows})
    for d in env["decisions"]:
        e = d["edge"]
        g.query("MATCH (a:Asset {id:$src}), (b:Asset {id:$dst}) "
                "CREATE (x:Decision {id:$id, edge_id:$edge_id, status:$status, reason:$reason, at:$at, run:$run}) "
                "CREATE (x)-[:ABOUT]->(a), (x)-[:ABOUT]->(b)",
                {"src": e["src"], "dst": e["dst"], "id": d["id"], "edge_id": e["id"],
                 "status": d["status"], "reason": d["reason"], "at": d["at"], "run": d["run"]})
    return {"graph": graph_name, "assets": len(env["assets"]), "pivot_edges": len(env["edges"]),
            "teams": len(env["teams"]), "decisions": len(env["decisions"])}


if __name__ == "__main__":
    name = f"env:{config.TENANT_DEFAULT}"
    print(seed_graph(name))
