import type { ChatEvent } from "../types";

/** Split a buffer of server-sent events into complete events plus the unfinished rest. */
export function parseSseChunk(buffer: string): { events: ChatEvent[]; rest: string } {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: ChatEvent[] = [];
  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data: "))
      .map((line) => line.slice(6))
      .join("\n");
    if (!data) continue;
    try {
      events.push(JSON.parse(data) as ChatEvent);
    } catch {
      // a malformed event is skipped rather than breaking the whole stream
    }
  }
  return { events, rest };
}
