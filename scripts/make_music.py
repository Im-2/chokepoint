"""Generate an ORIGINAL ambient background track for the demo video. Nothing is downloaded or sampled.

What it makes: slow, warm pad chords (Cmaj9 - Am9 - Fmaj9 - Gsus2, repeating, each overlapping the next), no drums
and no melody, so it never competes with the voice. Each note is a few detuned sine partials with a slow swell,
spread across left and right. Then ffmpeg adds a gentle low-pass, light reverb (aecho), a 3 s fade-in and a 4 s fade-out.

Usage: python -m scripts.make_music [--seconds 240] [--out demo/audio/music.wav]
Output: 44.1 kHz 16-bit stereo WAV (git-ignored with the rest of demo/audio/). Needs numpy and ffmpeg.
It is fully deterministic (fixed seed), so the same command always makes the same track.
"""
import argparse
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
STEP = 16.0        # seconds between chord changes
OVERLAP = 7.0      # each chord fades over the next one for this long
# note frequencies in Hz (low voicings, so the pad sits under the voice)
CHORDS = [
    [130.81, 164.81, 196.00, 246.94, 293.66],   # Cmaj9: C3 E3 G3 B3 D4
    [110.00, 164.81, 196.00, 246.94, 261.63],   # Am9:   A2 E3 G3 B3 C4
    [87.31, 130.81, 164.81, 196.00, 220.00],    # Fmaj9: F2 C3 E3 G3 A3
    [98.00, 146.83, 196.00, 220.00, 293.66],    # Gsus2: G2 D3 G3 A3 D4
]
PARTIALS = [(1, 1.0), (2, 0.38), (3, 0.16), (4, 0.07)]   # soft, mostly the fundamental


def chord_buffer(freqs, length_s, rng):
    """One chord: every note as two slightly detuned voices (one left, one right) with a slow swell."""
    n = int(length_s * SR)
    t = np.arange(n, dtype=np.float32) / SR
    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)
    for f in freqs:
        for side, detune in ((left, 0.9988), (right, 1.0012)):
            phase = rng.uniform(0, 2 * np.pi)
            lfo = 1.0 + 0.10 * np.sin(2 * np.pi * rng.uniform(0.07, 0.15) * t + rng.uniform(0, 2 * np.pi))
            voice = np.zeros(n, dtype=np.float32)
            for k, amp in PARTIALS:
                voice += amp * np.sin(2 * np.pi * f * k * detune * t + phase * k)
            side += voice * lfo
    env = np.ones(n, dtype=np.float32)
    ramp = int(OVERLAP * SR)
    fade = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, ramp, dtype=np.float32))   # raised cosine 0 -> 1
    env[:ramp] = fade
    env[-ramp:] = fade[::-1]
    return left * env, right * env


def render(seconds):
    rng = np.random.default_rng(7)
    total = int(seconds * SR)
    out_l = np.zeros(total, dtype=np.float32)
    out_r = np.zeros(total, dtype=np.float32)
    start, index = 0.0, 0
    while start < seconds:
        left, right = chord_buffer(CHORDS[index % len(CHORDS)], STEP + OVERLAP, rng)
        a = int(start * SR)
        b = min(total, a + len(left))
        out_l[a:b] += left[: b - a]
        out_r[a:b] += right[: b - a]
        start += STEP
        index += 1
    peak = max(np.abs(out_l).max(), np.abs(out_r).max())
    scale = 0.5 / peak if peak else 1.0   # leave headroom; the mix sets the real level
    return (out_l * scale), (out_r * scale)


def write_wav(path, left, right):
    pcm = (np.stack([left, right], axis=1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--out", default="demo/audio/music.wav")
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    left, right = render(args.seconds)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.wav"
        write_wav(raw, left, right)
        # warm it up (low-pass), add a light reverb, and fade in over 3 s and out over 4 s
        filters = (f"highpass=f=60,lowpass=f=1700,aecho=0.8:0.85:90|180|320:0.35|0.25|0.18,"
                   f"afade=t=in:st=0:d=3,afade=t=out:st={args.seconds - 4:.2f}:d=4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", filters, "-ar", str(SR),
                        "-c:a", "pcm_s16le", str(out)], check=True)
    print(f"wrote {out} ({args.seconds:.1f} s, original synthesised pad)")


if __name__ == "__main__":
    sys.exit(main())
