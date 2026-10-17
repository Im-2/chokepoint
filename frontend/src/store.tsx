import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { api, ApiError } from "./api";
import { computeLayout, type Layout } from "./lib/layout";
import type {
  AttackPath, ChokeRow, DecisionRecord, Envelope, GraphResponse, PlanData, ProposalData, SimulationData,
  TraceEntry, TraceRun,
} from "./types";

export interface Async<T> { status: "idle" | "loading" | "ok" | "error"; data: T | null; error: string | null }
const idle = <T,>(): Async<T> => ({ status: "idle", data: null, error: null });

type ScanEnv = Envelope<{ depth: number; count: number; shortest_hops: number; truncated: boolean }>;
type ReachEnv = Envelope<{ from: string; to: string; hops: number; attacker_cost: number; unknown?: string[] }>;
type ChokeEnv = Envelope<{ depth: number; total_paths: number; ranked: ChokeRow[]; naive_most_paths: ChokeRow }>;
type PlanEnv = Envelope<PlanData>;
type SimEnv = Envelope<SimulationData>;
type ProposalEnv = Envelope<ProposalData>;
type DecideEnv = Envelope<{ status: string; reason: string; decided: { decision_id: string; edge_id: string }[] }>;
type DecisionsEnv = Envelope<{ decisions: DecisionRecord[] }>;

/** What the graph canvas should show. */
export interface View {
  source: "none" | "scan" | "reach" | "plan" | "sim";
  paths: AttackPath[];
  planEdges: string[];
  cutEdges: string[];
  selected: number | null;
  focusEdge: string | null;
  simSide: "before" | "after";
}
const emptyView: View = { source: "none", paths: [], planEdges: [], cutEdges: [], selected: null, focusEdge: null, simSide: "after" };

interface State {
  graph: Async<GraphResponse>;
  health: Async<{ status: string; falkordb: boolean }>;
  scan: Async<ScanEnv>;
  reach: Async<ReachEnv>;
  choke: Async<ChokeEnv>;
  plan: Async<PlanEnv>;
  sim: Async<SimEnv>;
  proposal: Async<ProposalEnv>;
  decide: Async<DecideEnv>;
  decisions: Async<DecisionsEnv>;
  view: View;
  /** all attack paths at depth 8 before any fix; the "before" side of a simulation */
  baseline: AttackPath[];
  traces: TraceRun[];
  scanDepth: number;
}

const initial: State = {
  graph: idle(), health: idle(), scan: idle(), reach: idle(), choke: idle(), plan: idle(), sim: idle(),
  proposal: idle(), decide: idle(), decisions: idle(), view: emptyView, baseline: [], traces: [], scanDepth: 4,
};

type Key = "graph" | "health" | "scan" | "reach" | "choke" | "plan" | "sim" | "proposal" | "decide" | "decisions";
type Action =
  | { type: "set"; key: Key; value: Async<any> }
  | { type: "view"; patch: Partial<View> }
  | { type: "baseline"; paths: AttackPath[] }
  | { type: "trace"; run: TraceRun }
  | { type: "depth"; depth: number }
  | { type: "clearFix" };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "set": return { ...state, [action.key]: action.value };
    case "view": return { ...state, view: { ...state.view, ...action.patch } };
    case "baseline": return { ...state, baseline: action.paths };
    case "trace": return { ...state, traces: [action.run, ...state.traces].slice(0, 60) };
    case "depth": return { ...state, scanDepth: action.depth };
    case "clearFix": return { ...state, sim: idle(), proposal: idle(), decide: idle() };
  }
}

export interface Actions {
  runScan(depth: number): Promise<void>;
  runReach(from: string, to: string): Promise<void>;
  runChoke(): Promise<void>;
  runPlan(budget: number): Promise<void>;
  runSimulate(edgeIds?: string[]): Promise<void>;
  runPropose(note?: string): Promise<void>;
  runDecide(action: "approve" | "reject", reason?: string): Promise<void>;
  loadDecisions(): Promise<void>;
  selectPath(index: number | null): void;
  focusEdge(edgeId: string | null): void;
  setSimSide(side: "before" | "after"): void;
  setDepth(depth: number): void;
  /** Apply a tool result that arrived from the chat as if the matching button had been pressed. */
  applyChatResult(tool: string, envelope: Envelope): void;
}

