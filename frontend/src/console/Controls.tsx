import { useMemo, useState } from "react";
import { useGraph, useStore } from "../store";
import { AssetPicker } from "./AssetPicker";
import { Card, ErrorNote } from "./ui";

const DEPTH_HINT: Record<number, string> = {
  1: "Direct connections only.",
  2: "Two hops: a quick look, and an easy way to miss a longer route.",
  3: "Three hops.",
  4: "Four hops: deep enough to reach the first crown jewel in this environment.",
};

export function Controls() {
  const { state, actions } = useStore();
  const graph = useGraph();
  const names = useMemo(() => (graph ? graph.nodes.map((n) => n.name) : []), [graph]);
  const [from, setFrom] = useState("intern-laptop");
  const [to, setTo] = useState("prod-customer-db");
  const [budget, setBudget] = useState(3);
  const ready = state.graph.status === "ok";

  return (
    <div className="controls">
      <Card title="1 · Scan for attack paths">
        <label className="field__label" htmlFor="depth">
          Depth <strong className="field__value">{state.scanDepth} {state.scanDepth === 1 ? "hop" : "hops"}</strong>
        </label>
        <input id="depth" type="range" min={1} max={8} step={1} value={state.scanDepth}
          onChange={(e) => actions.setDepth(Number(e.target.value))} className="slider" />
        <p className="hint">{DEPTH_HINT[state.scanDepth] ?? "A deep search: every route up to this many hops."}</p>
        <button className="btn btn--attack" disabled={!ready || state.scan.status === "loading"}
          onClick={() => actions.runScan(state.scanDepth)}>
          {state.scan.status === "loading" ? "Scanning…" : "Scan"}
        </button>
        {state.scan.status === "error" && <ErrorNote message={state.scan.error ?? ""} onRetry={() => actions.runScan(state.scanDepth)} />}
      </Card>

      <Card title="2 · Can it reach?">
        <AssetPicker label="From" value={from} onChange={setFrom} names={names} placeholder="intern-laptop" />
        <AssetPicker label="To" value={to} onChange={setTo} names={names} placeholder="prod-customer-db" />
        <button className="btn" disabled={!ready || !from.trim() || !to.trim() || state.reach.status === "loading"}
          onClick={() => actions.runReach(from.trim(), to.trim())}>
          {state.reach.status === "loading" ? "Checking…" : "Check reach"}
        </button>
        {state.reach.status === "error" && <ErrorNote message={state.reach.error ?? ""} />}
      </Card>

      <Card title="3 · Pick the fix">
        <button className="btn" disabled={!ready || state.choke.status === "loading"} onClick={() => actions.runChoke()}>
          {state.choke.status === "loading" ? "Ranking…" : "Rank choke edges"}
        </button>
        <div className="divider" />
        <span className="field__label" id="budget-label">Plan budget (edges to remove)</span>
        <div className="segmented" role="radiogroup" aria-labelledby="budget-label">
          {[1, 2, 3].map((b) => (
            <button key={b} role="radio" aria-checked={budget === b}
              className={budget === b ? "segmented__item segmented__item--on" : "segmented__item"} onClick={() => setBudget(b)}>
              {b}
            </button>
          ))}
        </div>
        <button className="btn btn--fix" disabled={!ready || state.plan.status === "loading"} onClick={() => actions.runPlan(budget)}>
          {state.plan.status === "loading" ? "Planning…" : "Plan remediation"}
        </button>
        {state.choke.status === "error" && <ErrorNote message={state.choke.error ?? ""} onRetry={() => actions.runChoke()} />}
        {state.plan.status === "error" && <ErrorNote message={state.plan.error ?? ""} onRetry={() => actions.runPlan(budget)} />}
      </Card>
    </div>
  );
}
