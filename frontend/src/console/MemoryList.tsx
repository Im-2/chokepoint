import { useStore } from "../store";
import { shortDate } from "../lib/format";
import { Card, Empty, ErrorNote, Skeleton } from "./ui";

/** Decisions stored in the graph; the planner reads rejected edges from here before it chooses. */
export function MemoryList() {
  const { state, actions } = useStore();
  const { decisions } = state;
  const list = decisions.data?.data.decisions ?? [];

  return (
    <Card title="Decision memory" aside={<button className="btn btn--small" onClick={() => actions.loadDecisions()} disabled={decisions.status === "loading"}>Refresh</button>}>
      {decisions.status === "loading" && !list.length ? <Skeleton lines={3} height={30} /> : decisions.status === "error" ? (
        <ErrorNote message={decisions.error ?? ""} onRetry={() => actions.loadDecisions()} />
      ) : list.length === 0 ? (
        <Empty>No decisions are recorded yet. Approvals and rejections you make are stored in the graph.</Empty>
      ) : (
        <ul className="memory">
          {list.map((m) => (
            <li key={m.decision_id} className="memory__item">
              <span className={`status status--${m.status}`}>{m.status}</span>
              <div>
                <p className="memory__reason">{m.reason || <em>no reason given</em>}</p>
                <p className="memory__meta mono">edge {m.edge_id} · {shortDate(m.at)}{m.assets.length ? ` · ${m.assets.join(" → ")}` : ""}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
