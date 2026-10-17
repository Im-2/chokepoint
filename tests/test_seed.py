"""Phase 1 / brief test 1: the seed has the right size and the planted properties."""
from app import queries
from app.seed import CHOKE_EDGE, CORE_ASSETS, DECOY_EDGE, KEBAB, build_environment


def rows(g, text, params=None):
    return g.ro_query(text, params).result_set


def test_sizes_within_free_tier_budget(seeded_graph):
    assets = rows(seeded_graph, "MATCH (a:Asset) RETURN count(a)")[0][0]
    pivots = rows(seeded_graph, "MATCH ()-[r:PIVOT]->() RETURN count(r)")[0][0]
    assert 120 <= assets <= 200
    assert 300 <= pivots <= 500


def test_seed_is_deterministic():
    assert build_environment() == build_environment()


def test_names_are_unique_kebab_case():
    names = [a["name"] for a in build_environment()["assets"]]
    assert len(names) == len(set(names))
    assert all(KEBAB.match(n) for n in names)


def test_entries_and_crowns(seeded_graph):
    assert len(rows(seeded_graph, "MATCH (a:Asset {entry:true}) RETURN a")) == 3
    crowns = {r[0] for r in rows(seeded_graph, "MATCH (a:Asset {crown:true}) RETURN a.name")}
    assert crowns == {"prod-customer-db", "payments-signing-key"}


def test_shortest_entry_to_crown_is_exactly_4_hops(seeded_graph):
    paths = rows(seeded_graph, queries.attack_paths(8))
    assert min(p[2] for p in paths) == 4
    assert rows(seeded_graph, queries.attack_paths(2)) == []
    assert rows(seeded_graph, queries.attack_paths(3)) == []
    depth4 = rows(seeded_graph, queries.attack_paths(4))
    assert any("svc-legacy-etl" in p[0] for p in depth4)


def test_path_count_is_in_target_range(seeded_graph):
    assert 10 <= len(rows(seeded_graph, queries.attack_paths(8))) <= 30


def test_decoy_is_on_most_paths_and_choke_is_cheap(seeded_graph):
    freq = rows(seeded_graph, queries.choke_edge_frequency(8))
    ids = {(r[0]): r for r in freq}
    by_pair = {}
    for src, dst in (CHOKE_EDGE, DECOY_EDGE):
        eid = rows(seeded_graph, "MATCH (a:Asset {name:$s})-[r:PIVOT]->(b:Asset {name:$d}) RETURN r.id",
                   {"s": src, "d": dst})[0][0]
        by_pair[(src, dst)] = ids[eid]
    decoy, choke = by_pair[DECOY_EDGE], by_pair[CHOKE_EDGE]
    assert freq[0][0] == decoy[0]            # decoy has the most paths_through
    assert decoy[2] == 9 and choke[2] <= 2   # but is the most disruptive
    assert choke[4] > 0.5 * len(rows(seeded_graph, queries.attack_paths(8)))  # choke is on most paths


def test_noise_never_reaches_a_crown_jewel(seeded_graph):
    core = {a[0] for a in CORE_ASSETS}
    for via, _, _ in rows(seeded_graph, queries.attack_paths(8)):
        assert set(via) <= core


def test_owners_and_memory_exist(seeded_graph):
    owner = rows(seeded_graph, "MATCH (t:Team)-[:OWNS]->(a:Asset {name:$n}) RETURN t.name, t.lead",
                 {"n": "prod-customer-db"})
    assert owner == [["data-eng", "Tunde Bello"]]
    statuses = {r[0] for r in rows(seeded_graph, "MATCH (d:Decision) RETURN d.status")}
    assert statuses == {"rejected", "approved"}


def test_seed_is_idempotent():
    import uuid
    from app.db import get_client
    from app.seed import seed_graph
    name = f"test:idem-{uuid.uuid4().hex[:8]}"
    try:
        a, b = seed_graph(name), seed_graph(name)
        assert a == b
        assert get_client().select_graph(name).ro_query("MATCH (a:Asset) RETURN count(a)").result_set[0][0] == a["assets"]
    finally:
        get_client().select_graph(name).delete()
