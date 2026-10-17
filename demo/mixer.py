"""Audio mix for the demo video: voiceover + original ambient music, ducked under the voice, normalised to -16 LUFS.

build_final() does, in order:
  1. encode the picture alone (trimmed to the start of the run)         -> demo/video/video_only.mp4
  2. generate the music to the video length + 3 s (scripts/make_music.py)  -> demo/audio/music.wav
  3. place every narration clip at its logged start offset                 -> demo/audio/_voice_bus.wav
  4. set the music level so it sits GAP_BELOW_VOICE_DB under the voice in pauses, then duck it further while the
     voice speaks (ffmpeg sidechaincompress keyed on the voice)             -> demo/audio/_music_ducked.wav
  5. add voice + ducked music, two-pass loudnorm to -16 LUFS, true peak under -1.5 dB
  6. mux picture and sound (H.264 + AAC)                                   -> demo/chokepoint-demo.mp4
It then measures the result: how far under the voice the music is while speaking and in the pauses.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
AUDIO = ROOT / "audio"
VIDEO_DIR = ROOT / "video"
OUT_MP4 = ROOT / "chokepoint-demo.mp4"

GAP_BELOW_VOICE_DB = 16.0      # music level in the pauses, relative to the speaking voice
# sidechaincompress settings, tuned with demo/measure_mix.py so the music is ~20-25 dB under the voice while speaking
SIDECHAIN = dict(threshold=0.02, ratio=10, attack=60, release=900)
TARGET_LUFS, TARGET_TP, TARGET_LRA = -16.0, -2.0, 11.0


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def probe_duration(path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
              capture_output=True, text=True).stdout.strip()
    return float(out)


def decode_mono(path, rate=22050) -> np.ndarray:
    raw = run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(rate), "-"],
              capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-12)) if len(x) else float("-inf")


def loudnorm_stats(path, i=TARGET_LUFS, tp=TARGET_TP, lra=TARGET_LRA) -> dict:
    """Measure integrated loudness, true peak and loudness range (EBU R128) with ffmpeg's loudnorm analysis."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        f"loudnorm=I={i}:TP={tp}:LRA={lra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    block = re.findall(r"\{[^{}]*\}", p.stderr)[-1]
    return {k: float(v) for k, v in json.loads(block).items() if k != "normalization_type"}


def speech_spans(starts, trim, durations):
    return [(starts[s] - trim, starts[s] - trim + durations[s]) for s in starts]


def window(x, a, b, rate=22050):
    return x[int(max(0, a) * rate): int(max(0, b) * rate)]


def duck_report(voice_bus, ducked, spans, vdur, rate=22050) -> dict:
    """How far the music sits under the voice, while speaking and in the pauses (dB, positive = quieter than voice)."""
    v, m = decode_mono(voice_bus, rate), decode_mono(ducked, rate)
    speech_v = np.concatenate([window(v, a + 0.2, b - 0.1) for a, b in spans])
    speech_m = np.concatenate([window(m, a + 0.6, b - 0.1) for a, b in spans])      # skip the ~0.5 s the ducker needs to settle
    gaps = []   # pauses of 1.5 s or more between narration clips (shorter ones never let the music recover)
    for (_, end), (start, _) in zip(spans, spans[1:]):
        if start - end >= 1.5:
            gaps.append(window(m, end + 0.9, start - 0.1))                          # skip the release tail after speech
    gap_m = np.concatenate(gaps) if gaps else np.array([1e-6], dtype=np.float32)
    voice_level = rms_db(speech_v)
    return {"voice_speaking_dbfs": voice_level,
            "music_under_voice_while_speaking_db": voice_level - rms_db(speech_m),
            "music_under_voice_in_pauses_db": voice_level - rms_db(gap_m), "pauses_measured": len(gaps)}


