"""Write docs/DEMO_SCRIPT.md from demo/narration.json and the timings of the last recording (demo/offsets.json).
Usage: python demo/build_script_doc.py"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
narration = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))
offsets = json.loads((ROOT / "offsets.json").read_text(encoding="utf-8"))
durations = json.loads((ROOT / "audio" / "manifest.json").read_text(encoding="utf-8"))
voice = narration["voice"]
trim, starts = offsets["trim"], offsets["starts"]

ON_SCREEN = {
    "s01_intro": "Landing hero. Caption: the voiceover is AI-generated and this is a real run on the live site.",
    "s02_problem": "Slow scroll; the statement brightens word by word (scroll-linked).",
    "s03_graph": "The three step cards, then the console. Hover the stat tiles (130 assets, 322 connections) and the graph.",
    "s04_depth2": "Slider to 2, **Scan**: 'No modelled attack path within 2 hops ... not a statement that the asset is safe'. Slider to 3, **Scan**: same.",
    "s05_depth4": "Slider to 4, **Scan**: 1 path through `svc-legacy-etl`, highlighted on the graph. Slider to 8, **Scan**: 19 paths; click the shortest.",
    "s06_decoy": "**Rank choke edges**. The decoy row (15 paths, disruption 9) is hovered and clicked, then the best row (11 paths, disruption 2).",
    "s07_plan_sim": "**Plan remediation** (2 edges, 19 of 19, disruption 5), **Simulate on a scratch copy** (19 to 0, scratch graph deleted), toggle Before / After.",
    "s08a_chat_intro": "Open the docked chat, 'Ask Chokepoint'.",
    "s08b_chat_q1": "Click the suggested prompt 'Can intern-laptop reach prod-customer-db?': tool chip `explain_reachability`, the 5-hop path, 'checked' badge.",
    "s08c_chat_q2": "Open the Trace panel. Prompt 'Plan a fix with budget 3 and simulate it.': `plan_remediation` then `simulate_fix`; the trace fills with every query.",
    "s08d_chat_q3": "Prompt 'Is srv-alpha-01 safe?': 'no modelled path ... not a statement that the asset is safe'.",
    "s09_propose_reject": "Close the chat. **Propose only this edge** on the first plan step (e023): ticket, owner team, config diff. **Reject...**, type the reason, **Reject with reason**.",
    "s10_replan_memory": "**Plan remediation** again: the rejected edge is skipped; 15 of 19 cut, disruption 6, 4 remain. Then the decision memory.",
    "s11_unknown": "Reach from `ghost-host-99`: 'Unknown asset ... Nothing was searched'; the trace shows only name lookups.",
    "s12_close": "Trace panel and the MCP endpoint button, then the end card.",
}


def stamp(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


rows = []
for seg in narration["segments"]:
    start = starts[seg["id"]] - trim
    rows.append(f"| {stamp(start)} | {seg['scene']} | {seg['text']} | {ON_SCREEN[seg['id']]} |")

total_video = offsets["total"] - trim
speech = sum(durations.values())
doc = f"""# Demo video script (about {total_video / 60:.1f} minutes)

A real, unedited run against the live site, https://trychokepoint.vercel.app, recorded by `demo/record_demo.py`
(Playwright, Chromium, 1920x1080, visible cursor, slow scrolling). Captions and the end card are overlays; every
result on screen comes from the live API and is asserted by the recorder as it goes (a wrong number aborts the take).
**The voiceover is AI-generated** (ElevenLabs) and the video says so in its first caption and on the end card.

Length: {stamp(total_video)} of video with {speech:.0f} s of speech. The chat scene ("Ask Chokepoint") is about 35 s.

## Numbers the narration uses (all from the live run)
| Fact | Value |
|---|---|
| Environment | 130 assets, 322 `PIVOT` (attack) edges, synthetic |
| Paths at depth 2 and 3 | 0 (worded as "no modelled path", never "safe") |
| Paths at depth 4 | 1, through `svc-legacy-etl` |
| Paths at depth 8 | 19 |
| Decoy edge `role-prod-admin -> prod-customer-db` (e026) | on 15 paths, disruption 9 |
| Best edge `role-ci-deployer -> role-prod-admin` (e023) | on 11 paths, disruption 2 |
| Plan, budget 3 | 2 edges, cuts 19 of 19, total disruption 5 |
| Simulation on a scratch graph | 19 paths before, 0 after, scratch graph deleted |
| After rejecting e023 and re-planning | 15 of 19 cut, total disruption 6, 4 remain |

## Script
| Time | Scene | Narration (spoken) | On screen |
|---|---|---|---|
{chr(10).join(rows)}

## The chat scene
Three prompts, all read-only for the graph except that they update the console like the buttons do:
1. "Can intern-laptop reach prod-customer-db?" calls `explain_reachability` and shows the 5-hop path.
2. "Plan a fix with budget 3 and simulate it." calls `plan_remediation` first, then `simulate_fix` with **that plan's edges** (enforced in code).
3. "Is srv-alpha-01 safe?" calls `explain_reachability` with only the source, which checks every crown jewel; the answer is "no modelled path" plus the plain statement that this is not a claim of safety (added in code if the model leaves it out).

The model picks from the fixed tool catalogue over MCP and never writes Cypher; the answer checker rejects any sentence that names an asset the tools did not return, calls something safe, or claims a verified fix while paths remain. If the free-tier model were rate limited the recorder would stop and report it (it does not silently switch to router mode on camera).

## Voice
Used: **{voice['name']}** (ElevenLabs premade voice).
Requested: **{voice['requested']['name']}**. That is a Voice Library voice, and ElevenLabs answered HTTP 402 (free plans cannot use library voices through the API). To switch: upgrade or add $5 of credits, set `voice` in `demo/narration.json` to the requested one, then run the steps below.

## Re-make the video
```bash
python demo/make_narration.py --force      # voiceover clips (needs ELEVENLABS_API_KEY in .env), writes demo/audio/
python demo/reset_live.py                  # clean demo graph (needs RESET_TOKEN in .env; never shown on screen)
python demo/record_demo.py                 # records the live site and mixes the audio -> demo/chokepoint-demo.mp4
python demo/verify_video.py                # one frame per segment + contact sheets for a visual check
python demo/reset_live.py                  # leave the live graph clean for visitors
```
Generated media (`demo/*.mp4`, `demo/audio/`, `demo/video/`, `demo/frames/`) and the design-reference video `ui/` are git-ignored.
The recorder writes decisions to the live graph (propose and reject), which is why the graph is reset before and after.
"""
(ROOT.parent / "docs" / "DEMO_SCRIPT.md").write_text(doc, encoding="utf-8")
print(f"wrote docs/DEMO_SCRIPT.md ({len(doc)} chars, {len(rows)} rows)")
