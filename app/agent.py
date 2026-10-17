"""The agent: a no-LLM router, an optional free-tier LLM loop, and an answer checker.

Both modes call tools through MCP (in-memory transport), so the agent only sees the tools the
MCP server lists. The model never writes Cypher and cannot approve or reject anything.

Flow of run_chat():
  1. If an LLM is configured (and CHAT_ENABLED), let it pick tools. Its final sentence is run
     through check_answer(); if the checker rejects it, we return the templated sentence instead.
  2. If no LLM is configured, it is rate limited, or it fails, the deterministic router answers
     with templated sentences built from tool rows.
Events yielded: tool_call, tool_result, provider_error (LLM failed, moving on), final.
"""
import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass

from mcp import Client
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from app import config
from app.mcp_server import build_server

MAX_TOOL_CALLS = 6
HUMAN_ONLY = {"record_decision"}  # the agent can propose, but never approve or reject
KEBAB = re.compile(r"(?<![a-z0-9-])[a-z0-9]+(?:-[a-z0-9]+)+(?![a-z0-9-])")
EDGE_ID = re.compile(r"\be\d{3}\b")

SYSTEM_PROMPT = (
    "You are Chokepoint, a cloud-security assistant over a graph of assets and attack paths. "
    "Use the tools; you never write queries. After the tool results, answer in ONE short sentence. "
    "Quote asset names, edge ids and numbers exactly as the tool returned them, and use no "
    "hyphenated words except asset names. "
    "No path means 'no modelled path', never that something is safe. "
    "Say a fix is verified only if simulate_fix ran. "
    "You cannot approve or reject changes; only humans do. "
    "For 'can X reach Y' use explain_reachability. For 'is X safe, secure or exposed' call "
    "explain_reachability with only from_name (it then checks every crown jewel) and report whether a "
    "path is modelled; never answer yes or no about safety. Unknown names: say they are unknown. "
    "To simulate or propose 'the plan' or 'the fix', never ask the user for edge ids: first call "
    "plan_remediation, then call simulate_fix (or propose_change) with the edge_ids of that plan."
)


# ================================================================ answer checker

@dataclass
class Check:
    ok: bool
    reason: str = ""


