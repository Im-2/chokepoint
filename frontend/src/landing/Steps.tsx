import { useRef } from "react";
import { m, useReducedMotion, useScroll, useTransform, type MotionValue } from "framer-motion";
import { Reveal } from "./Reveal";

interface Step { n: string; title: string; body: string; foot: string; tone: "light" | "red" | "dark"; tilt: number }

const STEPS: Step[] = [
  {
    n: "01", title: "Find paths", tone: "light", tilt: -3,
    body: "Every route from an entry point to a crown jewel, hop by hop. Scan two hops and nothing shows, which is not the same as safe. Scan four and a forgotten service account appears.",
    foot: "FalkorDB path search",
  },
  {
    n: "02", title: "Pick the fix", tone: "red", tilt: 0,
    body: "Ranking by most paths picks the edge that breaks production. Ranking by paths cut per unit of disruption picks the cheap one. The plan says plainly that it is greedy, not optimal.",
    foot: "Greedy set cover over graph paths",
  },
  {
    n: "03", title: "Prove it", tone: "dark", tilt: 3,
    body: "The graph is copied, the fix is applied to the copy and the search is re-run: 19 paths before, 0 after. The copy is deleted. A human approves or rejects, and the graph remembers.",
    foot: "Scratch graph, then human decision",
  },
];

function StepCard({ step, progress, index, reduced }: {
  step: Step; progress: MotionValue<number>; index: number; reduced: boolean | null;
}) {
  // scroll-linked: cards swing in from a steep angle and settle at their resting tilt
  const start = index * 0.08;
  const rotateY = useTransform(progress, [start, start + 0.5], [index === 1 ? 0 : (index === 0 ? 38 : -38), 0]);
  const y = useTransform(progress, [start, start + 0.5], [80, 0]);
  const opacity = useTransform(progress, [start, start + 0.3], [0, 1]);
  return (
    <m.article
      className={`step step--${step.tone}`}
      style={reduced ? { rotate: step.tilt } : { rotateY, y, opacity, rotate: step.tilt }}
    >
      <span className="step__n">{step.n}</span>
      <h3 className="step__title serif">{step.title}</h3>
      <p className="step__body">{step.body}</p>
      <span className="step__foot">{step.foot}</span>
    </m.article>
  );
}

export function Steps() {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.95", "start 0.3"] });
  return (
    <section className="steps" id="how">
      <Reveal as="h2" className="steps__title serif">
        Find paths. Pick the fix. <em>Prove</em> it.
      </Reveal>
      <div className="steps__cards" ref={ref}>
        {STEPS.map((s, i) => (
          <StepCard key={s.n} step={s} progress={scrollYProgress} index={i} reduced={reduced} />
        ))}
      </div>
    </section>
  );
}
