import { useEffect, useMemo, useRef, useState } from "react";
import type { Collection, Core, ElementDefinition, EventObject, StylesheetJson } from "cytoscape";
import { useGraph, useStore } from "../store";
import { effectiveView } from "../lib/graphView";
import { Legend } from "./Legend";
import { ErrorNote, Skeleton } from "./ui";

const SHAPES: Record<string, string> = {
  user: "ellipse", service_account: "diamond", role: "round-rectangle", group: "hexagon",
  host: "rectangle", secret: "tag", datastore: "barrel", vault: "octagon",
};

const STYLE: StylesheetJson = [
  { selector: "node", style: {
    width: 30, height: 30, "background-color": "#2a2a2a", "border-width": 1.5, "border-color": "#6b6b6b",
    label: "data(label)", "font-family": "Inter Variable, Inter, system-ui, sans-serif", "font-size": 13, color: "#cfcfcf",
    "text-valign": "bottom", "text-margin-y": 6, "text-outline-color": "#050505", "text-outline-width": 2,
    "min-zoomed-font-size": 6, shape: "ellipse" } },
  ...Object.entries(SHAPES).map(([kind, shape]) => ({ selector: `node[kind = "${kind}"]`, style: { shape } as any })),
  { selector: "node.noise", style: { width: 12, height: 12, opacity: 0.38, "text-opacity": 0, "border-width": 1, "border-color": "#444" } },
  { selector: "node.entry", style: { "border-color": "#ff4a2b", "border-width": 3, "background-color": "#3a1510",
    "underlay-color": "#ff4a2b", "underlay-opacity": 0.22, "underlay-padding": 7 } },
  { selector: "node.crown", style: { shape: "star", width: 54, height: 54, "background-color": "#fafaf5", "border-color": "#fafaf5",
    "font-weight": 700, color: "#fafaf5", "underlay-color": "#fafaf5", "underlay-opacity": 0.14, "underlay-padding": 9 } },
  { selector: "edge", style: {
    width: 1.4, "line-color": "#4a4a4a", "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": "#4a4a4a",
    "arrow-scale": 0.7, opacity: 0.85 } },
  { selector: "edge.noise", style: { opacity: 0.1, width: 1 } },
  { selector: ".dim", style: { opacity: 0.08, "text-opacity": 0 } },
  { selector: "edge.ghost", style: { "line-color": "#ff4a2b", "target-arrow-color": "#ff4a2b", "line-style": "dotted", opacity: 0.3, width: 2 } },
  { selector: "node.hl", style: { opacity: 1, "text-opacity": 1, "border-color": "#ff4a2b", "background-color": "#4a1a12", "z-index": 20, width: 34, height: 34 } },
  { selector: "node.hl.crown", style: { width: 56, height: 56, "background-color": "#fafaf5" } },
  { selector: "node.ctx", style: { opacity: 1, "text-opacity": 1, "z-index": 15 } },
  { selector: "edge.hl", style: { "line-color": "#ff4a2b", "target-arrow-color": "#ff4a2b", width: 3.2, opacity: 1, "z-index": 20 } },
  { selector: "edge.plan", style: { "line-color": "#3ddbc0", "target-arrow-color": "#3ddbc0", "line-style": "dashed", "line-dash-pattern": [6, 5], width: 3.4, opacity: 1, "z-index": 25 } },
  { selector: "edge.cut", style: { "line-color": "#3ddbc0", "target-arrow-shape": "none", "line-style": "dashed", "line-dash-pattern": [3, 6], width: 3, opacity: 1,
    label: "✕", "font-size": 18, color: "#3ddbc0", "text-background-color": "#050505", "text-background-opacity": 1, "text-background-padding": "2px", "z-index": 25 } },
  { selector: "edge.focus", style: { "line-color": "#ffffff", "target-arrow-color": "#ffffff", width: 4.5, opacity: 1, "z-index": 30,
    "underlay-color": "#ffffff", "underlay-opacity": 0.2, "underlay-padding": 5 } },
];