def _numbers_in(obj, found):
    """Collect every number in a result, plus the length of every list (counts are legitimate)."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if float(obj).is_integer():
            found.add(int(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, found)
    elif isinstance(obj, list):
        found.add(len(obj))
        for v in obj:
            _numbers_in(v, found)


def _normalise(sentence: str) -> str:
    """Lower-case, fold look-alike characters (full-width letters etc.) and turn every Unicode
    dash or hyphen into '-', so a name written with a non-breaking hyphen cannot dodge the checks."""
    text = unicodedata.normalize("NFKC", sentence).lower()
    return re.sub("[‐-―−﹘﹣－]", "-", text)


def check_answer(sentence: str, envelopes: list[dict]) -> Check:
    """Reject sentences that invent names or numbers, say 'safe', claim impact when nothing was
    found, claim a fix is verified without simulate_fix, or claim the agent approved something.
    Any hyphenated token counts as an asset name, so ordinary hyphenated words are rejected too:
    that errs on the safe side (the caller then falls back to the templated sentence)."""
    corpus_obj = [{k: e[k] for k in ("outcome", "data", "paths", "notes")} for e in envelopes]
    corpus = json.dumps(corpus_obj)
    text = _normalise(sentence)

    for name in KEBAB.findall(text):
        if not re.search(rf"(?<![a-z0-9-]){re.escape(name)}(?![a-z0-9-])", corpus):
            return Check(False, f"'{name}' does not appear in the tool results")
    for edge_id in EDGE_ID.findall(text):
        if edge_id not in corpus:
            return Check(False, f"edge id '{edge_id}' does not appear in the tool results")

    allowed = set(range(0, 11))
    _numbers_in(corpus_obj, allowed)
    stripped = EDGE_ID.sub(" ", KEBAB.sub(" ", text))
    for number in re.findall(r"\d+", stripped):
        if int(number) not in allowed:
            return Check(False, f"the number {number} does not appear in the tool results")

    for match in re.finditer(r"\bsafe\b", text):
        before = text[max(0, match.start() - 40):match.start()]
        if not re.search(r"\b(not|never|no)\b|n't", before):
            return Check(False, "the sentence calls something safe")

    if envelopes and all(e["outcome"] in ("not_in_graph", "unknown_asset") for e in envelopes):
        if re.search(r"\b(cut|cuts|reduc\w*|eliminat\w*|fix(?:ed|es)?|block\w*|prevent\w*|mitigat\w*)\b", text):
            return Check(False, "the sentence claims an impact but the tools found no paths")

    if any(e["outcome"] == "not_in_graph" for e in envelopes) and re.search(
            r"\b(cannot|can't|can not|unable to|unreachable|impossible|not reachable|isn't reachable|"
            r"no way to|no access)\b", text):
        return Check(False, "'no modelled path' does not mean the asset cannot reach it")

    if envelopes and re.search(r"\bno (?:modelled|modeled) (?:attack )?path", text) and not any(
            e["outcome"] == "not_in_graph" for e in envelopes):
        return Check(False, "the sentence says no path is modelled but the tools did not report that")

    if re.search(r"\bverif\w*", text) and not any(e["outcome"] == "verified_fix" for e in envelopes):
        return Check(False, "the sentence says verified but simulate_fix did not run")
    if re.search(r"\bi (?:have )?(?:approved|rejected)\b", text):
        return Check(False, "the agent cannot approve or reject changes")
    return Check(True)


# ================================================================ templated sentences

def _route(path):
    return " -> ".join(n["name"] for n in path["nodes"])


def summarize(tool: str, env: dict) -> str:
    """One deterministic sentence built only from the tool's rows."""
    outcome, d = env["outcome"], env["data"]
    if outcome == "unknown_asset":
        return f"I don't know the asset {', '.join(d['unknown'])}; no search was run."
    if outcome == "not_in_graph":
        return env["notes"]
    if tool == "find_attack_paths":
        shortest = env["paths"][0]
        return (f"Found {d['count']} attack path(s) within {d['depth']} hops; the shortest is "
                f"{d['shortest_hops']} hops: {_route(shortest)}.")
    if tool == "explain_reachability":
        return (f"{d['from']} can reach {d['to']} in {d['hops']} hops (attacker cost "
                f"{int(d['attacker_cost'])}): {_route(env['paths'][0])}.")
    if tool == "rank_choke_edges":
        best, naive = d["ranked"][0], d["naive_most_paths"]
        text = (f"Best fix by paths cut per disruption: {best['fix_text']} (edge {best['edge_id']}, on "
                f"{best['paths_through']} of {d['total_paths']} paths, disruption {best['disruption']}).")
        if naive["edge_id"] != best["edge_id"]:
            text += (f" A plain most-paths ranking would pick {naive['edge_id']} ({naive['paths_through']} paths) "
                     f"but its disruption is {naive['disruption']}.")
        return text
    if tool == "rank_load_bearing_assets":
        return "Most central assets by betweenness: " + ", ".join(a["name"] for a in d["ranked"][:5]) + "."
    if tool == "plan_remediation":
        steps = "; ".join(f"{s['fix_text']} (edge {s['edge_id']}, disruption {s['disruption']}, cuts {s['paths_cut']})"
                          for s in d["plan"])
        text = (f"Greedy plan: {steps}. This cuts {d['paths_cut']} of {d['paths_total']} paths"
                f" and leaves {d['paths_remaining']}.")
        if d["excluded_by_memory"] and any(e["on_attack_path"] for e in d["excluded_by_memory"]):
            skipped = ", ".join(e["edge_id"] for e in d["excluded_by_memory"] if e["on_attack_path"])
            text += f" Skipped {skipped}, rejected earlier."
        return text
    if tool == "simulate_fix":
        return (f"Simulated on a scratch copy: {d['paths_before']} attack paths before, "
                f"{d['paths_after']} after removing {', '.join(d['edge_ids'])}.")
    if tool == "propose_change":
        return (f"Proposed change {d['run']} for owner team(s) {', '.join(d['owner_teams'])}; "
                "it is waiting for a human to approve or reject it.")
    if tool == "recall_decisions":
        lines = [f"{x['edge_id']} {x['status']} on {x['at'][:10]}: {x['reason']}" for x in d["decisions"][:5]]
        return f"{len(d['decisions'])} past decision(s): " + "; ".join(lines) + "."
    return env["notes"] or "Done."


