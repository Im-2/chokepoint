import { useMemo } from "react";
import { useStore } from "../store";
import { effectiveView } from "../lib/graphView";
import { plural } from "../lib/format";
import type { ChokeRow, Envelope } from "../types";
import { Card, Chain, Empty, ErrorNote, OutcomeBadge, OutcomeNote, Skeleton } from "./ui";

/** Attack paths (or the single route of a reach question), as clickable rows that highlight on the graph. */
export function PathList() {
  const { state, actions } = useStore();
  const { view } = state;
  const loading = [state.scan, state.reach].some((s) => s.status === "loading");

  const { title, slice } = useMemo(() => {
    switch (view.source) {
      case "reach": return { title: "Route", slice: state.reach };
      case "plan": return { title: "Attack paths before any fix", slice: state.plan };
      case "sim": return { title: view.simSide === "before" ? "Attack paths before the fix" : "Paths that remain after the fix", slice: state.sim };
      default: return { title: "Attack paths", slice: state.scan };
    }
  }, [view.source, view.simSide, state.reach, state.plan, state.sim, state.scan]);

  const paths = useMemo(() => effectiveView({ ...view, selected: null }, state.baseline).paths, [view, state.baseline]);
  const env = slice.data as Envelope | null;
  const error = state.scan.status === "error" ? state.scan.error : state.reach.status === "error" ? state.reach.error : null;

  return (
    <Card title={title} aside={env && view.source !== "none" ? <OutcomeBadge outcome={env.outcome} /> : null}>
      {loading ? <Skeleton lines={4} height={34} /> : error ? <ErrorNote message={error} /> : view.source === "none" || !env ? (
        <Empty>Run a scan to see the routes an attacker can take. Try depth 4, then depth 8.</Empty>
      ) : (
        <>
          <OutcomeNote outcome={env.outcome} notes={env.outcome === "not_in_graph" || env.outcome === "unknown_asset" ? env.notes : ""} />
          {view.source === "reach" && env.outcome === "answered_with_path" && (
            <p className="hint">{plural(env.data.hops, "hop")} · attacker cost {Math.round(env.data.attacker_cost)} (the cheapest route for an attacker)</p>
          )}
          {view.source === "scan" && env.outcome === "answered_with_path" && (
            <p className="hint">{plural(env.data.count, "path")} within {env.data.depth} hops · shortest {env.data.shortest_hops} hops. Click one to highlight it.</p>
          )}
          {paths.length > 0 && (
            <ol className="paths">
              {paths.map((p, i) => (
                <li key={p.edges.map((e) => e.id).join(">")}>
                  <button className={`path ${view.selected === i ? "path--on" : ""}`} aria-pressed={view.selected === i}
                    onClick={() => actions.selectPath(view.selected === i ? null : i)}>
                    <span className="path__hops">{p.edges.length} hops</span>
                    <Chain names={p.nodes.map((n) => n.name)} />
                  </button>
                </li>
              ))}
            </ol>
          )}
          {paths.length === 0 && env.outcome === "verified_fix" && (
            <p className="note note--fix">No modelled attack path remains after this fix.</p>
          )}
        </>
      )}
    </Card>
  );
}

const barWidth = (d: number) => `${Math.min(100, d * 10)}%`;

/** Choke edges ranked by paths cut per unit of disruption, with the naive "most paths" edge marked as the decoy. */
export function ChokeTable() {
  const { state, actions } = useStore();
  const { choke } = state;
  const rows = useMemo(() => {
    const data = choke.data?.data;
    if (!data) return [] as ChokeRow[];
    const list = [...data.ranked];
    if (!list.some((r) => r.edge_id === data.naive_most_paths.edge_id)) list.push(data.naive_most_paths);
    return list;
  }, [choke.data]);
  const best = choke.data?.data.ranked[0]?.edge_id;
  const naive = choke.data?.data.naive_most_paths.edge_id;
  const decoy = naive && naive !== best ? naive : null;

  return (
    <Card title="Choke edges" aside={choke.data ? <OutcomeBadge outcome={choke.data.outcome} /> : null}>
      {choke.status === "loading" ? <Skeleton lines={5} height={28} /> : choke.status === "error" ? <ErrorNote message={choke.error ?? ""} onRetry={() => actions.runChoke()} /> : !choke.data ? (
        <Empty>Rank the edges to see which single change cuts the most paths for the least disruption.</Empty>
      ) : choke.data.outcome !== "answered_with_path" ? (
        <OutcomeNote outcome={choke.data.outcome} notes={choke.data.notes} />
      ) : (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Edge</th><th title="Attack paths that go through this edge">Paths</th><th title="Business disruption if removed, 1 to 10">Disruption</th><th title="Paths cut per unit of disruption">Per disruption</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const isDecoy = r.edge_id === decoy;
                  const isBest = r.edge_id === best;
                  const focused = state.view.focusEdge === r.edge_id;
                  return (
                    <tr key={r.edge_id} className={`${isDecoy ? "row--decoy" : ""} ${isBest ? "row--best" : ""} ${focused ? "row--focus" : ""}`}
                      onClick={() => actions.focusEdge(focused ? null : r.edge_id)} tabIndex={0}
                      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), actions.focusEdge(focused ? null : r.edge_id))}
                      title={r.fix_text}>
                      <td>
                        <span className="mono edge-name"><span>{r.from}</span><span>→ {r.to}</span></span>
                        {isDecoy && <span className="tag tag--decoy">Decoy</span>}
                        {isBest && <span className="tag tag--best">Best</span>}
                      </td>
                      <td className="num">{r.paths_through}</td>
                      <td><span className="bar" aria-label={`disruption ${r.disruption} of 10`}><i style={{ width: barWidth(r.disruption) }} /></span> <span className="num">{r.disruption}</span></td>
                      <td className="num">{r.score.toFixed(2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {decoy && choke.data.data.naive_most_paths && (
            <p className="note note--decoy">
              <strong>Decoy:</strong> {choke.data.data.naive_most_paths.from} → {choke.data.data.naive_most_paths.to} is on the most
              paths ({choke.data.data.naive_most_paths.paths_through} of {choke.data.data.total_paths}) but costs a disruption of{" "}
              {choke.data.data.naive_most_paths.disruption}/10. Ranking by path count alone would pick it.
            </p>
          )}
          <p className="hint">Click a row to mark that edge on the graph.</p>
        </>
      )}
    </Card>
  );
}
