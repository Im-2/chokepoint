# UI spec: style and motion for the Chokepoint site and console

Derived from a style reference video (20 s screen recording, 580×434, scrolling a marketing page).
**Only style and motion are taken.** No brand name, logo, imagery, people, client logos or copy from
the video is used; Chokepoint has its own wording, and its imagery is generated (CSS gradients, SVG).
The video itself is git-ignored (`ui/`) and never committed.

**Method.** Frames at 1 fps (20) plus 4 fps around the one complex transition, cropped to the page
viewport. Colours marked **S** were sampled from pixels (the video is compressed, so values are
approximate); **E** are estimates from the frames; **C** are my choices for Chokepoint.
Durations are **not measurable** from a scroll recording (most motion is tied to scroll position, not
time), so the timings below are recommended values, marked **C**.

## 1. Storyboard (what happens, in order)
| t | Frame | Pattern |
|---|---|---|
| 0 s | Full-bleed red-orange gradient hero, centred serif headline, small sans sub-line, tiny meta text in the corners, full-width transparent nav (logo left, 3 links centre, white CTA right) | hero |
| 1 s | Scrolling shrinks the hero into an inset rounded rectangle; nav is still a bar | scroll-linked hero shrink |
| 2–3 s | Black page, large centred serif statement. Words/letters brighten in sequence as you scroll (the lines below are still dim). Row of logos beneath. Nav is now a floating dark pill | scroll-linked text reveal |
| 4 s | A red media panel rises from below and scales to about 60 % width | media panel |
| 4–5 s | Heading fades in ("... in your journey?", one italic word); the panel splits into 3 vertical slices that rotate in 3D and open into 3 tilted cards (light, red, dark) | one-off flourish |
| 5–8 s | Service rows: index label + sans title (left), list (centre), rounded media thumbnail (right), hairline separators; rows ease in as they scroll | list rows |
| 8–9 s | Huge serif heading, first word italic, soft white glow | display heading |
| 9–10 s | Media carousel: centre card full, neighbours dimmed, round arrow buttons | carousel |
| 10 s | Logo grid 6 columns, low opacity until hover | grid |
| 11–13 s | Heading + quote carousel (portrait left, quote right), dot pagination in a small pill | carousel |
| 13–14 s | Three stats: large serif numeral with "+" and a small sans caption | stats |
| 14 s | Heading + two cards tilted ±3° with a red-ringed avatar | tilted cards |
| 15 s | Rounded media expands to full-bleed red image with centred text over it | closing hero (mirrors hero) |

## 2. Colour (hex)
**Base and surfaces** — near-black page, surfaces barely lighter.
| Token | Hex | Source |
|---|---|---|
| `--bg` page | `#000000` (use `#050505` for less harsh) | S `#000000` |
| `--surface` card | `#0c0c09` → use `#0d0d0d` | S `#0c0c09` |
| `--surface-2` team card / panel | `#111110` → `#121212` | S `#111110` |
| `--pill` nav | `#272627` at ~85 % with backdrop blur | S `#272627` |
| `--hairline` | `rgba(255,255,255,0.08)` | E |

**Text tiers** (scroll reveal moves text from dim to lit):
| Token | Hex | Source |
|---|---|---|
| `--text-display` | `#fafaf5` (warm white) | S |
| `--text` lit | `#e8e8e8` | S |
| `--text-muted` | `#808080` (quote text) | S |
| `--text-dim` (unrevealed) | `#49484b` | S |
| `--cta-bg` / `--cta-text` | `#f2efe8` / `#0a0a0a` | E |
Accessibility: `#4a4a4a` on black is about 2.2:1, so it is used **only for not-yet-revealed text**.
UI text never goes below `#8a8a8a` (about 6:1).

**Red-orange gradient** (hero and closing only), sampled stops:
`#f85111` (top glow) → `#e6360c` / `#e1461a` (centre) → `#ca240a` → `#a81a09` → `#80170c` → `#6f130a`
→ `#49110b` → `#300d08` → `#060202` (edges and bottom fade to black).
Recipe **C**: `radial-gradient(ellipse 60% 50% at 50% 12%, #f85111, #ca240a 38%, #80170c 62%, #300d08 82%, #050202)`
plus a faint noise layer; the hero fades into `--bg` at the bottom.

