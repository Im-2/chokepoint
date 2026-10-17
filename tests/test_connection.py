"""Phase 0: reach FalkorDB and check the features the brief relies on.
Uses only 'test:' graphs and cleans up; never touches env:acme."""
import uuid


def test_basic_query(test_graph):
    test_graph.query("CREATE (:Asset {id:'a', name:'a-b'})")
    assert test_graph.ro_query("MATCH (n:Asset) RETURN n.name").result_set == [["a-b"]]


def test_graph_copy_and_delete(test_graph):
    """Simulation depends on copy + delete working on this server (Cloud included)."""
    from app.db import get_client

    test_graph.query("CREATE (:Asset {id:'a'})-[:PIVOT {id:'e1'}]->(:Asset {id:'b'})")
    copy_name = f"test:{uuid.uuid4().hex[:8]}"
    copy = test_graph.copy(copy_name)
    try:
        copy.query("MATCH ()-[r:PIVOT {id:'e1'}]->() DELETE r")
        assert copy.ro_query("MATCH ()-[r:PIVOT]->() RETURN count(r)").result_set == [[0]]
        # the original is untouched by edits to the copy
        assert test_graph.ro_query("MATCH ()-[r:PIVOT]->() RETURN count(r)").result_set == [[1]]
    finally:
        copy.delete()
    assert copy_name not in get_client().list_graphs()


def test_depth_param_distinct_and_algos(test_graph):
    g = test_graph
    g.query(
        "CREATE (a:Asset {id:'a',name:'a-a',entry:true}),(b:Asset {id:'b',name:'b-b'}),"
        "(c:Asset {id:'c',name:'c-c',crown:true}),"
        "(a)-[:PIVOT {id:'1',cost:1}]->(b),(b)-[:PIVOT {id:'2',cost:2}]->(c)"
    )
    # FalkorDB rejects a parameter as a variable-length bound (*1..$depth), so queries.py
    # validates depth as an int in 1..8 and writes it into the text. Names/ids stay parameters.
    depth = int(3)
    paths = g.ro_query(
        f"MATCH p=(e:Asset {{entry:true}})-[:PIVOT*1..{depth}]->(t:Asset {{crown:true}}) "
        "RETURN length(p)"
    ).result_set
    assert paths == [[2]]
    cnt = g.ro_query(
        "MATCH p=(e:Asset {entry:true})-[:PIVOT*1..3]->(t:Asset {crown:true}) "
        "UNWIND relationships(p) AS r RETURN r.id, count(DISTINCT p) ORDER BY r.id"
    ).result_set
    assert cnt == [["1", 1], ["2", 1]]
    sp = g.ro_query(
        "MATCH (a:Asset {name:'a-a'}),(b:Asset {name:'c-c'}) "
        "CALL algo.SPpaths({sourceNode:a,targetNode:b,relTypes:['PIVOT'],"
        "relDirection:'outgoing',weightProp:'cost',pathCount:1}) YIELD path,pathWeight "
        "RETURN [n IN nodes(path)|n.name], pathWeight"
    ).result_set
    assert sp == [[["a-a", "b-b", "c-c"], 3]]
    assert g.ro_query("CALL algo.pageRank('Asset','PIVOT') YIELD node,score RETURN count(node)").result_set == [[3]]
    assert g.ro_query(
        "CALL algo.betweenness({nodeLabels:['Asset'],relationshipTypes:['PIVOT']}) "
        "YIELD node,score RETURN count(node)"
    ).result_set == [[3]]
