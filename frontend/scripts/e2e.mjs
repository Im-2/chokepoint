// End-to-end walkthrough of the console with a real browser (Edge/Chrome via puppeteer-core).
// Usage: node scripts/e2e.mjs <base-url> <screenshot-dir> [--safe]
//   --safe  skips the steps that WRITE to the backend (propose / approve / reject), for use on the live site.
// Exits non-zero if any check fails.
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";
import { existsSync } from "node:fs";

const [base = "http://localhost:5174", outDir = "shots", ...flags] = process.argv.slice(2);
const safe = flags.includes("--safe");
mkdirSync(outDir, { recursive: true });

const CANDIDATES = [
  process.env.BROWSER_PATH,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
].filter(Boolean);
const executablePath = CANDIDATES.find((p) => existsSync(p));
if (!executablePath) throw new Error("No Edge/Chrome found; set BROWSER_PATH");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
  if (!ok) failures++;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath, headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
const consoleErrors = [];
page.on("pageerror", (e) => consoleErrors.push(String(e)));
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

const text = (sel) => page.$eval(sel, (el) => el.textContent ?? "").catch(() => "");
const clickText = async (label, scope = "button") => {
  const ok = await page.evaluate((label, scope) => {
    const el = [...document.querySelectorAll(scope)].find((b) => b.textContent.trim().startsWith(label) && !b.disabled);
    if (el) el.click();
    return !!el;
  }, label, scope);
  if (!ok) throw new Error(`button not found or disabled: ${label}`);
};
const setRange = (sel, value) => page.$eval(sel, (el, v) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(el, String(v));
  el.dispatchEvent(new Event("input", { bubbles: true }));
}, value);
const shot = async (name, selector = ".console") => {
  const el = await page.$(selector);
  await (el ?? page).screenshot({ path: `${outDir}/${name}.png` });
};
const waitFor = (fn, label, timeout = 30000, ...args) =>
  page.waitForFunction(fn, { timeout }, ...args).catch(() => { throw new Error(`timed out waiting for: ${label}`); });