HELP_TEXT = ("I can scan for attack paths (say a depth), tell you whether one asset can reach another, "
             "rank choke edges, plan a fix, simulate it, propose a change, or recall past decisions.")


# ================================================================ no-LLM router

def parse_request(message: str) -> dict:
    """Keyword/regex intent routing. Returns {"kind": ..., ...args}."""
    m = message.lower()
    names = KEBAB.findall(m)
    edge_ids = list(dict.fromkeys(EDGE_ID.findall(m)))
    depth = re.search(r"depth\s*(?:of\s*)?(\d)|(\d)\s*hops?", m)
    budget = re.search(r"budget\s*(?:of\s*)?(\d)", m)

    if re.search(r"\b(approve|reject|accept|deny)\b", m):
        return {"kind": "refuse_decision"}
    if len(names) >= 2 and re.search(r"reach|access|get to|path|why|from", m):
        return {"kind": "reach", "from_name": names[0], "to_name": names[1]}
    if len(names) == 1 and re.search(r"\b(safe|secure|exposed|exposure|risk\w*|vulnerable|compromis\w*|dangerous)\b", m):
        return {"kind": "exposure", "from_name": names[0]}
    if re.search(r"histor|decid|decision|memory|remember|rejected before|past|previous", m):
        return {"kind": "recall", "asset_name": names[0] if names else None}
    if re.search(r"simulat|prove|verify|what if|test the fix", m):
        return {"kind": "simulate", "edge_ids": edge_ids}
    if re.search(r"propos|ticket|change request|file a", m):
        return {"kind": "propose", "edge_ids": edge_ids}
    if re.search(r"\bplan\b|remediat|recommend|how (?:do|can|should) we|what should|fix", m):
        return {"kind": "plan", "budget": int(budget.group(1)) if budget else 3}
    if re.search(r"choke|rank|decoy|prioriti|which edge", m):
        return {"kind": "choke"}
    if re.search(r"load.bearing|central|critical asset|betweenness", m):
        return {"kind": "load_bearing"}
    if re.search(r"scan|attack path|paths|exposure|depth|hops?", m):
        return {"kind": "scan", "depth": int(next(g for g in depth.groups() if g)) if depth else 8}
    return {"kind": "help"}


async def _do(mcp, tool, args, results):
    """Call one tool through MCP; yield the tool_call and tool_result events; store the result."""
    yield {"event": "tool_call", "tool": tool, "args": args}
    env = await mcp.call(tool, args)
    results.append((tool, env))
    yield {"event": "tool_result", "tool": tool, "outcome": env["outcome"], "envelope": env}


def _final(text, checked, reason="", mode="router"):
    return {"event": "final", "text": text, "checked": checked, "reason": reason, "mode": mode}


