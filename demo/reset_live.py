"""Reseed the live demo graph (env:acme) through POST /api/reset. The token comes from .env and is never printed.
Usage: python demo/reset_live.py [base_url]"""
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
base = sys.argv[1] if len(sys.argv) > 1 else "https://trychokepoint.vercel.app"
token = os.getenv("RESET_TOKEN", "")
if not token:
    sys.exit("RESET_TOKEN is not set in .env")
r = httpx.post(f"{base}/api/reset", headers={"X-Reset-Token": token}, timeout=120)
print("reset:", r.status_code, r.json().get("data") if r.status_code == 200 else r.text[:120])
sys.exit(0 if r.status_code == 200 else 1)
