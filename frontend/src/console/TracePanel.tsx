import { useState } from "react";
import { useStore } from "../store";
import { Card, Empty, OutcomeBadge } from "./ui";

const short = (v: unknown) => {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 70 ? `${s.slice(0, 67)}…` : s;
};

/** Every tool call this session, with the queries the server reports for it (tool, args, ms, rows). */
export function TracePanel() {
  const { state } = useStore();
  const { traces } = state;
  const [open, setOpen] = useState(false);
  const totalMs = traces.reduce((sum, r) => sum + r.entries.reduce((s, e) => s + e.ms, 0), 0);

  return (
    <Card className="trace" title="Trace"
      aside={<>
        <span className="hint">{traces.length} calls · {Math.round(totalMs)} ms of query time</span>
        <button className="btn btn--small" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{open ? "Hide" : "Show"}</button>
      </>}>
      {!open ? null : traces.length === 0 ? (
        <Empty>Every response carries its own trace. Run something to see each query, its arguments, how long it took and how many rows it returned.</Empty>
      ) : (
        <div className="trace__list">
          {traces.map((run, idx) => (
            <details key={run.id} className="trace__run" open={idx === 0}>
              <summary>
                <span className="trace__label">{run.label}</span>
                {run.outcome && <OutcomeBadge outcome={run.outcome} />}
                <span className="trace__total mono">{Math.round(run.entries.reduce((s, e) => s + e.ms, 0))} ms</span>
              </summary>
              {run.entries.length > 0 && (
                <table className="table table--compact">
                  <thead><tr><th>Tool</th><th>Query</th><th>Arguments</th><th>ms</th><th>Rows</th></tr></thead>
                  <tbody>
                    {run.entries.map((e, i) => (
                      <tr key={i}>
                        <td className="mono">{e.tool}</td>
                        <td className="mono">{e.query}</td>
                        <td className="mono trace__args" title={JSON.stringify(e.args)}>{short(e.args)}</td>
                        <td className="num">{e.ms}</td>
                        <td className="num">{e.rows}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </details>
          ))}
        </div>
      )}
    </Card>
  );
}
