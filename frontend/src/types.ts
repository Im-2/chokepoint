// The REST contract (section 8 of the build brief; mirrors app/models.py).

export type Outcome =
  | "answered_with_path"
  | "answered_from_memory"
  | "not_in_graph"
  | "unknown_asset"
  | "verified_fix"
  | "proposed"
  | "recorded";

export interface PathNode { id: string; name: string; kind: string }
export interface PathEdge { id: string; kind: string }
export interface AttackPath { nodes: PathNode[]; edges: PathEdge[] }

export interface TraceEntry { tool: string; query: string; args: Record<string, unknown>; ms: number; rows: number }

export interface Envelope<D = Record<string, any>> {
  outcome: Outcome;
  data: D;
  paths: AttackPath[];
  trace: TraceEntry[];
  notes: string;
}

export type AssetKind = "user" | "service_account" | "role" | "group" | "host" | "secret" | "datastore" | "vault";

export interface GraphNode { id: string; name: string; kind: AssetKind; entry: boolean; crown: boolean; owner_team: string }
export interface GraphEdge { id: string; source: string; target: string; kind: string; cost: number; disruption: number }
export interface GraphResponse { nodes: GraphNode[]; edges: GraphEdge[]; trace: TraceEntry[] }

export interface ChokeRow {
  edge_id: string; kind: string; disruption: number; fix_text: string;
  from: string; to: string; paths_through: number; score: number;
}
export interface PlanStep {
  edge_id: string; from: string; to: string; kind: string; fix_text: string; disruption: number; paths_cut: number;
}
export interface PlanData {
  budget: number; method: string; plan: PlanStep[]; paths_total: number; paths_cut: number;
  paths_remaining: number; total_disruption: number;
  excluded_by_memory: { edge_id: string; reason: string; at: string; on_attack_path: boolean }[];
}
export interface SimulationData {
  edge_ids: string[]; paths_before: number; paths_after: number; paths_cut: number; fully_cut: boolean;
  remaining_via: string[][]; scratch_graph: string; scratch_deleted: boolean;
}
export interface ProposalData {
  run: string; status: string; owner_teams: string[]; ticket_markdown: string; config_diff: string;
  decisions: { decision_id: string; edge_id: string }[];
  owners: { edge_id: string; team: string; lead: string }[];
}
export interface DecisionRecord {
  decision_id: string; edge_id: string; status: "proposed" | "approved" | "rejected"; reason: string;
  at: string; run: string; assets: string[];
}

// One entry in the session trace log (a tool call with its server-reported queries).
export interface TraceRun { id: number; label: string; at: number; outcome?: Outcome; entries: TraceEntry[] }

// Server-sent events from POST /api/chat
export type ChatEvent =
  | { event: "tool_call"; tool: string; args: Record<string, unknown> }
  | { event: "tool_result"; tool: string; outcome: Outcome; envelope: Envelope }
  | { event: "provider_error"; provider: string; error: string }
  | { event: "final"; text: string; checked: boolean; reason: string; mode: string };