def build_final(video_webm: Path, trim: float, starts: dict, segments: list, durations: dict) -> dict:
    # 1. picture only
    video_only = VIDEO_DIR / "video_only.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{trim:.3f}", "-i", str(video_webm), "-an", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart", str(video_only)])
    vdur = probe_duration(video_only)

    # 2. music, a few seconds longer than the picture
    music = AUDIO / "music.wav"
    run([sys.executable, "-m", "scripts.make_music", "--seconds", f"{vdur + 3:.1f}", "--out", str(music)], cwd=REPO)

    # 3. the voice bus: each clip at its start offset
    voice_bus = AUDIO / "_voice_bus.wav"
    inputs, parts, labels = [], [], []
    for i, seg in enumerate(segments):
        inputs += ["-i", str(AUDIO / f"{seg['id']}.mp3")]
        delay = max(0, int(round((starts[seg["id"]] - trim) * 1000)))
        parts.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
        labels.append(f"[a{i}]")
    parts.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,apad=whole_dur={vdur:.3f},"
                 f"atrim=0:{vdur:.3f},aformat=sample_fmts=flt:sample_rates=44100:channel_layouts=stereo[bus]")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(parts), "-map", "[bus]", "-c:a", "pcm_f32le", str(voice_bus)])

    # 4. levels: music sits GAP_BELOW_VOICE_DB under the voice in pauses; the ducker takes it lower while speaking
    spans = speech_spans(starts, trim, durations)
    voice_speaking = rms_db(np.concatenate([window(decode_mono(voice_bus), a + 0.2, b - 0.1) for a, b in spans]))
    music_level = rms_db(decode_mono(music)[int(5 * 22050): int((vdur - 6) * 22050)])
    pre_gain = (voice_speaking - GAP_BELOW_VOICE_DB) - music_level
    sc = SIDECHAIN
    graph = (f"[0:a]asplit=2[vmix][vsc];"
             f"[1:a]atrim=0:{vdur:.3f},asetpts=N/SR/TB,aformat=sample_fmts=flt:channel_layouts=stereo,volume={pre_gain:.2f}dB,"
             f"afade=t=out:st={vdur - 4:.3f}:d=4[mus];"
             f"[mus][vsc]sidechaincompress=threshold={sc['threshold']}:ratio={sc['ratio']}:attack={sc['attack']}:release={sc['release']}"
             f":makeup=1:detection=rms:link=average[duck];"
             f"[duck]asplit=2[duckstem][duckmix];"
             f"[vmix][duckmix]amix=inputs=2:normalize=0:duration=first[mixed]")
    ducked, mixed = AUDIO / "_music_ducked.wav", AUDIO / "_mixed_prenorm.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(voice_bus), "-i", str(music), "-filter_complex", graph,
         "-map", "[duckstem]", "-c:a", "pcm_f32le", str(ducked), "-map", "[mixed]", "-c:a", "pcm_f32le", str(mixed)])
    report = duck_report(voice_bus, ducked, spans, vdur)

    # 5. two-pass loudness normalisation to -16 LUFS, true peak under -1.5 dB
    m = loudnorm_stats(mixed)
    final_wav = AUDIO / "_final.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(mixed), "-af",
         f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
         f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
         "-ar", "44100", "-c:a", "pcm_s16le", str(final_wav)])

    # 6. mux
    run(["ffmpeg", "-v", "error", "-y", "-i", str(video_only), "-i", str(final_wav), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-ar", "44100", "-movflags", "+faststart", "-shortest", str(OUT_MP4)])
    final = loudnorm_stats(OUT_MP4)
    report.update({"final_integrated_lufs": final["input_i"], "final_true_peak_dbtp": final["input_tp"],
                   "final_loudness_range_lu": final["input_lra"], "video_seconds": vdur, "music_pregain_db": pre_gain})
    (ROOT / "mix_report.json").write_text(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in report.items()}, indent=2),
                                          encoding="utf-8")
    return report


if __name__ == "__main__":
    saved = json.loads((ROOT / "offsets.json").read_text(encoding="utf-8"))
    spec = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))
    durs = json.loads((AUDIO / "manifest.json").read_text(encoding="utf-8"))
    stats = build_final(VIDEO_DIR / saved["video"], saved["trim"], saved["starts"], spec["segments"], durs)
    print(json.dumps({k: round(v, 2) for k, v in stats.items()}, indent=2))
    print(f"wrote {OUT_MP4} ({OUT_MP4.stat().st_size / 1e6:.1f} MB)")
