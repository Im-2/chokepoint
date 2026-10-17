import type { ReactNode } from "react";
import { outcomeInfo } from "../lib/format";
import type { Outcome } from "../types";

/** One badge for each of the seven outcomes; the hover text explains it in plain words. */
export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const info = outcomeInfo(outcome);
  return <span className={`badge badge--${info.tone}`} title={info.hint}>{info.label}</span>;
}

/** The server's note for an outcome, shown prominently for the two honest "nothing found" outcomes. */
export function OutcomeNote({ outcome, notes }: { outcome: Outcome; notes: string }) {
  if (!notes) return null;
  const warn = outcome === "not_in_graph" || outcome === "unknown_asset";
  return <p className={warn ? "note note--warn" : "note"}>{notes}</p>;
}

export function Skeleton({ lines = 3, height = 14 }: { lines?: number; height?: number }) {
  return (
    <div className="skeleton-group" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ height, width: `${100 - (i % 3) * 14}%` }} />
      ))}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-note" role="alert">
      <span>{message}</span>
      {onRetry && <button className="btn btn--small" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Card({ title, aside, children, className = "" }: {
  title: ReactNode; aside?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      <header className="card__head">
        <h3 className="card__title">{title}</h3>
        {aside && <div className="card__aside">{aside}</div>}
      </header>
      <div className="card__body">{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

/** A hop chain such as `a -> b -> c`, wrapping nicely. */
export function Chain({ names }: { names: string[] }) {
  return (
    <span className="chain">
      {names.map((n, i) => (
        <span key={`${n}-${i}`} className="chain__item">
          <span className="chain__name">{n}</span>
          {i < names.length - 1 && <span className="chain__arrow" aria-hidden="true">→</span>}
        </span>
      ))}
    </span>
  );
}
