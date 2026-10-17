"""Run chat questions through the agent (real LLM if configured in .env) and print what happened.
Usage: python -m scripts.chat_run "question 1" "question 2" ...
Prints tool calls, the model's raw sentence status, and whether the answer checker accepted it."""
import asyncio
import json
import sys
import time

from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")  # models may emit non-ASCII characters

from app import agent  # noqa: E402  (after load_dotenv so config sees .env)


async def ask(question):
    print(f"\n> {question}")
    start = time.perf_counter()
    async for ev in agent.run_chat(question):
        if ev["event"] == "tool_call":
            print(f"   tool_call   {ev['tool']} {json.dumps(ev['args'])}")
        elif ev["event"] == "tool_result":
            print(f"   tool_result {ev['tool']} -> {ev['outcome']}")
        elif ev["event"] == "provider_error":
            print(f"   provider_error {ev['provider']}: {ev['error']}")
        else:
            print(f"   FINAL mode={ev['mode']} checked={ev['checked']}"
                  + (f" reason={ev['reason']}" if ev["reason"] else ""))
            print(f"   {ev['text']}")
    print(f"   ({time.perf_counter() - start:.1f}s)")


async def main(questions):
    for i, q in enumerate(questions):
        if i:
            await asyncio.sleep(12)  # stay under the free tier's tokens-per-minute limit
        await ask(q)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
