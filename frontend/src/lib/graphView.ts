import type { AttackPath } from "../types";

export interface ViewInput {
  source: "none" | "scan" | "reach" | "plan" | "sim";
  paths: AttackPath[];
  planEdges: string[];
  cutEdges: string[];
  selected: number | null;
  simSide: "before" | "after";
}

export interface EffectiveView {
  /** paths drawn in red */
  paths: AttackPath[];
  /** edges drawn as removed (dashed teal with a cross) */
  cutEdges: string[];
  /** edges drawn as proposed fixes (dashed teal, not yet applied) */
  planEdges: string[];
  /** paths that existed before a fix and are gone after it (drawn faint) */
  ghostPaths: AttackPath[];
}

export const pathKey = (p: AttackPath) => p.edges.map((e) => e.id).join(">");

/** Resolve what the canvas shows, including the before/after toggle of a simulation. */
export function effectiveView(view: ViewInput, baseline: AttackPath[]): EffectiveView {
  let result: EffectiveView;
  if (view.source === "sim") {
    if (view.simSide === "before") {
      result = { paths: baseline.length ? baseline : view.paths, cutEdges: [], planEdges: view.cutEdges, ghostPaths: [] };
    } else {
      const remaining = new Set(view.paths.map(pathKey));
      result = { paths: view.paths, cutEdges: view.cutEdges, planEdges: [], ghostPaths: baseline.filter((p) => !remaining.has(pathKey(p))) };
    }
  } else {
    result = { paths: view.paths, cutEdges: view.cutEdges, planEdges: view.planEdges, ghostPaths: [] };
  }
  if (view.selected !== null && result.paths[view.selected]) {
    result = { ...result, paths: [result.paths[view.selected]] };
  }
  return result;
}