async def router_events(message, mcp):
    req = parse_request(message)
    kind, results = req["kind"], []
    if kind == "refuse_decision":
        yield _final("I can't approve or reject changes; only a human can. Use the decision endpoint "
                     "with the proposal's run id and a reason.", True)
        return
    if kind == "help":
        yield _final(HELP_TEXT, True)
        return

    calls = {"reach": ("explain_reachability", {"from_name": req.get("from_name"), "to_name": req.get("to_name")}),
             "exposure": ("explain_reachability", {"from_name": req.get("from_name")}),
             "recall": ("recall_decisions", {"asset_name": req.get("asset_name")}),
             "plan": ("plan_remediation", {"budget": req.get("budget")}),
             "choke": ("rank_choke_edges", {}),
             "load_bearing": ("rank_load_bearing_assets", {}),
             "scan": ("find_attack_paths", {"depth": req.get("depth")})}
    try:
        if kind in ("simulate", "propose"):
            edge_ids = req["edge_ids"]
            if not edge_ids:  # no ids given: use the current plan's edges
                async for ev in _do(mcp, "plan_remediation", {"budget": 3}, results):
                    yield ev
                edge_ids = [s["edge_id"] for s in results[-1][1]["data"].get("plan", [])]
                if not edge_ids:
                    yield _final(summarize("plan_remediation", results[-1][1]), True)
                    return
            tool = "simulate_fix" if kind == "simulate" else "propose_change"
            async for ev in _do(mcp, tool, {"edge_ids": edge_ids}, results):
                yield ev
        else:
            tool, args = calls[kind]
            args = {k: v for k, v in args.items() if v is not None}
            async for ev in _do(mcp, tool, args, results):
                yield ev
    except ToolCallError as e:
        yield _final(f"The request was rejected: {e}", True)
        return
    tool, env = results[-1]
    yield _final(summarize(tool, env), True)


# ================================================================ MCP access

class ToolCallError(Exception):
    pass


class McpCaller:
    """Talks to our own MCP server over the SDK's in-memory transport (no network hop)."""

    def __init__(self, graph_name=None):
        self._client = Client(build_server(graph_name))

    async def __aenter__(self):
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc):
        return await self._client.__aexit__(*exc)

    async def list_openai_tools(self):
        """Tool definitions discovered over MCP, in the OpenAI function format."""
        listing = await self._client.list_tools()
        tools = []
        for t in listing.tools:
            if t.name in HUMAN_ONLY:
                continue
            schema = json.loads(json.dumps(t.input_schema))
            schema.pop("title", None)
            for prop in schema.get("properties", {}).values():
                prop.pop("title", None)
            tools.append({"type": "function", "function": {
                "name": t.name, "description": (t.description or "")[:160], "parameters": schema}})
        return tools

    async def call(self, tool, args):
        result = await self._client.call_tool(tool, args)
        if result.is_error:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            raise ToolCallError(text or "the tool reported an error")
        return result.structured_content


# ================================================================ LLM loop

def compact(env: dict, max_chars: int = 4500) -> str:
    """What the model sees: names and numbers only, no trace, no long text, capped in size."""
    data = {k: v for k, v in env["data"].items() if k not in ("ticket_markdown", "config_diff")}
    out = {"outcome": env["outcome"], "notes": env["notes"][:300], "data": data}
    if env["paths"]:
        out["paths"] = [" > ".join(n["name"] for n in p["nodes"]) for p in env["paths"][:5]]
        out["paths_total"] = len(env["paths"])
    text = json.dumps(out, separators=(",", ":"))
    return text if len(text) <= max_chars else text[:max_chars] + "...(truncated)"


def providers():
    """Configured LLM endpoints in order: primary, then fallback. Empty when chat is disabled."""
    if not config.CHAT_ENABLED:
        return []
    found = []
    for label, url, key, model in (
            ("primary", config.LLM_BASE_URL, config.LLM_API_KEY, config.LLM_MODEL),
            ("fallback", config.LLM_FALLBACK_BASE_URL, config.LLM_FALLBACK_API_KEY, config.LLM_FALLBACK_MODEL)):
        if url and key and model:
            found.append((label, url, key, model))
    return found