**Chokepoint semantics (C)** — two accents only:
| Meaning | Colour |
|---|---|
| Attack path, entry point, danger, decoy outline | red `#ff4a2b` (glow `rgba(255,74,43,.35)`) |
| Fix, verified, approved, "cut" edge confirmation | teal `#3ddbc0` (dim `#1f7f70`) |
| Neutral graph, ordinary nodes/edges | greys `#3a3a3a` / `#6b6b6b` |
Everything else (badges for the 7 outcomes) is built from these two accents plus neutrals, with the
outcome shown in text as well as colour.

## 3. Typography
| Role | Look in the video | Free font (C) |
|---|---|---|
| Display / headlines / big numerals | high-contrast editorial serif, tight leading (about 0.95–1.05), slight negative tracking, **one italic word per headline** | **Instrument Serif** (regular + italic) |
| UI, labels, body, nav | neutral grotesque sans | **Inter** (system-ui fallback) |
| Trace, ids, config diff (console) | n/a (added) | **JetBrains Mono** or `ui-monospace` |
Scale **E/C**: hero h1 `clamp(40px, 6.2vw, 92px)`; statement `clamp(24px, 3.1vw, 46px)` at line-height
1.12, width about 62 % of the viewport, 4 lines; section display `clamp(52px, 8vw, 120px)`; UI 12–14 px;
labels 11 px uppercase with 0.08em tracking. Italic emphasis is a style swap inside the same face
(`<em>`), never a different colour.

## 4. Layout and spacing
- Landing: content centred, narrow measure; side margins about 12–18 % on wide screens; large vertical
  rhythm (about 30–40 vh between sections).
- Service-style rows (reusable for the three-step section): 3 columns about `1 : 1.3 : 1` (label, text,
  media), hairline between rows, 48–64 px vertical padding.
- Radii: page frames 24 px; cards 14–16 px; media thumbnails 6–8 px; nav pill about 12 px (rounded
  rectangle, not a full capsule); buttons 6–8 px; avatars full circle.
- Nav: floating, centred, about 38 % of viewport width, 40–44 px tall, 8–12 px from the top; inside it
  logo left, links centre, one white CTA right.
- Console (C): 12-column grid, 8 px base unit, panels 16 px padding, hairline borders instead of shadows.

## 5. Components
| Component | Style |
|---|---|
| Floating pill nav | `--pill` background, backdrop blur 12–16 px, 1 px hairline; at scroll 0 it is a transparent full-width bar, after about 80 px it condenses into the pill |
| White CTA | `--cta-bg` fill, dark text 12–13 px weight 500, radius 6–8 px; hover: slight lift (translateY -1 px) and brightness +4 % |
| Display heading | serif, one `<em>` word, optional soft glow `text-shadow: 0 0 40px rgba(255,255,255,.18)` on entry |
| Scroll-linked statement | each word is a span whose colour goes `--text-dim` → `--text` with scroll progress |
| Media panel / rounded card | `border-radius` 14–16 px, overflow hidden, starts smaller and scales up on scroll |
| Carousel | centre card scale 1 opacity 1; neighbours scale about 0.92, opacity about 0.2 (measured luminance ratio 0.19); circular dark arrow buttons 28 px; dot pagination in a small dark pill |
| Tilted cards | `rotate(±3deg)`, `--surface-2` fill, hairline border, subtle shadow; on hover straighten toward 0° (C) |
| Stats | serif numeral 40–56 px with "+", sans caption 12 px `--text-muted` |
| Hairline list rows | index label `[01]`, sans title 16–18 px, thumbnail right, row fades in on scroll |
| Logo/tag grid | `--text-dim` until hover, then `--text` (C) |

