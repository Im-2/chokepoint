"""Check the ElevenLabs key, the account tier, and find the voice by name. Prints no secrets.
Usage: python demo/elevenlabs_probe.py "adam stone" """
import os
import sys

import httpx
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()
key = os.getenv("ELEVENLABS_API_KEY", "")
if not key:
    sys.exit("ELEVENLABS_API_KEY is not set in .env")
headers = {"xi-api-key": key}
query = sys.argv[1] if len(sys.argv) > 1 else "adam stone"
base = "https://api.elevenlabs.io/v1"

r = httpx.get(f"{base}/user/subscription", headers=headers, timeout=30)
print("subscription:", r.status_code, {k: v for k, v in (r.json() if r.status_code == 200 else {}).items()
                                       if k in ("tier", "character_count", "character_limit", "status")} or r.text[:200])

r = httpx.get(f"{base}/voices", headers=headers, timeout=30)
print("my voices:", r.status_code)
if r.status_code == 200:
    for v in r.json().get("voices", []):
        print(f"  {v['voice_id']}  {v['name']}  [{v.get('category')}]")

r = httpx.get(f"{base}/shared-voices", headers=headers, params={"search": query, "page_size": 10}, timeout=30)
print(f"library search '{query}':", r.status_code)
if r.status_code == 200:
    for v in r.json().get("voices", []):
        print(f"  {v['voice_id']}  {v['name']}  owner={v.get('public_owner_id')}  free_users_allowed={v.get('free_users_allowed')}  "
              f"category={v.get('category')}  desc={str(v.get('description'))[:60]}")
else:
    print("  ", r.text[:200])