async def _create(client, model, messages, tools):
    """One completion with a small retry/backoff on rate limits and server errors."""
    for attempt in range(2):
        try:
            return await client.chat.completions.create(model=model, messages=messages, tools=tools,
                                                         tool_choice="auto" if tools else None,
                                                         temperature=0, max_tokens=400)
        except (APIConnectionError, APITimeoutError):
            if attempt == 1:
                raise
        except APIStatusError as e:
            if attempt == 1 or e.status_code not in (429, 500, 502, 503, 504):
                raise
        await asyncio.sleep(1.5)


async def _llm_events(client, model, message, history, mcp, results):
    """Let the model call tools (max MAX_TOOL_CALLS) until it writes its sentence."""
    tools = await mcp.list_openai_tools()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": message}]
    calls_made = 0
    while True:
        resp = await _create(client, model, messages, tools if calls_made < MAX_TOOL_CALLS else None)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            yield ("text", msg.content or "")
            return
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in msg.tool_calls]})
        for call in msg.tool_calls:
            name = call.function.name
            if calls_made >= MAX_TOOL_CALLS or name in HUMAN_ONLY:
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": "tool not available; answer with what you have"})
                continue
            calls_made += 1
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            yield ("event", {"event": "tool_call", "tool": name, "args": args})
            try:
                env = await mcp.call(name, args)
            except ToolCallError as e:
                messages.append({"role": "tool", "tool_call_id": call.id, "content": f"error: {e}"})
                continue
            results.append((name, env))
            yield ("event", {"event": "tool_result", "tool": name, "outcome": env["outcome"], "envelope": env})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": compact(env)})


async def run_chat(message: str, history: list | None = None, graph_name: str | None = None, llm_clients=None):
    """Async generator of events. `llm_clients` lets tests inject [(label, client, model)].

    The agent runs in its own task and hands events over through a queue. That keeps its MCP
    session inside the task that opened it, so abandoning the stream (a client disconnect)
    cancels it cleanly instead of closing the session from another task."""
    queue: asyncio.Queue = asyncio.Queue()

    async def worker():
        try:
            async for ev in _run_chat(message, history, graph_name, llm_clients):
                await queue.put(ev)
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker())
    try:
        while (ev := await queue.get()) is not None:
            yield ev
        await task  # surface any error the worker hit
    finally:
        if not task.done():
            task.cancel()


async def _run_chat(message, history, graph_name, llm_clients):
    history = [h for h in (history or []) if h.get("role") in ("user", "assistant")][-6:]
    if llm_clients is None:
        llm_clients = [(label, AsyncOpenAI(base_url=url, api_key=key, timeout=30, max_retries=0), model)
                       for label, url, key, model in providers()]

    async with McpCaller(graph_name) as mcp:
        for label, client, model in llm_clients:
            results, text = [], None
            try:
                async for kind, payload in _llm_events(client, model, message, history, mcp, results):
                    if kind == "event":
                        yield payload
                    else:
                        text = payload
            except (APIStatusError, APIConnectionError, APITimeoutError) as e:
                yield {"event": "provider_error", "provider": label, "error": type(e).__name__}
                continue
            if text is None:
                continue
            kind = parse_request(message)["kind"]
            if not results and kind != "help":
                break  # the model skipped the tools for a request we recognise: the router answers
            if kind == "exposure" and not any(tool == "explain_reachability" for tool, _ in results):
                break  # "is X safe?" needs the reachability check; a different tool would answer another question
            envelopes = [env for _, env in results]
            verdict = check_answer(text, envelopes) if text.strip() else Check(False, "empty answer")
            if verdict.ok:
                yield _final(text.strip(), True, mode=f"llm-{label}")
            elif results:
                tool, env = results[-1]
                yield _final(summarize(tool, env), False, verdict.reason, mode=f"llm-{label}+template")
            else:  # the model answered without calling any tool and the answer did not pass
                yield _final(HELP_TEXT, False, verdict.reason, mode=f"llm-{label}+template")
            return
        async for ev in router_events(message, mcp):
            yield ev
