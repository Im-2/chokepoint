// Thin typed client over the REST contract. It never calls /api/reset or /mcp.
import { parseSseChunk } from "./lib/sse";
import type {
  ChatEvent, DecisionRecord, Envelope, GraphResponse, PlanData, ProposalData, SimulationData, ChokeRow,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Cannot reach the Chokepoint API. Check your connection and try again.");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string; falkordb: boolean }>("/healthz"),
  graph: () => request<GraphResponse>("/api/graph"),
  scan: (depth: number) => post<Envelope<{ depth: number; count: number; shortest_hops: number; truncated: boolean }>>("/api/scan", { depth }),
  reach: (from_name: string, to_name: string) =>
    post<Envelope<{ from: string; to: string; hops: number; attacker_cost: number; unknown?: string[] }>>("/api/reach", { from_name, to_name }),
  choke: () =>
    post<Envelope<{ depth: number; total_paths: number; ranked: ChokeRow[]; naive_most_paths: ChokeRow }>>("/api/choke", { depth: 8, limit: 15 }),
  plan: (budget: number) => post<Envelope<PlanData>>("/api/plan", { budget }),
  simulate: (edge_ids: string[]) => post<Envelope<SimulationData>>("/api/simulate", { edge_ids }),
  propose: (edge_ids: string[], plan_note?: string) => post<Envelope<ProposalData>>("/api/propose", { edge_ids, plan_note }),
  decide: (decision_id: string, action: "approve" | "reject", reason?: string) =>
    post<Envelope<{ status: string; reason: string; decided: { decision_id: string; edge_id: string }[] }>>(
      "/api/decision", { decision_id, action, reason }),
  decisions: (asset_name?: string) =>
    request<Envelope<{ decisions: DecisionRecord[] }>>(
      `/api/decisions${asset_name ? `?asset_name=${encodeURIComponent(asset_name)}` : ""}`),
};

/** POST /api/chat and stream its server-sent events. Rejects with ApiError(429) when rate limited. */
export async function chatStream(
  message: string,
  history: { role: "user" | "assistant"; content: string }[],
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ApiError(0, "Cannot reach the Chokepoint API.");
  }
  if (!response.ok || !response.body) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, String(detail));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseSseChunk(buffer);
    buffer = rest;
    events.forEach(onEvent);
  }
  const tail = parseSseChunk(buffer + "\n\n");
  tail.events.forEach(onEvent);
}
