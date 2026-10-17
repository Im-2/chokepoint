import { useState, type ReactElement } from "react";

// small SVG outlines of the Cytoscape shapes used for each asset kind
const KINDS: { kind: string; label: string; shape: ReactElement }[] = [
  { kind: "user", label: "User", shape: <circle cx="8" cy="8" r="5.5" /> },
  { kind: "service_account", label: "Service account", shape: <path d="M8 2l6 6-6 6-6-6z" /> },
  { kind: "role", label: "Role", shape: <rect x="2" y="3.5" width="12" height="9" rx="3" /> },
  { kind: "group", label: "Group", shape: <path d="M4.5 3h7l3 5-3 5h-7l-3-5z" /> },
  { kind: "host", label: "Host", shape: <rect x="2.5" y="3" width="11" height="10" /> },
  { kind: "secret", label: "Secret", shape: <path d="M2 3h9l3 5-3 5H2z" /> },
  { kind: "datastore", label: "Datastore", shape: <path d="M3 4c0-1.5 10-1.5 10 0v8c0 1.5-10 1.5-10 0z" /> },
  { kind: "vault", label: "Vault", shape: <path d="M5 2h6l3 3v6l-3 3H5l-3-3V5z" /> },
];

function Icon({ children, className = "" }: { children: ReactElement; className?: string }) {
  return <svg className={`legend__icon ${className}`} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">{children}</svg>;
}

export function Legend() {
  // open on laptops; collapsed on phones, where it would otherwise cover the graph
  const [open, setOpen] = useState(() => window.matchMedia("(min-width: 700px)").matches);
  return (
    <aside className="legend" aria-label="Graph legend">
      <button className="legend__toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        Legend <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="legend__body">
          <ul className="legend__list">
            {KINDS.map((k) => (
              <li key={k.kind}><Icon>{k.shape}</Icon>{k.label}</li>
            ))}
          </ul>
          <ul className="legend__list legend__list--marks">
            <li><span className="legend__swatch legend__swatch--entry" />Entry point: an attacker can start here</li>
            <li><Icon className="legend__star"><path d="M8 1.5l1.9 4.2 4.6.5-3.4 3.1 1 4.5L8 11.5 3.9 13.8l1-4.5L1.5 6.2l4.6-.5z" /></Icon>Crown jewel</li>
            <li><span className="legend__line legend__line--attack" />Attack path</li>
            <li><span className="legend__line legend__line--fix" />Proposed fix</li>
            <li><span className="legend__line legend__line--cut" />Removed (cut) edge</li>
            <li><span className="legend__line legend__line--ghost" />Path that a fix removed</li>
            <li><span className="legend__swatch legend__swatch--noise" />Ordinary asset (dimmed)</li>
          </ul>
        </div>
      )}
    </aside>
  );
}
