"""QA walkthrough of the live site with Playwright (headless Chromium). One screenshot per demo step.
Usage: python demo/qa_live.py <desktop|phone> [out_dir] [base_url]
WRITES to the live decision memory (propose + reject), so reset the demo graph afterwards.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
DEVICE = sys.argv[1] if len(sys.argv) > 1 else "desktop"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else f"demo/qa_shots/{DEVICE}")
BASE = sys.argv[3] if len(sys.argv) > 3 else "https://trychokepoint.vercel.app"
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()

VIEWPORTS = {"desktop": dict(width=1440, height=900), "phone": dict(width=390, height=844)}
problems = []
counter = [0]


def note(msg):
    problems.append(msg)
    print("  !!", msg)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport=VIEWPORTS[DEVICE], is_mobile=DEVICE == "phone", has_touch=DEVICE == "phone",
                                      device_scale_factor=1)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        def shot(name):
            counter[0] += 1
            path = OUT / f"{counter[0]:02d}_{name}.png"
            page.screenshot(path=str(path))
            print(f"  shot {path.name}")

        def settle(ms=700):
            page.wait_for_timeout(ms)

        def bring(selector, block="center"):
            page.locator(selector).first.evaluate(f"el => el.scrollIntoView({{block: '{block}'}})")
            settle(500)

        def button(name, exact=False, scope=None):
            root = page.locator(scope) if scope else page
            return root.get_by_role("button", name=name, exact=exact).first

        def set_depth(value):
            page.locator("#depth").evaluate(
                "(el, v) => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, v);"
                " el.dispatchEvent(new Event('input', {bubbles: true})); }", str(value))

        def fill_asset(label, value):
            box = page.get_by_label(label, exact=True)
            box.click()
            box.fill(value)
            box.press("Escape")

        # ---------------- landing
        page.goto(BASE, wait_until="networkidle")
        settle(1200)
        shot("landing-hero")
        page.mouse.wheel(0, 900 if DEVICE == "desktop" else 700)
        settle(1200)
        shot("landing-scroll-1")
        bring(".statement__text")
        settle(1500)
        shot("landing-statement")
        bring(".steps__cards", "start")
        settle(1500)
        shot("landing-steps")

        # ---------------- console
        page.locator("a.btn--cta").first.click() if False else None
        bring("#console", "start")
        page.wait_for_selector(".canvas__cy canvas", timeout=30000)
        page.wait_for_function("document.querySelector('.stat__value')?.textContent === '130'", timeout=30000)
        settle(1200)
        shot("console-load")
        bring(".canvas")
        settle(800)
        shot("graph-render")

        # scan depth 2 (honest, never "safe")
        bring("#depth")
        set_depth(2)
        button("Scan", exact=True).click()
        page.wait_for_selector(".note--warn", timeout=30000)
        settle(900)
        bring(".note--warn")
        shot("scan-depth-2")
        text = page.locator(".note--warn").first.inner_text()
        if "not a statement that the asset is safe" not in text:
            note(f"depth 2 note lacks the not-safe statement: {text[:80]}")

        # scan depth 4
        bring("#depth")
        set_depth(4)
        button("Scan", exact=True).click()
        page.wait_for_function("document.querySelectorAll('.path').length === 1", timeout=30000)
        settle(1200)
        bring(".canvas")
        shot("scan-depth-4-graph")
        bring(".paths")
        shot("scan-depth-4-path")

        # depth 8
        bring("#depth")
        set_depth(8)
        button("Scan", exact=True).click()
        page.wait_for_function("document.querySelectorAll('.path').length === 19", timeout=30000)
        settle(1000)
        bring(".canvas")
        shot("scan-depth-8")

        # reach: intern-laptop -> prod-customer-db
        bring("input[placeholder='intern-laptop']")
        fill_asset("From", "intern-laptop")
        fill_asset("To", "prod-customer-db")
        button("Check reach").click()
        page.wait_for_function("[...document.querySelectorAll('.card__title')].some(t => t.textContent === 'Route')", timeout=30000)
        settle(1200)
        bring(".canvas")
        shot("reach-intern-laptop")

        # reach: unknown asset
        bring("input[placeholder='intern-laptop']")
        fill_asset("From", "ghost-host-99")
        button("Check reach").click()
        page.wait_for_function("[...document.querySelectorAll('.badge')].some(b => b.textContent === 'Unknown asset')", timeout=30000)
        settle(800)
        bring(".note--warn")
        shot("reach-ghost-host")

        # reach: no path
        bring("input[placeholder='intern-laptop']")
        fill_asset("From", "srv-alpha-01")
        button("Check reach").click()
        page.wait_for_function("/not a statement that the asset is safe/i.test(document.querySelector('.note--warn')?.textContent ?? '')", timeout=30000)
        settle(800)
        bring(".note--warn")
        shot("reach-srv-alpha-no-path")

        # choke ranking
        bring("button:has-text('Rank choke edges')")
        button("Rank choke edges").click()
        page.wait_for_selector(".row--decoy", timeout=30000)
        settle(1000)
        bring(".row--decoy")
        shot("choke-ranking")

        # plan budget 3
        bring("button:has-text('Plan remediation')")
        button("Plan remediation").click()
        page.wait_for_selector(".plan-step", timeout=30000)
        settle(1200)
        bring(".plan-step")
        shot("plan-budget-3")
        bring(".canvas")
        shot("plan-graph")

        # simulate
        bring("button:has-text('Simulate on a scratch copy')")
        button("Simulate on a scratch copy").click()
        page.wait_for_selector(".beforeafter", timeout=60000)
        settle(1500)
        bring(".beforeafter")
        shot("simulate-after")
        bring(".canvas")
        shot("simulate-graph-after")
        button("Before", scope=".beforeafter").click()
        settle(1200)
        shot("simulate-graph-before")
        button("After", scope=".beforeafter").click()

        # propose
        bring("button:has-text('Propose change')")
        button("Propose change").click()
        page.wait_for_selector(".ticket", timeout=30000)
        settle(900)
        bring(".ticket", "start")
        shot("propose-ticket")
        bring(".diff-block")
        shot("propose-diff")

        # reject with a reason
        button("Reject…").click()
        page.fill("#reject-reason", "CI needs prod-admin during releases")
        settle(500)
        bring("#reject-reason")
        shot("reject-reason-typed")
        button("Reject with reason").click()
        page.wait_for_function("document.body.textContent.includes('Recorded as')", timeout=30000)
        settle(1200)
        bring(".memory")
        shot("decision-memory")

        # re-plan
        bring("button:has-text('Plan remediation')")
        button("Plan remediation").click()
        page.wait_for_selector(".note--memory", timeout=30000)
        settle(1500)
        bring(".note--memory")
        shot("replan-skips-rejected")
        bring(".canvas")
        shot("replan-graph")

        # trace panel
        bring(".trace")
        button("Show", scope=".trace").click()
        page.wait_for_selector(".trace__run", timeout=10000)
        settle(800)
        bring(".trace")
        shot("trace-panel")

        # chat
        page.locator(".dock-toggle").click()
        page.wait_for_selector(".dock")
        settle(600)
        shot("chat-open")
        for i, prompt in enumerate(["Can intern-laptop reach prod-customer-db?", "Plan a fix with budget 3 and simulate it.",
                                    "Is srv-alpha-01 safe?"], start=1):
            page.get_by_role("button", name=prompt, exact=True).click()
            page.wait_for_function(f"document.querySelectorAll('.msg--assistant').length === {i} && !document.querySelector('.typing')", timeout=90000)
            settle(1000)
            shot(f"chat-question-{i}")
            answer = page.locator(".msg--assistant").nth(i - 1).inner_text()
            print(f"  chat {i}: {answer[:160].replace(chr(10), ' | ')}")
        last = page.locator(".msg--assistant").nth(2).inner_text().lower()
        if "not a statement" not in last or "no modelled path" not in last:
            note("srv-alpha-01 answer lacks the honesty wording")

        # layout checks
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        if overflow > 1:
            note(f"horizontal overflow {overflow}px")
        real = [e for e in errors if "favicon" not in e]
        if real:
            note(f"browser console errors: {real[:2]}")
        browser.close()


run()
print(f"\n{DEVICE}: {counter[0]} screenshots in {OUT}; {len(problems)} problem(s)")
for p_ in problems:
    print(" -", p_)
sys.exit(1 if problems else 0)