try {
  // ---------- landing ----------
  await page.goto(base, { waitUntil: "networkidle0" });
  await sleep(600);
  check("landing hero renders", (await text(".hero__title")).includes("chokepoint"));
  await shot("landing-hero", "body");
  await page.evaluate(() => document.querySelector("#how").scrollIntoView());
  await sleep(1200);
  await page.screenshot({ path: `${outDir}/landing-steps.png` });
  check("three step cards", (await page.$$(".step")).length === 3);

  // ---------- console ----------
  await page.evaluate(() => document.querySelector("#console").scrollIntoView());
  await waitFor(() => document.querySelector(".canvas__cy canvas") && document.querySelector(".stat__value")?.textContent === "130", "graph loaded");
  await sleep(900);
  check("graph loaded: 130 assets", (await text(".stat__value")) === "130");
  const dockButton = await page.$(".dock-toggle");
  check("chat dock is collapsed by default", !!dockButton);
  await shot("console-initial");

  // depth 2: honest "not modelled", never "safe"
  await setRange("#depth", 2);
  await clickText("Scan");
  await waitFor(() => document.querySelector(".note--warn"), "depth 2 note");
  const warn = await text(".note--warn");
  check("depth 2 shows no modelled path", /no modelled attack path within 2 hops/i.test(warn), warn.slice(0, 60));
  check("depth 2 says it is not a statement of safety", /not a statement that the asset is safe/i.test(warn));
  check("depth 2 badge is Not in graph", (await text(".card .badge")).includes("Not in graph"));
  await shot("console-scan-depth2");

  // depth 4: the hidden path
  await setRange("#depth", 4);
  await clickText("Scan");
  await waitFor(() => document.querySelectorAll(".path").length === 1, "one path at depth 4");
  check("depth 4 finds the hidden path", (await text(".path")).includes("svc-legacy-etl"));
  await shot("console-scan-depth4");

  // depth 8: all paths; click one to highlight
  await setRange("#depth", 8);
  await clickText("Scan");
  await waitFor(() => document.querySelectorAll(".path").length === 19, "19 paths at depth 8");
  check("depth 8 lists 19 paths", true);
  await page.click(".path");
  await sleep(700);
  check("clicking a path selects it", (await page.$$(".path--on")).length === 1);
  await shot("console-scan-depth8");

  // reach (default pickers: intern-laptop -> prod-customer-db)
  await clickText("Check reach");
  await waitFor(() => document.querySelector(".card__title")?.textContent === "Route" || [...document.querySelectorAll(".card__title")].some((t) => t.textContent === "Route"), "route card");
  check("reach returns a 5-hop route", (await text(".path__hops")).includes("5 hops"));
  // unknown asset
  await page.$eval("input[placeholder='intern-laptop']", (el) => { el.focus(); el.select(); });
  await page.keyboard.type("ghost-host-99");
  await clickText("Check reach");
  await waitFor(() => [...document.querySelectorAll(".badge")].some((b) => b.textContent === "Unknown asset"), "unknown asset badge");
  check("unknown asset is reported honestly", /Nothing was searched/i.test(await text(".note--warn")));
  await page.$eval("input[placeholder='intern-laptop']", (el) => { el.focus(); el.select(); });
  await page.keyboard.type("srv-alpha-01");
  await clickText("Check reach");
  await waitFor(() => /not a statement that the asset is safe/i.test(document.querySelector(".note--warn")?.textContent ?? ""), "no-path note");
  check("no-path asset: not_in_graph, never 'safe'", (await text(".card .badge")).includes("Not in graph"));
  await shot("console-reach-nopath");

  // choke ranking with the decoy
  await clickText("Rank choke edges");
  await waitFor(() => document.querySelector(".row--decoy"), "decoy row");
  check("decoy edge is marked", (await text(".row--decoy")).includes("Decoy") && (await text(".row--decoy")).includes("prod-customer-db"));
  check("best edge is the cheap choke edge", (await text(".row--best")).includes("role-ci-deployer"));
  await page.click(".row--best");
  await sleep(700);
  await page.$eval(".row--decoy", (el) => el.scrollIntoView({ block: "center" }));
  await shot("console-choke");

  // plan -> simulate -> toggle
  await clickText("Plan remediation");
  await waitFor(() => document.querySelector(".plan-step"), "plan steps");
  check("plan has two steps for budget 3 (stops when nothing is left)", (await page.$$(".plan-step")).length === 2);
  await shot("console-plan");
  await clickText("Simulate on a scratch copy");
  await waitFor(() => document.querySelector(".beforeafter"), "simulation");
  const ba = await page.$$eval(".ba__num", (els) => els.map((e) => e.textContent));
  check("simulation shows 19 before and 0 after", ba[0] === "19" && ba[1] === "0", ba.join(" -> "));
  check("scratch graph reported deleted", (await text(".chips")).includes("scratch graph deleted"));
  await sleep(700);
  await shot("console-simulation-after");
  await clickText("Before", ".ba");
  await sleep(700);
  check("toggle redraws the graph before the fix", (await page.$$(".path")).length === 19);
  await shot("console-simulation-before");
  await clickText("After", ".ba");

  if (!safe) {
    // propose -> reject with a reason -> re-plan
    await clickText("Propose change");
    await waitFor(() => document.querySelector(".ticket"), "ticket");
    check("proposal shows an owner team", (await text(".chips")).length > 0 && (await page.$$eval(".chip--owner", (e) => e.length)) > 0);
    check("config diff is shown", (await text(".diff-block")).includes("assume_role"));
    check("reject needs a reason", await page.$$eval("button", (bs) => !!bs.find((b) => b.textContent.startsWith("Reject…"))));
    await clickText("Reject…");
    const rejectDisabled = await page.$$eval("button", (bs) => bs.find((b) => b.textContent.startsWith("Reject with reason"))?.disabled);
    check("reject-with-reason is disabled until a reason is typed", rejectDisabled === true);
    await page.type("#reject-reason", "CI needs prod-admin during releases");
    await page.$eval(".ticket", (el) => el.scrollIntoView({ block: "start" }));
    await shot("console-proposal");
    await clickText("Reject with reason");
    await waitFor(() => /Recorded as/.test(document.querySelector(".note--fix, .note--decoy")?.textContent ?? "") || document.body.textContent.includes("Recorded as rejected"), "decision recorded");
    await waitFor(() => [...document.querySelectorAll(".memory__reason")].some((e) => e.textContent.includes("CI needs prod-admin")), "memory shows the rejection");
    check("rejection appears in decision memory", true);
    await clickText("Plan remediation");
    await waitFor(() => document.querySelector(".note--memory"), "memory note on re-plan");
    check("re-plan skips the rejected edge", (await text(".note--memory")).includes("CI needs prod-admin"));
    const steps = await page.$$eval(".plan-step__meta", (els) => els.map((e) => e.textContent));
    check("re-plan avoids role-ci-deployer -> role-prod-admin", !steps.some((s) => s.includes("role-ci-deployer → role-prod-admin")), steps.length + " steps");
    await shot("console-replan");
  }

  // trace panel
  await clickText("Show", ".trace button");
  await page.waitForSelector(".trace__run");
  const traceRuns = (await page.$$(".trace__run")).length;
  check("trace panel lists every call", traceRuns >= 8, `${traceRuns} runs`);
  await page.$eval(".trace", (el) => el.scrollIntoView({ block: "center" }));
  await shot("console-trace");

  // ---------- chat ----------
  await page.click(".dock-toggle");
  await page.waitForSelector(".dock");
  await clickText("Can intern-laptop reach prod-customer-db? Why?");
  await waitFor(() => document.querySelector(".msg--assistant .msg__text") && !document.querySelector(".typing"), "chat answer", 60000);
  const answer = (await text(".msg--assistant .msg__text")).replace(/[‐-―]/g, "-"); // models sometimes write non-breaking hyphens
  check("chat answers with the path", answer.includes("grp-platform-eng"), answer.slice(0, 70));
  check("chat shows a tool-call chip", (await page.$$(".callchip")).length >= 1);
  check("chat shows a checked badge or a template note", (await text(".msg__meta")).length > 0);
  check("chat shows the mode indicator", /Mode: (LLM|Router)/.test(await text(".dock__mode")), await text(".dock__mode"));
  await shot("console-chat", ".dock");
  await page.screenshot({ path: `${outDir}/console-with-chat.png` });

  // ---------- mobile ----------
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1, isMobile: true });
  await page.goto(base, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.querySelector("#console").scrollIntoView());
  await waitFor(() => document.querySelector(".canvas__cy canvas"), "mobile graph");
  await sleep(600);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check("mobile: no horizontal overflow", overflow <= 1, `overflow ${overflow}px`);
  await page.screenshot({ path: `${outDir}/mobile-console.png` });
} catch (e) {
  console.log(`FAIL  ${e.message}`);
  failures++;
  await page.screenshot({ path: `${outDir}/failure.png` }).catch(() => {});
}

const real = consoleErrors.filter((e) => !/favicon|ERR_BLOCKED|net::/.test(e));
check("no browser console errors", real.length === 0, real.slice(0, 2).join(" | "));
await browser.close();
console.log(failures ? `\n${failures} check(s) FAILED` : "\nall checks passed");
process.exit(failures ? 1 : 0);
