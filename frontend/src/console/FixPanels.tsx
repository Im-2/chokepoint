import { Fragment, useState } from "react";
import { useStore } from "../store";
import { markdownBlocks, plural, shortDate } from "../lib/format";
import { Card, Empty, ErrorNote, OutcomeBadge, OutcomeNote, Skeleton } from "./ui";

export function PlanCard() {
  const { state, actions } = useStore();
  const { plan, sim, proposal } = state;
  const env = plan.data;
  const d = env?.data;

  return (
    <Card title="Plan" aside={env ? <OutcomeBadge outcome={env.outcome} /> : null}>
      {plan.status === "loading" ? <Skeleton lines={4} height={30} /> : plan.status === "error" ? <ErrorNote message={plan.error ?? ""} /> : !env || !d ? (
        <Empty>Plan a remediation to choose the fewest, least disruptive edges to remove.</Empty>
      ) : env.outcome !== "answered_with_path" ? (
        <OutcomeNote outcome={env.outcome} notes={env.notes} />
      ) : (
        <>
          <div className="stat-row">
            <div><span className="stat__big serif">{d.paths_cut}<small> of {d.paths_total}</small></span><span className="stat__label">paths cut</span></div>
            <div><span className="stat__big serif">{d.paths_remaining}</span><span className="stat__label">remain</span></div>
            <div><span className="stat__big serif">{d.total_disruption}</span><span className="stat__label">total disruption</span></div>
          </div>
          <ol className="steps-list">
            {d.plan.map((s, i) => (
              <li key={s.edge_id} className="plan-step">
                <span className="plan-step__n">{i + 1}</span>
                <div>
                  <p className="plan-step__text">{s.fix_text}</p>
                  <p className="plan-step__meta mono">{s.from} → {s.to} · edge {s.edge_id}</p>
                  <p className="plan-step__chips">
                    <span className="chip">disruption {s.disruption}/10</span>
                    <span className="chip chip--fix">cuts {plural(s.paths_cut, "path")}</span>
                    <button className="chip chip--button" disabled={proposal.status === "loading"}
                      onClick={() => actions.runPropose(`Proposed on its own: ${s.fix_text}`, [s.edge_id])}>
                      Propose only this edge
                    </button>
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <p className="note">{env.notes}</p>
          {d.excluded_by_memory.some((e) => e.on_attack_path) && (
            <div className="note note--memory">
              <strong>Skipped because a human rejected it before:</strong>
              <ul>
                {d.excluded_by_memory.filter((e) => e.on_attack_path).map((e) => (
                  <li key={e.edge_id}><span className="mono">{e.edge_id}</span> · “{e.reason}” · {shortDate(e.at)}</li>
                ))}
              </ul>
            </div>
          )}
          {d.plan.length > 0 && (
            <div className="actions">
              <button className="btn btn--fix" disabled={sim.status === "loading"} onClick={() => actions.runSimulate()}>
                {sim.status === "loading" ? "Simulating…" : "Simulate on a scratch copy"}
              </button>
              <button className="btn" disabled={proposal.status === "loading"} onClick={() => actions.runPropose("Greedy plan from the console")}>
                {proposal.status === "loading" ? "Proposing…" : "Propose change"}
              </button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

export function SimulationCard() {
  const { state, actions } = useStore();
  const { sim } = state;
  const env = sim.data;
  const d = env?.data;
  const side = state.view.source === "sim" ? state.view.simSide : "after";

  return (
    <Card title="Simulation" aside={env ? <OutcomeBadge outcome={env.outcome} /> : null}>
      {sim.status === "loading" ? <Skeleton lines={3} height={36} /> : sim.status === "error" ? <ErrorNote message={sim.error ?? ""} /> : !env || !d ? (
        <Empty>Simulate a plan to prove it: the graph is copied, the fix applied to the copy, and the paths searched again.</Empty>
      ) : env.outcome !== "verified_fix" ? (
        <OutcomeNote outcome={env.outcome} notes={env.notes} />
      ) : (
        <>
          <div className="beforeafter" aria-live="polite">
            <button className={`ba ${side === "before" ? "ba--on" : ""}`} onClick={() => actions.setSimSide("before")} aria-pressed={side === "before"}>
              <span className="ba__label">Before</span><span className="ba__num serif">{d.paths_before}</span><span className="ba__unit">paths</span>
            </button>
            <span className="beforeafter__arrow serif" aria-hidden="true">→</span>
            <button className={`ba ba--after ${side === "after" ? "ba--on" : ""}`} onClick={() => actions.setSimSide("after")} aria-pressed={side === "after"}>
              <span className="ba__label">After</span><span className="ba__num serif">{d.paths_after}</span><span className="ba__unit">paths</span>
            </button>
          </div>
          <p className="hint">Toggle to redraw the graph before and after the fix. Removed edges are drawn cut.</p>
          <p className="chips">
            <span className="chip chip--fix">{d.fully_cut ? "all paths cut" : `${d.paths_after} remain`}</span>
            <span className="chip">{d.scratch_deleted ? "scratch graph deleted ✓" : "scratch graph still exists"}</span>
            <span className="chip mono">{d.edge_ids.join(" + ")}</span>
          </p>
          <p className="note">{env.notes}</p>
          {d.remaining_via.length > 0 && (
            <details className="details">
              <summary>{plural(d.remaining_via.length, "remaining path")}</summary>
              <ul className="remaining">{d.remaining_via.map((v, i) => <li key={i} className="mono">{v.join(" → ")}</li>)}</ul>
            </details>
          )}
        </>
      )}
    </Card>
  );
}

function Ticket({ markdown }: { markdown: string }) {
  const inline = (text: string) =>
    text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <strong key={i}>{part}</strong> : <Fragment key={i}>{part}</Fragment>));
  return (
    <div className="ticket">
      {markdownBlocks(markdown).map((b, i) => {
        if (b.type === "heading") return <h4 key={i} className="ticket__title serif">{b.text}</h4>;
        if (b.type === "paragraph") return <p key={i}>{inline(b.text)}</p>;
        return (
          <table key={i} className="table table--compact">
            <thead><tr>{b.header.map((h) => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>{b.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k}>{c}</td>)}</tr>)}</tbody>
          </table>
        );
      })}
    </div>
  );
}

function ConfigDiff({ text }: { text: string }) {
  return (
    <pre className="diff-block" aria-label="Configuration diff">
      {text.split("\n").map((line, i) => {
        const cls = line.startsWith("+++") || line.startsWith("---") ? "diff diff--meta" : line.startsWith("+") ? "diff diff--add"
          : line.startsWith("-") ? "diff diff--del" : "diff diff--note";
        return <span key={i} className={cls}>{line || " "}{"\n"}</span>;
      })}
    </pre>
  );
}

/** The change record. Approve and Reject are plain buttons for a person to click; nothing automated calls them. */
export function ProposalCard() {
  const { state, actions } = useStore();
  const { proposal, decide } = state;
  const env = proposal.data;
  const d = env?.data;
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const decided = decide.status === "ok" ? decide.data?.data.status : null;
  const busy = decide.status === "loading";

  return (
    <Card title="Change proposal" aside={env ? <OutcomeBadge outcome={decided ? "recorded" : env.outcome} /> : null}>
      {proposal.status === "loading" ? <Skeleton lines={5} height={22} /> : proposal.status === "error" ? <ErrorNote message={proposal.error ?? ""} /> : !env || !d ? (
        <Empty>Propose a plan to file a change record with an owner, a ticket and a config diff. A person then approves or rejects it.</Empty>
      ) : env.outcome !== "proposed" ? (
        <OutcomeNote outcome={env.outcome} notes={env.notes} />
      ) : (
        <>
          <p className="chips">
            <span className="chip">status: {decided ?? d.status}</span>
            {d.owner_teams.map((t) => <span key={t} className="chip chip--owner">owner: {t}</span>)}
            <span className="chip mono">{d.run}</span>
          </p>
          <Ticket markdown={d.ticket_markdown} />
          <ConfigDiff text={d.config_diff} />
          {decided ? (
            <p className={`note ${decided === "approved" ? "note--fix" : "note--decoy"}`}>
              Recorded as <strong>{decided}</strong>{decide.data?.data.reason ? ` · “${decide.data.data.reason}”` : ""}. The planner will remember this.
            </p>
          ) : (
            <>
              <p className="hint">Only a person can decide. The assistant can propose but never approves or rejects.</p>
              {!rejecting ? (
                <div className="actions">
                  <button className="btn btn--fix" disabled={busy} onClick={() => actions.runDecide("approve")}>Approve</button>
                  <button className="btn btn--attack" disabled={busy} onClick={() => setRejecting(true)}>Reject…</button>
                </div>
              ) : (
                <div className="reject">
                  <label className="field__label" htmlFor="reject-reason">Reason (required, it becomes memory)</label>
                  <textarea id="reject-reason" className="input" rows={2} maxLength={300} value={reason} autoFocus
                    placeholder="e.g. breaks the nightly ETL" onChange={(e) => setReason(e.target.value)} />
                  <div className="actions">
                    <button className="btn btn--attack" disabled={busy || reason.trim().length < 3}
                      onClick={() => actions.runDecide("reject", reason.trim())}>{busy ? "Recording…" : "Reject with reason"}</button>
                    <button className="btn" disabled={busy} onClick={() => { setRejecting(false); setReason(""); }}>Cancel</button>
                  </div>
                </div>
              )}
              {decide.status === "error" && <ErrorNote message={decide.error ?? ""} />}
            </>
          )}
        </>
      )}
    </Card>
  );
}
