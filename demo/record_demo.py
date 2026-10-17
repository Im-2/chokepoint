"""Record the demo video: a REAL run against the live site, synchronised with the narration clips.

Usage:  python demo/record_demo.py [--no-mix] [--base https://trychokepoint.vercel.app]
Prereqs: python demo/make_narration.py (clips in demo/audio), python demo/reset_live.py (clean graph), ffmpeg on PATH.
What it does: Playwright (Chromium, 1920x1080) drives the site with a visible cursor and slow scrolling. For each
narration segment it logs the start offset, performs that scene's actions while the clip plays, and holds until the
clip ends. Every number shown is asserted against the live UI, so a wrong result aborts the run instead of being
recorded. Nothing is mocked or edited; captions and the end card are overlays. The clips are mixed in with ffmpeg.
Output: demo/chokepoint-demo.mp4 (git-ignored, with demo/video/ and demo/audio/).
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--base", default="https://trychokepoint.vercel.app")
parser.add_argument("--no-mix", action="store_true")
args = parser.parse_args()
BASE = args.base

SEGMENTS = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))["segments"]
DURATIONS = json.loads((ROOT / "audio" / "manifest.json").read_text(encoding="utf-8"))
VIDEO_DIR = ROOT / "video"
OUT_MP4 = ROOT / "chokepoint-demo.mp4"
W, H = 1920, 1080

# ------------------------------------------------------------------ cursor, captions, end card (overlays only)
OVERLAY_JS = r"""
(() => {
  const css = `
  #__cur{position:fixed;z-index:2147483647;left:-50px;top:-50px;width:30px;height:30px;pointer-events:none;filter:drop-shadow(0 2px 3px rgba(0,0,0,.6))}
  #__ring{position:fixed;z-index:2147483646;pointer-events:none;width:44px;height:44px;border-radius:50%;border:3px solid rgba(255,255,255,.95);left:-50px;top:-50px;opacity:0}
  #__ring.go{animation:__ripple .55s ease-out}
  @keyframes __ripple{0%{opacity:.95;transform:translate(-50%,-50%) scale(.3)}100%{opacity:0;transform:translate(-50%,-50%) scale(1.5)}}
  #__cap{position:fixed;z-index:2147483645;left:50%;bottom:30px;transform:translateX(-50%);padding:11px 24px;border-radius:999px;
    background:rgba(8,8,8,.86);border:1px solid rgba(255,255,255,.2);color:#f4f1ea;font:500 21px/1.3 Inter,system-ui,sans-serif;
    opacity:0;transition:opacity .4s;pointer-events:none;max-width:84vw;text-align:center;white-space:nowrap}
  #__cap.on{opacity:1}
  #__end{position:fixed;inset:0;z-index:2147483644;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;
    background:radial-gradient(ellipse 60% 50% at 50% 12%,#f85111,#ca240a 38%,#80170c 62%,#300d08 82%,#050202);opacity:0;transition:opacity .8s;pointer-events:none;color:#fafaf5}
  #__end.on{opacity:1}
  #__end h1{font:400 120px/1 'Instrument Serif',Georgia,serif;margin:0}
  #__end p{font:500 26px/1.4 Inter,system-ui,sans-serif;margin:0;opacity:.92}
  #__end small{font:500 18px/1.4 Inter,system-ui,sans-serif;opacity:.7;letter-spacing:.08em;text-transform:uppercase}`;
  const style = document.createElement('style'); style.textContent = css;
  const cur = document.createElement('div'); cur.id = '__cur';
  cur.innerHTML = '<svg viewBox="0 0 24 24" width="30" height="30"><path d="M3.5 2.5l7.6 18.2 2.5-7.5 7.4-2.6z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const ring = document.createElement('div'); ring.id = '__ring';
  const cap = document.createElement('div'); cap.id = '__cap';
  const end = document.createElement('div'); end.id = '__end';
  end.innerHTML = '<h1>Chokepoint</h1><p>trychokepoint.vercel.app &nbsp;·&nbsp; github.com/Im-2/chokepoint</p><small>Graph Hacks · Track 01 · FalkorDB · synthetic data · AI-generated voiceover</small>';
  const mount = () => { document.head.append(style); document.body.append(cur, ring, cap, end); };
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
  addEventListener('mousemove', e => { cur.style.left = e.clientX - 5 + 'px'; cur.style.top = e.clientY - 3 + 'px'; }, true);
  addEventListener('mousedown', e => { ring.style.left = e.clientX + 'px'; ring.style.top = e.clientY + 'px';
    ring.classList.remove('go'); void ring.offsetWidth; ring.classList.add('go'); }, true);
  window.__caption = t => { if (t) cap.textContent = t; cap.classList.toggle('on', !!t); };
  window.__endcard = on => end.classList.toggle('on', !!on);
})();
"""


def smooth(t):  # ease in-out
    return t * t * (3 - 2 * t)


class Recorder:
    def __init__(self, page):
        self.page = page
        self.t0 = time.perf_counter()
        self.x, self.y = W / 2, H / 2
        self.starts = {}
        self.notes = []
        self.fallbacks = []

    # ---- time
    def now(self):
        return time.perf_counter() - self.t0

    def at(self, t_abs):
        wait = t_abs - self.now()
        if wait > 0:
            time.sleep(wait)

    def pause(self, s):
        time.sleep(s)

    # ---- pointer
    def glide(self, x, y, dur=0.7):
        steps = max(10, int(dur * 55))
        x0, y0 = self.x, self.y
        for i in range(1, steps + 1):
            k = smooth(i / steps)
            self.page.mouse.move(x0 + (x - x0) * k, y0 + (y - y0) * k)
            time.sleep(dur / steps)
        self.x, self.y = x, y

    def center(self, loc):
        box = loc.bounding_box()
        assert box, "element has no box"
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def hover(self, loc, dur=0.7):
        x, y = self.center(loc)
        self.glide(x, y, dur)

    def click(self, loc, dur=0.7):
        self.hover(loc, dur)
        time.sleep(0.12)
        self.page.mouse.down()
        time.sleep(0.07)
        self.page.mouse.up()
        time.sleep(0.15)

    # ---- scrolling (instant steps, smoothed by us)
    def _scroll(self, js_get_target, total, dur):
        steps = max(12, int(dur * 50))
        prev = 0.0
        for i in range(1, steps + 1):
            cur = total * smooth(i / steps)
            self.page.evaluate(f"d => {js_get_target}.scrollBy({{top: d, behavior: 'instant'}})", cur - prev)
            prev = cur
            time.sleep(dur / steps)

    def scroll_window(self, total, dur=2.0):
        self._scroll("window", total, dur)

    def bring_window(self, selector, top_offset=110, dur=1.6):
        delta = self.page.evaluate(f"document.querySelector('{selector}').getBoundingClientRect().top") - top_offset
        self.scroll_window(delta, dur)

    def bring_in(self, container, selector, dur=1.0, align=0.35):
        """Scroll inside a panel so the element sits at `align` of the panel height."""
        delta = self.page.evaluate(
            """([c, s, a]) => { const box = document.querySelector(c); const el = document.querySelector(s);
              const cb = box.getBoundingClientRect(), eb = el.getBoundingClientRect();
              return eb.top + eb.height / 2 - (cb.top + cb.height * a); }""", [container, selector, align])
        if abs(delta) > 4:
            self._scroll(f"document.querySelector('{container}')", delta, dur)

    # ---- overlays
    def caption(self, text):
        self.page.evaluate("t => window.__caption(t)", text)

    def endcard(self, on=True):
        self.page.evaluate("o => window.__endcard(o)", on)

    # ---- narration segments
    def segment(self, seg_id):
        self.starts[seg_id] = round(self.now(), 3)
        print(f"[{self.now():6.1f}s] {seg_id}")
        return self.starts[seg_id]

    def end_segment(self, seg_id, tail=0.45):
        self.at(self.starts[seg_id] + DURATIONS[seg_id] + tail)

    def check(self, ok, what):
        print(f"      {'ok  ' if ok else 'FAIL'} {what}")
        if not ok:
            raise SystemExit(f"assertion failed during recording: {what}")


def run():
    VIDEO_DIR.mkdir(exist_ok=True)
    for f in VIDEO_DIR.glob("*.webm"):
        f.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                                  record_video_dir=str(VIDEO_DIR), record_video_size={"width": W, "height": H})
        ctx.add_init_script(OVERLAY_JS)
        page = ctx.new_page()
        page.set_default_timeout(45000)
        R = Recorder(page)
        page.goto(BASE, wait_until="networkidle")
        # warm up the lazily loaded console chunk off-camera so the scene is smooth, then return to the top
        page.evaluate("document.querySelector('#console').scrollIntoView({behavior: 'instant'})")
        page.wait_for_selector(".canvas__cy canvas")
        page.wait_for_function("document.querySelector('.stat__value')?.textContent === '130'")
        page.wait_for_timeout(1200)
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        page.wait_for_timeout(1500)
        TRIM = R.now() - 0.2  # everything before this (page load) is cut from the final video
        R.glide(W * 0.62, H * 0.62, 0.01)

        scan_btn = page.get_by_role("button", name="Scan", exact=True)
        slider = page.locator("#depth")

        def set_depth(target, current):
            """Move the slider with the keyboard (visible) from `current` to `target`."""
            slider.focus()
            key = "ArrowRight" if target > current else "ArrowLeft"
            for _ in range(abs(target - current)):
                page.keyboard.press(key)
                time.sleep(0.28)

        def scan(depth, current):
            R.hover(slider, 0.6)
            set_depth(depth, current)
            R.click(scan_btn, 0.5)

        # =============== s01 intro ===============
        t = R.segment("s01_intro")
        R.caption("Voiceover is AI-generated · everything on screen is a real run on trychokepoint.vercel.app")
        R.glide(W * 0.5, H * 0.72, 3.0)
        R.end_segment("s01_intro")

        # =============== s02 problem: scroll to the statement ===============
        t = R.segment("s02_problem")
        R.caption(None)
        R.scroll_window(1350, 11.0)  # the statement words light up as we scroll
        R.end_segment("s02_problem")

        # =============== s03 graph: steps, then the console ===============
        t = R.segment("s03_graph")
        R.scroll_window(1050, 3.5)   # the three step cards
        R.pause(1.2)
        R.bring_window(".console__grid", 105, 3.0)
        R.caption("130 assets · 322 attack edges · stored in FalkorDB")
        page.wait_for_selector(".canvas__cy canvas")
        R.check(page.locator(".stat__value").nth(0).inner_text() == "130", "130 assets on screen")
        R.check(page.locator(".stat__value").nth(1).inner_text() == "322", "322 connections on screen")
        R.bring_window(".chead", 70, 1.0)
        R.hover(page.locator(".stat").nth(0), 0.8)
        R.hover(page.locator(".stat").nth(1), 0.8)
        R.bring_window(".console__grid", 105, 1.0)
        R.hover(page.locator(".canvas__cy"), 1.0)
        R.end_segment("s03_graph")

        # =============== s04 depth 2 and 3 ===============
        t = R.segment("s04_depth2")
        R.caption("Depth 2 and 3: 0 paths · no modelled path is not the same as safe")
        scan(2, 4)
        page.wait_for_selector(".note--warn")
        page.wait_for_function("document.querySelector('.note--warn')?.textContent.includes('2 hops')")
        warn = page.locator(".note--warn").first.inner_text()
        R.check("not a statement that the asset is safe" in warn, "depth 2 says it is not a statement of safety")
        R.pause(2.2)
        R.hover(page.locator(".note--warn").first, 0.8)
        R.pause(1.0)
        R.hover(slider, 0.6)
        set_depth(3, 2)
        R.click(scan_btn, 0.5)
        page.wait_for_function("document.querySelector('.note--warn')?.textContent.includes('3 hops')")
        R.check("3 hops" in page.locator(".note--warn").first.inner_text(), "depth 3 also finds nothing")
        R.end_segment("s04_depth2")

        # =============== s05 depth 4 and 8 ===============
        t = R.segment("s05_depth4")
        R.caption("Depth 4: 1 path, through svc-legacy-etl · Depth 8: 19 paths")
        scan(4, 3)
        page.wait_for_function("document.querySelectorAll('.path').length === 1")
        R.check("svc-legacy-etl" in page.locator(".path").first.inner_text(), "depth 4: one path through svc-legacy-etl")
        R.pause(1.5)
        R.hover(page.locator(".path").first, 1.0)
        R.pause(6.0)
        R.hover(slider, 0.6)
        set_depth(8, 4)
        R.click(scan_btn, 0.5)
        page.wait_for_function("document.querySelectorAll('.path').length === 19")
        R.check(True, "depth 8: 19 paths")
        R.pause(1.2)
        R.click(page.locator(".path").first, 0.8)
        R.end_segment("s05_depth4")

        # =============== s06 choke edges and the decoy ===============
        t = R.segment("s06_decoy")
        R.caption(None)
        R.click(page.get_by_role("button", name="Rank choke edges"), 0.9)
        page.wait_for_selector(".row--decoy")
        R.bring_in(".console__right", ".row--decoy", 1.0, 0.45)
        R.pause(0.6)
        R.caption("Decoy: 15 paths but disruption 9 · Best: 11 paths at disruption 2")
        decoy = page.locator(".row--decoy")
        R.check("15" in decoy.inner_text() and "9" in decoy.inner_text(), "decoy row: 15 paths, disruption 9")
        best = page.locator(".row--best")
        R.check("11" in best.inner_text() and "role-ci-deployer" in best.inner_text(), "best row: role-ci-deployer, 11 paths")
        R.at(t + 8.0)
        R.click(decoy, 0.9)
        R.at(t + 14.5)
        R.click(best, 0.9)
        R.end_segment("s06_decoy")

        # =============== s07 plan and simulate ===============
        t = R.segment("s07_plan_sim")
        R.caption(None)
        R.click(page.get_by_role("button", name="Plan remediation"), 0.9)
        page.wait_for_selector(".plan-step")
        R.check(len(page.locator(".plan-step").all()) == 2, "plan: two edges")
        R.bring_in(".console__right", ".plan-step", 1.0, 0.35)
        plan_text = page.locator(".stat-row").first.inner_text()
        R.check("19" in plan_text and "5" in plan_text, f"plan cuts 19 of 19 at disruption 5 ({plan_text.replace(chr(10), ' ')})")
        R.caption("Plan: 19 of 19 paths cut · total disruption 5 · greedy, not a proof")
        R.at(t + 7.0)
        R.click(page.get_by_role("button", name="Simulate on a scratch copy"), 0.9)
        page.wait_for_selector(".beforeafter")
        R.bring_in(".console__right", ".beforeafter", 1.0, 0.35)
        nums = [e.inner_text() for e in page.locator(".ba__num").all()]
        R.check(nums == ["19", "0"], f"simulation 19 -> 0 ({nums})")
        R.check("scratch graph deleted" in page.locator(".chips").first.inner_text(), "scratch graph deleted")
        R.caption("Simulated on a scratch graph: 19 paths before → 0 after · scratch graph deleted")
        R.at(t + 13.5)
        R.click(page.locator(".ba").first, 0.8)   # Before
        R.pause(2.2)
        R.click(page.locator(".ba").nth(1), 0.8)  # After
        R.end_segment("s07_plan_sim")

        # =============== s08 chat ===============
        asked = [0]

        def ask(prompt, retry=True):
            asked[0] += 1
            n = asked[0]
            chip = page.get_by_role("button", name=prompt, exact=True)
            chip.scroll_into_view_if_needed()
            R.click(chip, 0.8)
            page.wait_for_function(f"document.querySelectorAll('.msg--assistant').length >= {n} && !document.querySelector('.typing')", timeout=75000)
            R.pause(0.4)
            meta = page.locator(".msg--assistant").nth(n - 1).inner_text()
            mode_text = page.locator(".dock__mode").inner_text()
            limited = "rate limited" in mode_text.lower() or "router" in mode_text.lower() or "replaced by template" in meta.lower()
            if limited:
                R.fallbacks.append((prompt, mode_text, meta[:120]))
                print(f"      !! chat fell back: {mode_text.strip()} | {meta[:100]!r}")
            return meta

        t = R.segment("s08a_chat_intro")
        R.caption("Ask Chokepoint")
        R.click(page.locator(".dock-toggle"), 0.9)
        page.wait_for_selector(".dock")
        R.end_segment("s08a_chat_intro")

        t = R.segment("s08b_chat_q1")
        R.caption("The model only picks from a fixed tool catalogue over MCP · it never writes Cypher")
        ans1 = ask("Can intern-laptop reach prod-customer-db?")
        R.check("grp-platform-eng" in ans1.replace("‑", "-") and "explain_reachability" in ans1, "chat 1: reach tool + the 5-hop path")
        R.check("checked" in ans1, "chat 1: checked badge")
        R.end_segment("s08b_chat_q1")

        t = R.segment("s08c_chat_q2")
        R.click(page.get_by_role("button", name="Show", exact=True).last, 0.9)  # open the trace panel
        page.wait_for_selector(".trace__run")
        ans2 = ask("Plan a fix with budget 3 and simulate it.")
        R.check("plan_remediation" in ans2 and "simulate_fix" in ans2, "chat 2: plan_remediation then simulate_fix")
        R.check("e023" in ans2 or "e022" in ans2 or "19" in ans2 or "verified" in ans2.lower(), "chat 2: answer about the plan")
        R.hover(page.locator(".trace__run").first, 0.9)
        R.end_segment("s08c_chat_q2")

        t = R.segment("s08d_chat_q3")
        R.caption("No modelled path ≠ safe")
        ans3 = ask("Is srv-alpha-01 safe?")
        low = ans3.lower()
        R.check("no modelled path" in low and "not a statement" in low, "chat 3: no modelled path, not a statement of safety")
        R.hover(page.locator(".msg--assistant").last, 0.8)
        R.end_segment("s08d_chat_q3")

        # =============== s09 propose one edge, reject with a reason ===============
        t = R.segment("s09_propose_reject")
        R.caption(None)
        R.click(page.get_by_role("button", name="Close chat", exact=True), 0.8)  # close chat
        R.bring_in(".console__right", ".plan-step", 1.0, 0.3)
        R.click(page.get_by_role("button", name="Propose only this edge").first, 0.9)
        page.wait_for_selector(".ticket")
        R.bring_in(".console__right", ".ticket", 1.0, 0.3)
        ticket = page.locator(".ticket").inner_text()
        R.check("e023" in ticket and "e022" not in ticket, "proposal is for e023 only")
        R.check(page.locator(".chip--owner").count() > 0, "owner team shown")
        R.caption("Only a person can approve or reject")
        R.at(t + 8.5)
        R.click(page.get_by_role("button", name="Reject…"), 0.9)
        box = page.locator("#reject-reason")
        R.click(box, 0.7)
        page.keyboard.type("CI needs prod-admin during releases", delay=62)
        R.pause(0.5)
        R.click(page.get_by_role("button", name="Reject with reason"), 0.8)
        page.wait_for_function("document.body.textContent.includes('Recorded as')")
        R.check(True, "rejection recorded")
        R.end_segment("s09_propose_reject")

        # =============== s10 re-plan and memory ===============
        t = R.segment("s10_replan_memory")
        R.caption(None)
        R.bring_in(".console__right", ".plan-step", 0.8, 0.3)
        R.click(page.get_by_role("button", name="Plan remediation"), 0.9)
        page.wait_for_selector(".note--memory")
        page.wait_for_function("document.querySelector('.note--memory')?.textContent.includes('CI needs prod-admin')")
        R.bring_in(".console__right", ".stat-row", 0.8, 0.2)
        stats = page.locator(".stat-row").first.inner_text().replace("\n", " ")
        R.check("15" in stats and "19" in stats and "4" in stats and "6" in stats, f"re-plan: 15 of 19, 4 remain, disruption 6 ({stats})")
        R.caption("Re-plan: 15 of 19 paths cut · total disruption 6 · 4 remain · rejected edge skipped")
        R.pause(3.0)
        R.hover(page.locator(".note--memory"), 0.9)
        R.at(t + 11.0)
        R.bring_in(".console__right", ".memory", 1.2, 0.3)
        R.hover(page.locator(".memory__item").first, 0.9)
        R.end_segment("s10_replan_memory")

        # =============== s11 unknown asset ===============
        t = R.segment("s11_unknown")
        R.caption("Unknown asset: no query runs")
        from_box = page.get_by_label("From", exact=True)
        R.click(from_box, 0.9)
        page.keyboard.press("Control+A")
        page.keyboard.type("ghost-host-99", delay=70)
        page.keyboard.press("Escape")
        R.click(page.get_by_role("button", name="Check reach"), 0.8)
        page.wait_for_function("[...document.querySelectorAll('.badge')].some(b => b.textContent === 'Unknown asset')")
        R.bring_in(".console__right", ".badge--warn", 0.8, 0.3)
        R.check(True, "unknown asset reported")
        R.end_segment("s11_unknown")

        # =============== s12 trace and close ===============
        t = R.segment("s12_close")
        R.caption(None)
        R.hover(page.locator(".trace"), 1.0)
        R.pause(3.0)
        R.hover(page.get_by_role("button", name="Copy MCP endpoint"), 1.0)
        R.at(t + DURATIONS["s12_close"] - 1.5)
        R.endcard(True)
        R.end_segment("s12_close", tail=4.0)

        total = R.now()
        ctx.close()
        video = max(VIDEO_DIR.glob("*.webm"), key=lambda f: f.stat().st_mtime)
        browser.close()

    offsets = {"trim": round(TRIM, 3), "total": round(total, 3), "starts": R.starts, "fallbacks": R.fallbacks,
               "video": video.name}
    (ROOT / "offsets.json").write_text(json.dumps(offsets, indent=2), encoding="utf-8")
    print(f"\nrecorded {total:.1f}s (trim {TRIM:.2f}s) -> {video.name}")
    return video, TRIM, R.starts, R.fallbacks


def mix(video: Path, trim: float, starts: dict):
    inputs = ["-ss", f"{trim:.3f}", "-i", str(video)]
    filters, labels = [], []
    for i, seg in enumerate(SEGMENTS, start=1):
        inputs += ["-i", str(ROOT / "audio" / f"{seg['id']}.mp3")]
        delay = max(0, int(round((starts[seg["id"]] - trim) * 1000)))
        filters.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
        labels.append(f"[a{i}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0[aout]")
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "25",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(OUT_MP4)]
    subprocess.run(cmd, check=True)
    size = OUT_MP4.stat().st_size / 1e6
    print(f"mixed -> {OUT_MP4} ({size:.1f} MB)")


if __name__ == "__main__":
    video, trim, starts, fallbacks = run()
    if fallbacks:
        print("\nThe free-tier model fell back during the chat scene:")
        for f in fallbacks:
            print("  ", f)
        print("Fix or re-record (the narration says the model answered) before publishing this take.")
    if not args.no_mix:
        mix(video, trim, starts)
    sys.exit(3 if fallbacks else 0)