## 6. Hover, transition and scroll behaviour
| Behaviour | Value |
|---|---|
| Hover (buttons, links, rows, cards) | 150–200 ms, `ease-out`; links dim → lit; cards border `--hairline` → rgba(255,255,255,.16) |
| Reveal-on-scroll (headings, rows) | opacity 0→1 and translateY 24→0 px, **600–800 ms**, `cubic-bezier(.22,1,.36,1)`; triggered once at 20–30 % in view; stagger 60–90 ms between siblings (C) |
| Scroll-linked text brightening | progress-based (no duration): span colour interpolated over its own slice of the paragraph's scroll range; granularity word-by-word |
| Hero shrink | scroll-linked: inset 0 → about 3 %, border-radius 0 → 24 px, scale 1 → 0.96 across the first viewport of scroll |
| Media panel growth | scroll-linked: width about 55 % → 60 % while rising (the video shows it grow wide then settle) |
| Nav condense | 250–300 ms `ease-out` once scrollY passes about 80 px |
| Carousel move | 450–550 ms `ease-in-out`; drag/arrow/keyboard; neighbours animate scale and opacity together |
| Smooth scroll | the reference scrolls with inertia, so a light smooth-scroll (Lenis-style) fits **the landing section only**; the console uses native scroll |
| Reduced motion | no scroll-linked animation: text fully lit, panels static, reveals become a 150 ms fade; carousel snaps |

## 7. Reusable pattern vs one-off flourish
| Reusable (build once, use often) | One-off (use at most once, or skip) |
|---|---|
| Near-black base with hairlines | The 3D slice-and-tilt panel opening (best candidate for the "three steps" moment) |
| Serif display + italic word + Inter UI | Hero shrinking into an inset frame |
| Floating pill nav with white CTA | Closing full-bleed media expansion |
| Scroll-linked text brightening | Soft glow on one big heading |
| Fade-up reveals with stagger | Logo/client strip (Chokepoint has none) |
| Rounded cards, carousel with dimmed neighbours | Counter stats band |
| Subtle card tilt | |

## 8. How this maps to Chokepoint (C)
- **Landing hero:** red-orange gradient hero, serif headline with one italic word, one-line pitch,
  white "Launch console" CTA. Imagery is a CSS gradient plus a faint generated node-link line drawing in
  SVG; nothing from the video.
- **Three-step scroll section** ("Find paths · Pick the fix · Prove it"): scroll-linked brightening
  statement, then three cards that tilt in 3D as they enter (the one reuse of the flourish).
- **Console:** `--bg` black, panels `--surface` with hairlines. Red = attack paths and the decoy
  outline; teal = fixes, "cut" confirmation, verified/approved. Serif for the big before/after numbers
  (for example "19 → 0"), Inter for UI, mono for trace and the config diff. Attack-path list and
  carousel-like cards reuse the dimmed-neighbour idea for the before/after toggle.
- **Performance:** no video or photos; gradients and SVG only; fonts limited to Instrument Serif (2
  styles), Inter and one mono, loaded with `font-display: swap`; Framer Motion loaded for the landing
  section only where possible.
- **Not copied:** the brand, wordmark, hand/statue/mountain imagery, client logos, portraits, copy and layout of the original page.

## 9. As built (differences and decisions)
- Fonts are self-hosted through `@fontsource` (Instrument Serif regular + italic, Inter variable, JetBrains Mono): no external font requests.
- Scroll-linked effects use Framer Motion (`useScroll` / `useTransform`): hero shrink, word-by-word statement brightening, step cards swinging in with a 3D rotation. The lightweight `m` components need `LazyMotion` to render motion values, so the features load as a small async chunk.
- No smooth-scroll library: the reference's inertia was not needed; `scroll-behavior: smooth` is used for anchors, and everything is switched off under `prefers-reduced-motion`.
- The console and its graph library are a separate chunk, fetched shortly before the console scrolls into view; the first load carries only the landing section (about 100 KB of gzipped JavaScript).
- Colour semantics as specified: red for attack paths, entry points and the decoy; teal for fixes, cut edges and verified or approved states.
- Imagery is generated: a CSS gradient and a small SVG node-link drawing. Nothing from the video is used.
