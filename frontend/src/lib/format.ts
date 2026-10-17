import type { Outcome } from "../types";

export interface OutcomeInfo { label: string; tone: "neutral" | "attack" | "fix" | "warn" | "muted"; hint: string }

/** Badge text, colour tone and a plain-language hint for each of the seven outcomes. */
export function outcomeInfo(outcome: Outcome): OutcomeInfo {
  switch (outcome) {
    case "answered_with_path":
      return { label: "Path found", tone: "attack", hint: "The graph returned a path; it is shown with the answer." };
    case "answered_from_memory":
      return { label: "From memory", tone: "neutral", hint: "Answered from decisions stored in the graph." };
    case "not_in_graph":
      return { label: "No modelled path", tone: "warn", hint: "No modelled path. This is not a statement that the asset is safe: the dependency may not be modelled." };
    case "unknown_asset":
      return { label: "Unknown asset", tone: "warn", hint: "That name is not in the graph, so nothing was searched." };
    case "verified_fix":
      return { label: "Verified fix", tone: "fix", hint: "Proven on a scratch copy of the graph." };
    case "proposed":
      return { label: "Proposed", tone: "neutral", hint: "A change record was written. A human must approve or reject it." };
    case "recorded":
      return { label: "Recorded", tone: "fix", hint: "Written to the graph." };
  }
}

export function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${d.getUTCDate()} ${months[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export type MdBlock =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "table"; header: string[]; rows: string[][] };

/** A tiny renderer for the ticket format the API produces: headings, bold lines and one table. */
export function markdownBlocks(md: string): MdBlock[] {
  const blocks: MdBlock[] = [];
  const lines = md.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    if (line.startsWith("#")) {
      blocks.push({ type: "heading", text: line.replace(/^#+\s*/, "") });
    } else if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].split("|").slice(1, -1).map((c) => c.trim());
        if (!cells.every((c) => /^-+$/.test(c))) rows.push(cells);
        i++;
      }
      i--;
      blocks.push({ type: "table", header: rows[0] ?? [], rows: rows.slice(1) });
    } else {
      blocks.push({ type: "paragraph", text: line });
    }
  }
  return blocks;
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
