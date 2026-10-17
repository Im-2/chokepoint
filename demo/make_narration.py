"""Generate the voiceover clips from demo/narration.json with the ElevenLabs API.
Usage: python demo/make_narration.py [--force] [--only s01_intro,s02_problem]
Writes demo/audio/<id>.mp3 and demo/audio/manifest.json (durations measured with ffprobe).
The clips are git-ignored (demo/audio/); the narration text is committed. Needs ELEVENLABS_API_KEY in .env."""
import argparse
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


def synthesize(text: str) -> bytes:
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice['voice_id']}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": text, "model_id": voice["model"],
              "voice_settings": {"stability": 0.55, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True, "speed": 0.96}},
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:300]}")
    return r.content


chars = sum(len(s["text"]) for s in segments)
print(f"{len(segments)} segments, {chars} characters, voice: {voice['name']}")
manifest = {}
for seg in segments:
    path = AUDIO / f"{seg['id']}.mp3"
    if only is not None and seg["id"] not in only:
        pass
    elif force or not path.exists():
        print(f"  generating {seg['id']} ({len(seg['text'])} chars)")
        path.write_bytes(synthesize(seg["text"]))
    else:
        print(f"  keeping    {seg['id']} (exists)")
    if path.exists():
        manifest[seg["id"]] = round(duration(path), 3)
(AUDIO / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
total = sum(manifest.values())
print(f"durations: {manifest}\ntotal narration: {total:.1f}s ({total / 60:.2f} min)")
