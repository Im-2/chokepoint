"""Ask the chat questions used in the demo over real HTTP (SSE) and check the answers.
Usage: python -m scripts.live_chat_check [base_url]     (default https://trychokepoint.vercel.app)
Read-only questions only: nothing here writes to the graph's decision memory."""
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://trychokepoint.vercel.app"
sys.stdout.reconfigure(encoding="utf-8")


def ask(message):
    events = []
    started = time.perf_counter()
    with httpx.stream("POST", f"{BASE}/api/chat", json={"message": message}, timeout=90) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events, time.perf_counter() - started


def norm(text):
    return text.replace("‑", "-").replace("‐", "-")


QUESTIONS = [
    ("Can intern-laptop reach prod-customer-db?",
     lambda tools, final, text: tools == ["explain_reachability"] and "grp-platform-eng" in text),
    ("Plan a fix with budget 3 and simulate it.",
     lambda tools, final, text: tools[:2] == ["plan_remediation", "simulate_fix"] and "Edge IDs are required" not in text),
    ("Is srv-alpha-01 safe?",
     lambda tools, final, text: "explain_reachability" in tools and "no modelled path" in text.lower()
     and "not a statement" in text.lower()),
]

failed = 0
for i, (question, check) in enumerate(QUESTIONS):
    if i:
        time.sleep(8)  # stay inside the free tier's tokens-per-minute budget
    events, seconds = ask(question)
    tools = [e["tool"] for e in events if e["event"] == "tool_call"]
    final = next((e for e in events if e["event"] == "final"), {})
    text = norm(final.get("text", ""))
    errors = [e for e in events if e["event"] == "provider_error"]
    ok = bool(final) and check(tools, final, text)
    failed += not ok
    print(f"\n[{'PASS' if ok else 'FAIL'}] {question}  ({seconds:.1f}s)")
    print(f"   tools: {tools}")
    print(f"   mode={final.get('mode')} checked={final.get('checked')} reason={final.get('reason') or '-'}"
          + (f" provider_errors={[e['error'] for e in errors]}" if errors else ""))
    print(f"   answer: {text}")
print("\nall chat checks passed" if not failed else f"\n{failed} chat check(s) FAILED")
sys.exit(1 if failed else 0)
