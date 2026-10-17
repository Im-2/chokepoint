"""Print the real numbers for a seeded graph: python -m scripts.seed_report [graph-name]
Default graph is env:acme. Read-only. The budget=1 preview is a tiny greedy stand-in;
the real planner arrives in Phase 2 (app/planner.py)."""
import sys

from app import config, queries
from app.db import get_client


def main(name: str):
    g = get_client().select_graph(name)

    def q(text, params=None):
        return g.ro_query(text, params).result_set

    print(f"graph: {name}")
    print("assets:", q("MATCH (a:Asset) RETURN count(a)")[0][0],
          "| PIVOT edges:", q("MATCH ()-[r:PIVOT]->() RETURN count(r)")[0][0],
          "| OWNS edges:", q("MATCH ()-[r:OWNS]->() RETURN count(r)")[0][0],
          "| teams:", q("MATCH (t:Team) RETURN count(t)")[0][0],
          "| decisions:", q("MATCH (d:Decision) RETURN count(d)")[0][0])
    print("entries:", [r[0] for r in q("MATCH (a:Asset {entry:true}) RETURN a.name ORDER BY a.name")])
    print("crowns:", [r[0] for r in q("MATCH (a:Asset {crown:true}) RETURN a.name ORDER BY a.name")])

    for d in (2, 3, 4, 8):
        print(f"attack paths at depth {d}: {len(q(queries.attack_paths(d), {"limit": 500}))}")

    paths = q(queries.attack_paths(8), {"limit": 500})
    shortest = paths[0][2]
    print(f"\nshortest entry->crown path: {shortest} hops")
    for via, _, hops, *_ in paths:
        if hops == shortest:
            print("  ", " -> ".join(via))
    print("path length histogram:", {h: sum(1 for p in paths if p[2] == h) for h in sorted({p[2] for p in paths})})

    freq = q(queries.choke_edge_frequency(8))
    print("\ntop edges by paths_through (naive ranking):")
    for edge_id, kind, dis, fix, _s, _d, n in freq[:6]:
        print(f"  {edge_id}  paths={n:<3} disruption={dis:<2} ratio={n/dis:.2f}  {fix}")
    print("top edges by paths_through / disruption (cost-aware):")
    for edge_id, kind, dis, fix, _s, _d, n in sorted(freq, key=lambda r: -r[6] / r[2])[:6]:
        print(f"  {edge_id}  paths={n:<3} disruption={dis:<2} ratio={n/dis:.2f}  {fix}")

    # Greedy preview: repeatedly pick the edge cutting most remaining paths per disruption.
    info = {r[0]: (r[2], r[3]) for r in freq}
    remaining = [set(p[1]) for p in paths]
    total, chosen = len(remaining), []
    for budget in (1, 2, 3):
        if not remaining:
            break
        best = max(info, key=lambda e: sum(1 for p in remaining if e in p) / info[e][0]
                   if e not in chosen else -1)
        chosen.append(best)
        remaining = [p for p in remaining if best not in p]
        print(f"greedy preview budget={budget}: picks {chosen} -> {total - len(remaining)} of {total} cut, {len(remaining)} left")

    # Honesty probe: pick a noise asset and check it has no path to the customer DB.
    noise = q("MATCH (a:Asset {kind:'host'}) WHERE NOT a.name IN ['web-frontend-01','app-server-02',"
              "'batch-runner-01','jump-host-01','vpn-gateway-01'] RETURN a.name ORDER BY a.name LIMIT 1")[0][0]
    n = q("MATCH p=(a:Asset {name:$a})-[:PIVOT*1..8]->(b:Asset {name:'prod-customer-db'}) RETURN count(p)", {"a": noise})[0][0]
    print(f"\nnoise asset {noise} -> prod-customer-db paths: {n}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else f"env:{config.TENANT_DEFAULT}")
