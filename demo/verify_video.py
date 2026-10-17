"""Extract one frame per narration segment from the final video (for visual checks) and print stream facts.
Usage: python demo/verify_video.py [out_dir]   -> contact sheets (4 frames each) in out_dir"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "frames")
out.mkdir(parents=True, exist_ok=True)
for f in out.glob("*.png"):
    f.unlink()
offsets = json.loads((ROOT / "offsets.json").read_text(encoding="utf-8"))
durations = json.loads((ROOT / "audio" / "manifest.json").read_text(encoding="utf-8"))
trim, starts = offsets["trim"], offsets["starts"]
video = ROOT / "chokepoint-demo.mp4"

print("segment start (s in final video) / narration length / gap before next")
ids = list(starts)
frames = []
for i, seg in enumerate(ids):
    start = starts[seg] - trim
    nxt = (starts[ids[i + 1]] - trim) if i + 1 < len(ids) else None
    gap = f"{nxt - (start + durations[seg]):+.1f}s" if nxt is not None else "-"
    print(f"  {seg:<20} start {start:6.1f}  len {durations[seg]:5.1f}  gap {gap}")
    t = start + min(4.0, durations[seg] * 0.6)
    path = out / f"{i:02d}_{seg}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(path)], check=True)
    frames.append(path)

for n in range(0, len(frames), 4):
    group = frames[n:n + 4]
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for g in group:
        cmd += ["-i", str(g)]
    filt = "".join(f"[{k}:v]scale=960:540[v{k}];" for k in range(len(group)))
    while len(group) < 4:
        group.append(None)
    layout = {1: "0_0", 2: "0_0|w0_0", 3: "0_0|w0_0|0_h0", 4: "0_0|w0_0|0_h0|w0_h0"}[len([g for g in group if g])]
    filt += "".join(f"[v{k}]" for k in range(len([g for g in group if g]))) + f"xstack=inputs={len([g for g in group if g])}:layout={layout}[out]"
    cmd += ["-filter_complex", filt, "-map", "[out]", "-frames:v", "1", str(out / f"sheet_{n // 4}.png")]
    subprocess.run(cmd, check=True)
print("sheets:", sorted(p.name for p in out.glob("sheet_*.png")))

info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video)],
                      capture_output=True, text=True).stdout.strip()
print(f"video duration {float(info):.1f}s; narration ends at {starts[ids[-1]] - trim + durations[ids[-1]]:.1f}s")