/** Frame some elements without ever zooming in absurdly far on a single edge or node. */
function fitTo(cy: Core, eles: Collection, padding: number, animate: boolean, maxZoom = 1.35) {
  if (eles.empty()) return;
  const bb = eles.boundingBox();
  const w = cy.width();
  const h = cy.height();
  const zoom = Math.max(cy.minZoom(), Math.min(maxZoom, (w - 2 * padding) / Math.max(bb.w, 1), (h - 2 * padding) / Math.max(bb.h, 1)));
  const pan = { x: w / 2 - zoom * (bb.x1 + bb.w / 2), y: h / 2 - zoom * (bb.y1 + bb.h / 2) };
  if (animate) cy.animate({ zoom, pan }, { duration: 450, easing: "ease-out-cubic" });
  else { cy.zoom(zoom); cy.pan(pan); }
}

interface Tip { x: number; y: number; title: string; lines: string[] }

export function GraphCanvas() {
  const { state, layout } = useStore();
  const graph = useGraph();
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);

  const eff = useMemo(
    () => effectiveView(state.view, state.baseline),
    [state.view, state.baseline],
  );
  const focusEdge = state.view.focusEdge;

  // build the Cytoscape instance once the graph and its layout exist (library is loaded on demand)
  useEffect(() => {
    if (!graph || !layout || !host.current) return;
    let cancelled = false;
    void (async () => {
      try {
        const cytoscape = (await import("cytoscape")).default;
        if (cancelled || !host.current) return;
        const elements: ElementDefinition[] = [
          ...graph.nodes.map((n) => ({
            data: { id: n.id, label: n.name, kind: n.kind, owner: n.owner_team, entry: n.entry, crown: n.crown },
            position: layout.positions[n.id],
            classes: [!layout.relevant.has(n.id) ? "noise" : "", n.entry ? "entry" : "", n.crown ? "crown" : ""].join(" ").trim(),
          })),
          ...graph.edges.map((e) => ({
            data: { id: e.id, source: e.source, target: e.target, kind: e.kind, cost: e.cost, disruption: e.disruption },
            classes: !layout.relevant.has(e.source) || !layout.relevant.has(e.target) ? "noise" : "",
          })),
        ];
        const cy = cytoscape({
          container: host.current, elements, style: STYLE, layout: { name: "preset" },
          minZoom: 0.12, maxZoom: 3, wheelSensitivity: 0.25, boxSelectionEnabled: false, autounselectify: true,
        });
        cyRef.current = cy;
        fitTo(cy, cy.nodes().not(".noise"), 40, false, 1.2);

        const showNode = (evt: EventObject) => {
          const n = evt.target;
          const p = n.renderedPosition();
          n.addClass("ctx");
          setTip({ x: p.x, y: p.y, title: n.data("label"), lines: [
            `kind: ${n.data("kind").replace("_", " ")}`, `owner: ${n.data("owner")}`,
            n.data("entry") ? "entry point (attacker can start here)" : "", n.data("crown") ? "crown jewel" : "",
          ].filter(Boolean) });
        };
        cy.on("mouseover", "node", showNode);
        cy.on("mouseout", "node", (evt) => { evt.target.removeClass("ctx"); setTip(null); });
        cy.on("mouseover", "edge", (evt) => {
          const e = evt.target;
          const pos = evt.renderedPosition ?? e.midpoint();
          setTip({ x: pos.x, y: pos.y, title: `${e.source().data("label")} → ${e.target().data("label")}`, lines: [
            `${e.data("kind").replace("_", " ")} · edge ${e.id()}`, `attacker cost ${e.data("cost")} · disruption ${e.data("disruption")}/10`] });
        });
        cy.on("mouseout", "edge", () => setTip(null));
        cy.on("pan zoom drag", () => setTip(null));
        setReady(true);
      } catch {
        if (!cancelled) setFailed("The graph view could not load. Reload the page to try again.");
      }
    })();
    return () => {
      cancelled = true;
      cyRef.current?.destroy();
      cyRef.current = null;
      setReady(false);
    };
  }, [graph, layout]);

  // keep the canvas sized to its container
  useEffect(() => {
    if (!ready || !host.current) return;
    const ro = new ResizeObserver(() => cyRef.current?.resize());
    ro.observe(host.current);
    return () => ro.disconnect();
  }, [ready]);

  // restyle whenever what we should show changes
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !ready) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    cy.batch(() => {
      cy.elements().removeClass("dim hl ctx plan cut ghost focus");
      const hlNodes = new Set<string>();
      const hlEdges = new Set<string>();
      for (const p of eff.paths) {
        p.nodes.forEach((n) => hlNodes.add(n.id));
        p.edges.forEach((e) => hlEdges.add(e.id));
      }
      const marked = new Set<string>([...eff.cutEdges, ...eff.planEdges, ...(focusEdge ? [focusEdge] : [])]);
      const active = hlEdges.size > 0 || marked.size > 0 || eff.ghostPaths.length > 0;
      if (!active) return;
      cy.elements().addClass("dim");
      const reveal = (ele: ReturnType<Core["getElementById"]>, cls: string) => { ele.removeClass("dim").addClass(cls); };
      for (const id of hlNodes) reveal(cy.getElementById(id), "hl");
      for (const id of hlEdges) reveal(cy.getElementById(id), "hl");
      for (const p of eff.ghostPaths) {
        p.edges.forEach((e) => { const el = cy.getElementById(e.id); if (!hlEdges.has(e.id)) reveal(el, "ghost"); });
        p.nodes.forEach((n) => cy.getElementById(n.id).removeClass("dim"));
      }
      const mark = (ids: string[], cls: string) => ids.forEach((id) => {
        const el = cy.getElementById(id);
        if (el.empty()) return;
        reveal(el, cls);
        el.connectedNodes().removeClass("dim").addClass("ctx");
      });
      mark(eff.planEdges, "plan");
      mark(eff.cutEdges, "cut");
      if (focusEdge) mark([focusEdge], "focus");
    });
    // frame whatever is highlighted (or the interesting part of the graph when nothing is)
    const target = cy.elements(".hl, .plan, .cut, .focus, .ghost");
    const eles = target.empty() ? cy.nodes().not(".noise") : target;
    fitTo(cy, eles, 60, !reduced);
  }, [eff, focusEdge, ready]);

  const zoom = (factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };
  const fit = () => {
    const cy = cyRef.current;
    if (cy) fitTo(cy, cy.nodes().not(".noise"), 40, true, 1.2);
  };

  if (state.graph.status === "error") {
    return <div className="canvas canvas--state"><ErrorNote message={state.graph.error ?? "The graph could not be loaded."} onRetry={() => window.location.reload()} /></div>;
  }

  return (
    <div className="canvas">
      <div ref={host} className="canvas__cy" role="img"
        aria-label={`Attack graph: ${graph?.nodes.length ?? 0} assets and ${graph?.edges.length ?? 0} connections. Highlighted paths are listed in the side panel.`} />
      {!ready && !failed && (
        <div className="canvas__overlay"><div className="canvas__skeleton"><Skeleton lines={5} height={16} /><span className="hint">Loading the graph…</span></div></div>
      )}
      {failed && <div className="canvas__overlay"><ErrorNote message={failed} onRetry={() => window.location.reload()} /></div>}
      {tip && (
        <div className="tooltip" style={{ left: Math.min(tip.x + 14, (host.current?.clientWidth ?? 600) - 230), top: Math.max(tip.y - 12, 8) }}>
          <strong className="mono">{tip.title}</strong>
          {tip.lines.map((l) => <span key={l}>{l}</span>)}
        </div>
      )}
      <div className="canvas__controls" aria-label="Zoom controls">
        <button className="btn btn--small" onClick={() => zoom(1.3)} aria-label="Zoom in">+</button>
        <button className="btn btn--small" onClick={() => zoom(1 / 1.3)} aria-label="Zoom out">−</button>
        <button className="btn btn--small" onClick={fit} aria-label="Fit to the attack-relevant part of the graph">Fit</button>
      </div>
      <Legend />
    </div>
  );
}
