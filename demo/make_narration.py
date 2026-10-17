"""Generate the voiceover clips from demo/narration.json with the ElevenLabs API.
Usage: python demo/make_narration.py [--force] [--only s01_intro,s02_problem]
Only clips whose text (or voice settings) changed are regenerated; the rest are reused to save credits (demo/audio/cache.json).
Writes demo/audio/<id>.mp3 and demo/audio/manifest.json (durations measured with ffprobe).
The clips are git-ignored (demo/audio/); the narration text is committed. Needs ELEVENLABS_API_KEY in .env."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()
ROOT = Path(__file__).resolve().parent
AUDIO = ROOT / "audio"
AUDIO.mkdir(exist_ok=True)

key = os.getenv("ELEVENLABS_API_KEY", "")
if not key:
    sys.exit("ELEVENLABS_API_KEY is not set in .env")
spec = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))
voice, segments = spec["voice"], spec["segments"]
parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true", help="regenerate clips that already exist")
parser.add_argument("--only", default="", help="comma-separated segment ids to (re)generate")
args = parser.parse_args()
force = args.force
only = set(filter(None, args.only.split(","))) or None


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


SETTINGS = {"stability": 0.55, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True, "speed": 0.96}


def synthesize(text: str) -> bytes:
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice['voice_id']}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": text, "model_id": voice["model"],
              "voice_settings": SETTINGS},
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:300]}")
    return r.content


def fingerprint(text: str) -> str:
    """What a clip depends on: its text and the voice settings. If this is unchanged the cached clip is reused."""
    blob = json.dumps([text, voice["voice_id"], voice["model"], SETTINGS], sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def bootstrap_cache() -> dict:
    """First run with a cache: trust the existing clips as the ones made from the last committed narration text."""
    cache = {}
    shown = subprocess.run(["git", "show", "HEAD:demo/narration.json"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if shown.returncode == 0:
        old = json.loads(shown.stdout)
        old_voice = old["voice"]
        for seg in old["segments"]:
            if (AUDIO / f"{seg['id']}.mp3").exists():
                blob = json.dumps([seg["text"], old_voice["voice_id"], old_voice["model"], SETTINGS], sort_keys=True)
                cache[seg["id"]] = hashlib.sha1(blob.encode("utf-8")).hexdigest()
    return cache


CACHE_FILE = AUDIO / "cache.json"
cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else bootstrap_cache()

chars = sum(len(s["text"]) for s in segments)
print(f"{len(segments)} segments, {chars} characters, voice: {voice['name']}")
manifest, spent = {}, 0
for seg in segments:
    path = AUDIO / f"{seg['id']}.mp3"
    fp = fingerprint(seg["text"])
    wanted = only is None or seg["id"] in only
    if wanted and (force or not path.exists() or cache.get(seg["id"]) != fp):
        why = "forced" if force else "new" if not path.exists() else "text changed"
        print(f"  generating {seg['id']} ({len(seg['text'])} chars, {why})")
        path.write_bytes(synthesize(seg["text"]))
        cache[seg["id"]] = fp
        spent += len(seg["text"])
    else:
        print(f"  reusing    {seg['id']} (cached, text unchanged)")
    if path.exists():
        manifest[seg["id"]] = round(duration(path), 3)
CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
(AUDIO / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
total = sum(manifest.values())
print(f"credits spent this run: {spent} characters")
print(f"durations: {manifest}")
print(f"total narration: {total:.1f}s ({total / 60:.2f} min)")
