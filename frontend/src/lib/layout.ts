import type { GraphEdge, GraphNode } from "../types";

export interface Layout {
  positions: Record<string, { x: number; y: number }>;
  /** Assets that lie on some route from an entry point to a crown jewel (used only for layout). */
  relevant: Set<string>;
}

const COLUMN_GAP = 230;
const ROW_GAP = 74;
const KIND_ORDER = ["user", "secret", "host", "group", "service_account", "role", "datastore", "vault"];

function reach(start: Iterable<string>, adjacency: Map<string, string[]>): Set<string> {
  const seen = new Set<string>(start);
  const queue = [...seen];
  while (queue.length) {
    const id = queue.shift() as string;
    for (const next of adjacency.get(id) ?? []) {
      if (!seen.has(next)) {
        seen.add(next);
        queue.push(next);
      }
    }
  }
  return seen;
}

// Small deterministic generator so the layout never changes between visits.
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Layered layout: entry points on the left, crown jewels on the right, the assets between them in
 * columns by distance from an entry. Everything else (ordinary assets) is spread in two bands above and
 * below, so the interesting structure stays readable.
 */
export function computeLayout(nodes: GraphNode[], edges: GraphEdge[]): Layout {
  const forward = new Map<string, string[]>();
  const backward = new Map<string, string[]>();
  for (const e of edges) {
    forward.set(e.source, [...(forward.get(e.source) ?? []), e.target]);
    backward.set(e.target, [...(backward.get(e.target) ?? []), e.source]);
  }
  const entries = nodes.filter((n) => n.entry).map((n) => n.id);
  const crowns = nodes.filter((n) => n.crown).map((n) => n.id);
  const fromEntries = reach(entries, forward);
  const toCrowns = reach(crowns, backward);
  const relevant = new Set(nodes.filter((n) => fromEntries.has(n.id) && toCrowns.has(n.id)).map((n) => n.id));

  // distance from an entry, inside the relevant sub-graph
  const distance = new Map<string, number>(entries.map((id) => [id, 0]));
  const queue = [...entries];
  while (queue.length) {
    const id = queue.shift() as string;
    for (const next of forward.get(id) ?? []) {
      if (relevant.has(next) && !distance.has(next)) {
        distance.set(next, (distance.get(id) ?? 0) + 1);
        queue.push(next);
      }
    }
  }
  const crownSet = new Set(crowns);
  const maxLayer = Math.max(0, ...[...distance.entries()].filter(([id]) => !crownSet.has(id)).map(([, d]) => d));
  const columns = new Map<number, GraphNode[]>();
  for (const n of nodes) {
    if (!relevant.has(n.id)) continue;
    const layer = n.crown ? maxLayer + 1 : (distance.get(n.id) ?? 0);
    columns.set(layer, [...(columns.get(layer) ?? []), n]);
  }

  const positions: Layout["positions"] = {};
  let tallest = 0;
  for (const [layer, members] of columns) {
    members.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || a.name.localeCompare(b.name));
    tallest = Math.max(tallest, members.length);
    members.forEach((n, i) => {
      positions[n.id] = { x: layer * COLUMN_GAP, y: (i - (members.length - 1) / 2) * ROW_GAP };
    });
  }

  const width = (maxLayer + 1) * COLUMN_GAP;
  const halfHeight = (tallest * ROW_GAP) / 2 + 140;
  const rand = mulberry32(7);
  const rest = nodes.filter((n) => !relevant.has(n.id)).sort((a, b) => a.id.localeCompare(b.id));
  const perBand = Math.ceil(rest.length / 2);
  const perRow = Math.max(6, Math.ceil((width + 500) / 95));
  rest.forEach((n, i) => {
    const band = i < perBand ? -1 : 1;
    const idx = i < perBand ? i : i - perBand;
    const row = Math.floor(idx / perRow);
    const col = idx % perRow;
    positions[n.id] = {
      x: -250 + (col / perRow) * (width + 500) + (rand() - 0.5) * 36,
      y: band * (halfHeight + row * 84 + rand() * 24),
    };
  });
  return { positions, relevant };
}
