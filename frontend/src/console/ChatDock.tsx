import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, chatStream } from "../api";
import { useStore } from "../store";
import type { ChatEvent, Outcome } from "../types";
import { OutcomeBadge } from "./ui";

interface Call { tool: string; args: Record<string, unknown>; outcome?: Outcome }
interface Msg {
  id: number; role: "user" | "assistant"; text: string; calls: Call[]; notes: string[];
  pending?: boolean; checked?: boolean; reason?: string; mode?: string; error?: boolean;
}

const SUGGESTED = [
  "Can intern-laptop reach prod-customer-db?",
  "Plan a fix with budget 3 and simulate it.",
  "Is srv-alpha-01 safe?",
  "Scan at depth 4",
  "What did we decide before?",
];

const argText = (args: Record<string, unknown>) =>
  Object.entries(args).map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : String(v)}`).join(" ");

/** "LLM" when a model wrote the sentence, "Router" when the deterministic router did. */
export function modeInfo(mode?: string): { label: string; llm: boolean; templated: boolean } {
  if (!mode) return { label: "LLM or router", llm: false, templated: false };
  const llm = mode.startsWith("llm");
  return { label: llm ? "LLM" : "Router (no LLM)", llm, templated: mode.endsWith("+template") };
}

export function ChatDock() {
  const { actions } = useStore();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [lockedUntil, setLockedUntil] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [llmLimited, setLlmLimited] = useState(false);
  const idRef = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const locked = lockedUntil > now;
  const lastMode = [...messages].reverse().find((m) => m.mode)?.mode;
  const mode = modeInfo(lastMode);

  useEffect(() => {
    if (!locked) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [locked]);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages, open]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((id: number, fn: (m: Msg) => Msg) => {
    setMessages((all) => all.map((m) => (m.id === id ? fn(m) : m)));
  }, []);

  const send = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question || busy || locked) return;
    const history = messages.filter((m) => !m.pending && !m.error && m.text).slice(-6)
      .map((m) => ({ role: m.role, content: m.text }));
    const assistantId = ++idRef.current + 1;
    idRef.current = assistantId;
    setMessages((all) => [...all,
      { id: assistantId - 1, role: "user", text: question, calls: [], notes: [] },
      { id: assistantId, role: "assistant", text: "", calls: [], notes: [], pending: true }]);
    setInput("");
    setBusy(true);
    setLlmLimited(false);
    const controller = new AbortController();
    abortRef.current = controller;

    const onEvent = (ev: ChatEvent) => {
      if (ev.event === "tool_call") {
        patch(assistantId, (m) => ({ ...m, calls: [...m.calls, { tool: ev.tool, args: ev.args }] }));
      } else if (ev.event === "tool_result") {
        patch(assistantId, (m) => {
          const calls = [...m.calls];
          const i = calls.map((c) => c.tool === ev.tool && !c.outcome).lastIndexOf(true);
          if (i >= 0) calls[i] = { ...calls[i], outcome: ev.outcome };
          return { ...m, calls };
        });
        actions.applyChatResult(ev.tool, ev.envelope);
      } else if (ev.event === "provider_error") {
        if (/RateLimit/i.test(ev.error)) setLlmLimited(true);
        patch(assistantId, (m) => ({ ...m, notes: [...m.notes, `The free-tier model was unavailable (${ev.error}), so the router answers.`] }));
      } else if (ev.event === "final") {
        patch(assistantId, (m) => ({ ...m, pending: false, text: ev.text, checked: ev.checked, reason: ev.reason, mode: ev.mode }));
      }
    };

    try {
      await chatStream(question, history, onEvent, controller.signal);
      patch(assistantId, (m) => (m.pending ? { ...m, pending: false, text: m.text || "No answer came back. Try again.", error: !m.text } : m));
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        setLockedUntil(Date.now() + 60_000);
        setNow(Date.now());
        patch(assistantId, (m) => ({ ...m, pending: false, error: true, text: "Chat is rate limited for a minute to protect the free tier." }));
      } else {
        patch(assistantId, (m) => ({ ...m, pending: false, error: true, text: e instanceof ApiError ? e.message : "The chat request failed. Try again." }));
      }
    } finally {
      setBusy(false);
    }
  }, [actions, busy, locked, messages, patch]);

  const secondsLeft = Math.max(0, Math.ceil((lockedUntil - now) / 1000));

  if (!open) {
    return (
      <button className="dock-toggle" onClick={() => setOpen(true)} aria-label="Open Ask Chokepoint">
        <span className="dock-toggle__dot" aria-hidden="true" /> Ask <em>Chokepoint</em>
      </button>
    );
  }

  return (
    <section className="dock" aria-label="Ask Chokepoint">
      <header className="dock__head">
        <div>
          <h3 className="dock__title serif">Ask <em>Chokepoint</em></h3>
          <p className="dock__mode" title="Whether the last answer was written by a free language model or by the deterministic router">
            <span className={`dot ${mode.llm ? "dot--llm" : "dot--router"}`} aria-hidden="true" /> Mode: {mode.label}
            {llmLimited && <span className="chip chip--warn">LLM rate limited · router mode</span>}
          </p>
        </div>
        <button className="btn btn--small" onClick={() => setOpen(false)} aria-label="Close chat">Close</button>
      </header>

      <div className="dock__log" role="log" aria-live="polite">
        {messages.length === 0 && (
          <p className="hint">Ask about attack paths, reachability, fixes or past decisions. It works without any language model too: a deterministic router answers from the same tools.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`msg msg--${m.role} ${m.error ? "msg--error" : ""}`}>
            {m.calls.length > 0 && (
              <div className="msg__calls">
                {m.calls.map((c, i) => (
                  <span key={i} className="callchip" title={argText(c.args)}>
                    <span className="mono">{c.tool}</span>
                    {c.outcome && <OutcomeBadge outcome={c.outcome} />}
                  </span>
                ))}
              </div>
            )}
            {m.pending ? <span className="typing" aria-label="Working"><i /><i /><i /></span> : <p className="msg__text">{m.text}</p>}
            {m.notes.map((n) => <p key={n} className="msg__note">{n}</p>)}
            {m.role === "assistant" && !m.pending && !m.error && m.mode && (
              <p className="msg__meta">
                {m.checked
                  ? <span className="chip chip--fix" title="Every name and number in this sentence appears in the tool results">✓ checked</span>
                  : <span className="chip chip--warn" title={m.reason}>replaced by template · {m.reason || "failed the answer check"}</span>}
                <span className="chip">{modeInfo(m.mode).label}{modeInfo(m.mode).templated ? " + template" : ""}</span>
              </p>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <div className="dock__prompts" aria-label="Suggested prompts">
        {SUGGESTED.map((p) => (
          <button key={p} className="prompt" disabled={busy || locked} onClick={() => send(p)}>{p}</button>
        ))}
      </div>

      <form className="dock__form" onSubmit={(e) => { e.preventDefault(); void send(input); }}>
        <input className="input" value={input} maxLength={1000} disabled={busy || locked} onChange={(e) => setInput(e.target.value)}
          placeholder={locked ? `Rate limited, try again in ${secondsLeft}s` : "Ask a question…"} aria-label="Your question" />
        <button className="btn btn--cta btn--small" type="submit" disabled={busy || locked || !input.trim()}>{busy ? "…" : "Send"}</button>
      </form>
      {locked && <p className="dock__locked" role="status">Chat is rate limited for {secondsLeft}s. The rest of the console still works.</p>}
    </section>
  );
}
