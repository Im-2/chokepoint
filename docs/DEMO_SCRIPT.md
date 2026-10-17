# Demo video script (about 3.8 minutes)

A real, unedited run against the live site, https://trychokepoint.vercel.app, recorded by `demo/record_demo.py`
(Playwright, Chromium, 1920x1080, visible cursor, slow scrolling). Captions and the end card are overlays; every
result on screen comes from the live API and is asserted by the recorder as it goes (a wrong number aborts the take).
**The voiceover is AI-generated** (ElevenLabs) and the video says so in its first caption and on the end card.

Length: 3:46 of video with 211 s of speech. The chat scene ("Ask Chokepoint") is about 35 s.

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
| 0:00 | Landing | This is Chokepoint. One thing first: this voiceover is AI-generated. Everything you see on screen is the real product, running live, and none of the results are edited. | Landing hero. Caption: the voiceover is AI-generated and this is a real run on the live site. |
| 0:12 | Landing | Every company has crown-jewel data, like a customer database. The hard question is simple: how could an attacker actually get there, and what is the smallest change that stops them? A spreadsheet of permissions cannot answer that. A graph can. | Slow scroll; the statement brightens word by word (scroll-linked). |
| 0:28 | Console | This is a synthetic cloud: one hundred and thirty assets and three hundred and twenty-two attack edges, stored in FalkorDB, the primary database behind everything you will see. Assets are nodes. Every possible pivot is an edge, with a cost and a disruption score. | The three step cards, then the console. Hover the stat tiles (130 assets, 322 connections) and the graph. |
| 0:45 | Depth contrast | Scan two hops, and there is nothing. Zero paths. Three hops, still zero. But read the wording. No modelled path is not the same as safe. | Slider to 2, **Scan**: 'No modelled attack path within 2 hops ... not a statement that the asset is safe'. Slider to 3, **Scan**: same. |
| 0:56 | Depth contrast | At four hops, one path appears. It runs through svc-legacy-etl, a forgotten service account that nobody had modelled as dangerous. It assumes a deploy role, which assumes an admin role, which reaches the customer database. Go deeper, to eight hops, and there are nineteen paths. | Slider to 4, **Scan**: 1 path through `svc-legacy-etl`, highlighted on the graph. Slider to 8, **Scan**: 19 paths; click the shortest. |
| 1:16 | Choke edges | Which edge do we fix? Rank by paths through it, and you get this one: fifteen paths. But its disruption is nine out of ten. Cut it, and you break production. That is the decoy. Rank by paths cut per unit of disruption, and another edge wins: eleven paths, at a disruption of two. | **Rank choke edges**. The decoy row (15 paths, disruption 9) is hovered and clicked, then the best row (11 paths, disruption 2). |
| 1:37 | Plan and simulate | The planner picks two edges. Together they cut all nineteen paths, at a total disruption of five. It says plainly that this is a greedy heuristic, not a proof. So we prove it: copy the graph, apply the fix to the copy, search again. Nineteen paths before. Zero after. The copy is deleted. | **Plan remediation** (2 edges, 19 of 19, disruption 5), **Simulate on a scratch copy** (19 to 0, scratch graph deleted), toggle Before / After. |
| 1:57 | Ask Chokepoint | Now the same graph, through chat. Ask Chokepoint. | Open the docked chat, 'Ask Chokepoint'. |
| 2:02 | Ask Chokepoint | The model can only choose from a fixed catalogue of tools, over the Model Context Protocol. It never writes Cypher. Here it picks the reachability tool, and gets the five-hop path. | Click the suggested prompt 'Can intern-laptop reach prod-customer-db?': tool chip `explain_reachability`, the 5-hop path, 'checked' badge. |
| 2:13 | Ask Chokepoint | Next, plan and simulate. It plans first, then simulates exactly the edges the plan chose, and the trace fills with every query. | Open the Trace panel. Prompt 'Plan a fix with budget 3 and simulate it.': `plan_remediation` then `simulate_fix`; the trace fills with every query. |
| 2:22 | Ask Chokepoint | Now the honest one. Is this machine safe? No path is modelled, and that is not a statement that it is safe. An answer checker rejects any sentence naming an asset the graph did not return. | Prompt 'Is srv-alpha-01 safe?': 'no modelled path ... not a statement that the asset is safe'. |
| 2:34 | Human decision | Back to the fix. Propose just the first edge. A change record is written, with an owning team found by traversing the graph, a ticket, and a config diff. Only a person can approve or reject. I reject it, with a reason: C I needs prod-admin during releases. | Close the chat. **Propose only this edge** on the first plan step (e023): ticket, owner team, config diff. **Reject...**, type the reason, **Reject with reason**. |
| 2:53 | Memory | Now re-plan. The agent reads that decision from the graph, skips the rejected edge, and finds three cheaper ones. Fifteen of nineteen paths cut, total disruption six, and it says plainly that four remain. The memory lives in the graph, so it survives restarts. | **Plan remediation** again: the rejected edge is skipped; 15 of 19 cut, disruption 6, 4 remain. Then the decision memory. |
| 3:11 | Honesty | Ask about an asset that does not exist, and you get unknown asset. No query runs at all. | Reach from `ghost-host-99`: 'Unknown asset ... Nothing was searched'; the trace shows only name lookups. |
| 3:21 | Trace and close | Every response carries its own trace. The same nine tools are an MCP server that any agent can use. FalkorDB does the work: path search, choke ranking, shortest paths, scratch-graph simulation, and decision memory. Take it away, and none of this exists. This was Chokepoint, for Graph Hacks, Track one. | Trace panel and the MCP endpoint button, then the end card. |

## The chat scene
Three prompts, all read-only for the graph except that they update the console like the buttons do:
1. "Can intern-laptop reach prod-customer-db?" calls `explain_reachability` and shows the 5-hop path.
2. "Plan a fix with budget 3 and simulate it." calls `plan_remediation` first, then `simulate_fix` with **that plan's edges** (enforced in code).
3. "Is srv-alpha-01 safe?" calls `explain_reachability` with only the source, which checks every crown jewel; the answer is "no modelled path" plus the plain statement that this is not a claim of safety (added in code if the model leaves it out).

The model picks from the fixed tool catalogue over MCP and never writes Cypher; the answer checker rejects any sentence that names an asset the tools did not return, calls something safe, or claims a verified fix while paths remain. If the free-tier model were rate limited the recorder would stop and report it (it does not silently switch to router mode on camera).

## Voice
Used: **George - Warm, Captivating Storyteller** (ElevenLabs premade voice).
Requested: **Adam Stone - Smooth and Relaxed**. That is a Voice Library voice, and ElevenLabs answered HTTP 402 (free plans cannot use library voices through the API). To switch: upgrade or add $5 of credits, set `voice` in `demo/narration.json` to the requested one, then run the steps below.

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
