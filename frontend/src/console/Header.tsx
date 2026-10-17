import { useState } from "react";
import { REPO_URL } from "../landing/Nav";
import { useGraph, useStore } from "../store";
import { Skeleton } from "./ui";

export function ConsoleHeader() {
  const { state } = useStore();
  const graph = useGraph();
  const [copied, setCopied] = useState(false);
  const mcpUrl = `${window.location.origin}/mcp`;
  const found = state.scan.data?.data?.count ?? (state.baseline.length || null);
  const healthy = state.health.status === "ok" && state.health.data?.falkordb;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(mcpUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const stats: [string, string | number | null][] = [
    ["Assets", graph?.nodes.length ?? null],
    ["Connections", graph?.edges.length ?? null],
    ["Entry points", graph ? graph.nodes.filter((n) => n.entry).length : null],
    ["Crown jewels", graph ? graph.nodes.filter((n) => n.crown).length : null],
    ["Paths found", found],
  ];

  return (
    <header className="chead">
      <div className="chead__title">
        <h2 className="serif chead__h">The <em>console</em></h2>
        <p className="hint">A synthetic cloud environment held in a FalkorDB graph. Every number comes from a live query.</p>
      </div>
      <dl className="chead__stats">
        {stats.map(([label, value]) => (
          <div key={label} className="stat">
            <dd className="stat__value serif">{state.graph.status === "loading" && label !== "Paths found" ? <Skeleton lines={1} height={22} /> : value ?? "—"}</dd>
            <dt className="stat__label">{label}</dt>
          </div>
        ))}
        <div className="stat">
          <dd className="stat__value"><span className={`dot ${healthy ? "dot--ok" : state.health.status === "error" ? "dot--bad" : "dot--wait"}`} aria-hidden="true" /> {healthy ? "connected" : state.health.status === "error" ? "unreachable" : "checking"}</dd>
          <dt className="stat__label">FalkorDB</dt>
        </div>
      </dl>
      <nav className="chead__links" aria-label="Project links">
        <a className="btn btn--small" href={REPO_URL} target="_blank" rel="noreferrer">GitHub</a>
        <button className="btn btn--small" onClick={copy} title={mcpUrl}>{copied ? "Copied ✓" : "Copy MCP endpoint"}</button>
        <a className="btn btn--small" href="/docs" target="_blank" rel="noreferrer">API docs</a>
      </nav>
    </header>
  );
}
