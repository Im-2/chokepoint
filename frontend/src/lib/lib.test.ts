import { describe, expect, it } from "vitest";
import { computeLayout } from "./layout";
import { parseSseChunk } from "./sse";
import { outcomeInfo, shortDate, markdownBlocks } from "./format";
import type { GraphEdge, GraphNode } from "../types";

const node = (id: string, extra: Partial<GraphNode> = {}): GraphNode =>
  ({ id, name: id, kind: "host", entry: false, crown: false, owner_team: "t", ...extra });
const edge = (id: string, source: string, target: string): GraphEdge =>
  ({ id, source, target, kind: "network", cost: 1, disruption: 1 });

describe("computeLayout", () => {
  const nodes = [node("e", { entry: true }), node("m"), node("c", { crown: true }), node("x1"), node("x2")];
  const edges = [edge("1", "e", "m"), edge("2", "m", "c"), edge("3", "e", "x1"), edge("4", "x1", "x2")];

  it("marks only nodes on an entry-to-crown route as relevant", () => {
    expect([...computeLayout(nodes, edges).relevant].sort()).toEqual(["c", "e", "m"]);
  });
  it("puts entries left of crown jewels and is deterministic", () => {
    const a = computeLayout(nodes, edges);
    expect(a.positions.e.x).toBeLessThan(a.positions.c.x);
    expect(computeLayout(nodes, edges)).toEqual(a);
  });
  it("places every node", () => {
    expect(Object.keys(computeLayout(nodes, edges).positions)).toHaveLength(nodes.length);
  });
});

describe("parseSseChunk", () => {
  it("returns complete events and keeps the unfinished tail", () => {
    const text = 'event: tool_call\ndata: {"event":"tool_call","tool":"a","args":{}}\n\nevent: final\ndata: {"event":"fin';
    const { events, rest } = parseSseChunk(text);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ event: "tool_call", tool: "a" });
    expect(rest).toContain('"event":"fin');
  });
  it("skips malformed events", () => {
    expect(parseSseChunk("data: {not json}\n\n").events).toEqual([]);
  });
});

describe("format helpers", () => {
  it("describes all seven outcomes", () => {
    const outcomes = ["answered_with_path", "answered_from_memory", "not_in_graph", "unknown_asset",
      "verified_fix", "proposed", "recorded"] as const;
    for (const o of outcomes) expect(outcomeInfo(o).label.length).toBeGreaterThan(2);
    expect(outcomeInfo("not_in_graph").hint).toMatch(/not.*safe/i);
  });
  it("formats ISO dates", () => {
    expect(shortDate("2026-09-02T15:05:00Z")).toBe("2 Sep 2026");
  });
  it("splits ticket markdown into blocks", () => {
    const blocks = markdownBlocks("# Title\n\n**Owning team(s):** platform-eng\n\n| A | B |\n|---|---|\n| 1 | 2 |");
    expect(blocks.map((b) => b.type)).toEqual(["heading", "paragraph", "table"]);
  });
});

import { effectiveView } from "./graphView";
import type { AttackPath } from "../types";

const path = (...edgeIds: string[]): AttackPath => ({
  nodes: [], edges: edgeIds.map((id) => ({ id, kind: "network" })),
});

describe("effectiveView (before/after toggle)", () => {
  const baseline = [path("e1", "e2"), path("e3", "e2"), path("e4", "e5")];
  const view = { source: "sim" as const, paths: [path("e4", "e5")], planEdges: [], cutEdges: ["e2"], selected: null, simSide: "after" as const };

  it("after: shows remaining paths, cut edges, and the paths the fix removed as ghosts", () => {
    const v = effectiveView(view, baseline);
    expect(v.paths).toHaveLength(1);
    expect(v.cutEdges).toEqual(["e2"]);
    expect(v.ghostPaths).toHaveLength(2);
  });
  it("before: shows every original path and previews the edges to be cut", () => {
    const v = effectiveView({ ...view, simSide: "before" }, baseline);
    expect(v.paths).toHaveLength(3);
    expect(v.cutEdges).toEqual([]);
    expect(v.planEdges).toEqual(["e2"]);
  });
  it("a selected path narrows the highlight to that path", () => {
    const v = effectiveView({ ...view, source: "scan", paths: baseline, cutEdges: [], selected: 1 }, baseline);
    expect(v.paths).toEqual([baseline[1]]);
  });
});