interface Ctx { state: State; layout: Layout | null; actions: Actions }
const StoreContext = createContext<Ctx | null>(null);

export function useStore(): Ctx {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore outside provider");
  return ctx;
}

const message = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const stateRef = useRef(state);
  stateRef.current = state;
  const traceId = useRef(0);

  const pushTrace = useCallback((label: string, entries: TraceEntry[], outcome?: TraceRun["outcome"]) => {
    dispatch({ type: "trace", run: { id: ++traceId.current, label, at: Date.now(), outcome, entries } });
  }, []);

  /** Run one API call with loading / ok / error handling and a trace entry. */
  const call = useCallback(async <E extends Envelope>(key: Key, label: string, fn: () => Promise<E>): Promise<E | null> => {
    dispatch({ type: "set", key, value: { status: "loading", data: stateRef.current[key].data, error: null } });
    try {
      const env = await fn();
      dispatch({ type: "set", key, value: { status: "ok", data: env, error: null } });
      pushTrace(label, env.trace, env.outcome);
      return env;
    } catch (e) {
      dispatch({ type: "set", key, value: { status: "error", data: null, error: message(e) } });
      return null;
    }
  }, [pushTrace]);

  const loadDecisions = useCallback(async () => { await call("decisions", "GET /api/decisions", () => api.decisions()); }, [call]);

  const handlers = useMemo(() => {
    const onScan = (env: ScanEnv) => {
      dispatch({ type: "view", patch: { source: "scan", paths: env.paths, planEdges: [], cutEdges: [], selected: null, focusEdge: null } });
      if (env.data.depth === 8) dispatch({ type: "baseline", paths: env.paths });
    };
    const onReach = (env: ReachEnv) =>
      dispatch({ type: "view", patch: { source: "reach", paths: env.paths, planEdges: [], cutEdges: [], selected: null, focusEdge: null } });
    const onPlan = (env: PlanEnv) => {
      const ids = env.data.plan ? env.data.plan.map((s) => s.edge_id) : [];
      dispatch({ type: "view", patch: { source: "plan", paths: env.paths, planEdges: ids, cutEdges: [], selected: null, focusEdge: null } });
      if (env.paths.length) dispatch({ type: "baseline", paths: env.paths });
      dispatch({ type: "clearFix" });
    };
    const onSim = (env: SimEnv) => {
      if (env.outcome !== "verified_fix") return;
      dispatch({ type: "view", patch: { source: "sim", paths: env.paths, planEdges: [], cutEdges: env.data.edge_ids, selected: null, simSide: "after" } });
    };
    return { onScan, onReach, onPlan, onSim };
  }, []);

  const actions = useMemo<Actions>(() => ({
    async runScan(depth) {
      const env = await call("scan", `POST /api/scan depth ${depth}`, () => api.scan(depth));
      if (env) handlers.onScan(env);
    },
    async runReach(from, to) {
      const env = await call("reach", "POST /api/reach", () => api.reach(from, to));
      if (env) handlers.onReach(env);
    },
    async runChoke() { await call("choke", "POST /api/choke", () => api.choke()); },
    async runPlan(budget) {
      const env = await call("plan", `POST /api/plan budget ${budget}`, () => api.plan(budget));
      if (env) handlers.onPlan(env);
    },
    async runSimulate(edgeIds) {
      const plan = stateRef.current.plan.data;
      const ids = edgeIds ?? plan?.data.plan.map((s) => s.edge_id) ?? [];
      if (!ids.length) return;
      // the "before" picture: every attack path at depth 8, fetched once if we do not have it yet
      if (!stateRef.current.baseline.length) {
        try {
          const before = await api.scan(8);
          pushTrace("POST /api/scan depth 8 (baseline for before/after)", before.trace, before.outcome);
          dispatch({ type: "baseline", paths: before.paths });
        } catch {
          // the simulation itself still runs; only the before/after toggle loses its "before" side
        }
      }
      const env = await call("sim", "POST /api/simulate", () => api.simulate(ids));
      if (env) handlers.onSim(env);
    },
    async runPropose(note) {
      const plan = stateRef.current.plan.data;
      const ids = plan?.data.plan.map((s) => s.edge_id) ?? [];
      if (!ids.length) return;
      const env = await call("proposal", "POST /api/propose", () => api.propose(ids, note));
      if (env) {
        dispatch({ type: "set", key: "decide", value: idle() });
        dispatch({ type: "view", patch: { planEdges: ids } });
      }
    },
    async runDecide(action, reason) {
      const proposal = stateRef.current.proposal.data;
      if (!proposal) return;
      const env = await call("decide", `POST /api/decision ${action}`, () => api.decide(proposal.data.run, action, reason));
      if (env) await loadDecisions();
    },
    loadDecisions,
    selectPath(index) { dispatch({ type: "view", patch: { selected: index, focusEdge: null } }); },
    focusEdge(edgeId) { dispatch({ type: "view", patch: { focusEdge: edgeId } }); },
    setSimSide(side) { dispatch({ type: "view", patch: { simSide: side } }); },
    setDepth(depth) { dispatch({ type: "depth", depth }); },
    applyChatResult(tool, env) {
      const label = `chat: ${tool}`;
      pushTrace(label, env.trace, env.outcome);
      switch (tool) {
        case "find_attack_paths":
          dispatch({ type: "set", key: "scan", value: { status: "ok", data: env, error: null } });
          handlers.onScan(env as ScanEnv);
          break;
        case "explain_reachability":
          dispatch({ type: "set", key: "reach", value: { status: "ok", data: env, error: null } });
          handlers.onReach(env as ReachEnv);
          break;
        case "rank_choke_edges":
          dispatch({ type: "set", key: "choke", value: { status: "ok", data: env, error: null } });
          break;
        case "plan_remediation":
          dispatch({ type: "set", key: "plan", value: { status: "ok", data: env, error: null } });
          handlers.onPlan(env as PlanEnv);
          break;
        case "simulate_fix":
          dispatch({ type: "set", key: "sim", value: { status: "ok", data: env, error: null } });
          handlers.onSim(env as SimEnv);
          break;
        case "propose_change":
          dispatch({ type: "set", key: "proposal", value: { status: "ok", data: env, error: null } });
          dispatch({ type: "set", key: "decide", value: idle() });
          break;
        case "recall_decisions":
          dispatch({ type: "set", key: "decisions", value: { status: "ok", data: env, error: null } });
          break;
      }
    },
  }), [call, handlers, loadDecisions, pushTrace]);

  // first load: graph, health and the decision memory
  useEffect(() => {
    dispatch({ type: "set", key: "graph", value: { status: "loading", data: null, error: null } });
    api.graph()
      .then((g) => {
        dispatch({ type: "set", key: "graph", value: { status: "ok", data: g, error: null } });
        pushTrace("GET /api/graph", g.trace);
      })
      .catch((e) => dispatch({ type: "set", key: "graph", value: { status: "error", data: null, error: message(e) } }));
    api.health()
      .then((h) => dispatch({ type: "set", key: "health", value: { status: "ok", data: h, error: null } }))
      .catch(() => dispatch({ type: "set", key: "health", value: { status: "error", data: null, error: "unreachable" } }));
    void loadDecisions();
  }, [loadDecisions, pushTrace]);

  const graphData = state.graph.data;
  const layout = useMemo(() => (graphData ? computeLayout(graphData.nodes, graphData.edges) : null), [graphData]);

  return <StoreContext.Provider value={{ state, layout, actions }}>{children}</StoreContext.Provider>;
}

/** The graph payload (nodes + edges) once loaded. */
export function useGraph(): GraphResponse | null {
  return useStore().state.graph.data;
}
