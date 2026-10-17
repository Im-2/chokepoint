import { useRef } from "react";
import { m, useReducedMotion, useScroll, useTransform, type MotionValue } from "framer-motion";

const TEXT =
  "Chokepoint traces every route from the internet to your crown-jewel data, chooses the fix that " +
  "disrupts the business least, and proves it on a copy of the graph, so a human can approve a change " +
  "they can trust.";

const DIM = "#49484b";
const LIT = "#e8e8e8";

function Word({ word, progress, start, end, reduced }: {
  word: string; progress: MotionValue<number>; start: number; end: number; reduced: boolean | null;
}) {
  // scroll-linked: each word goes from dim to lit over its own slice of the section's scroll range
  const color = useTransform(progress, [start, end], [DIM, LIT]);
  return <m.span style={{ color: reduced ? LIT : color }}>{word} </m.span>;
}

export function Statement() {
  const ref = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.8", "end 0.55"] });
  const words = TEXT.split(" ");
  return (
    <section ref={ref} className="statement" aria-label="What Chokepoint does">
      <p className="statement__text serif">
        {words.map((w, i) => (
          <Word key={i} word={w} progress={scrollYProgress} start={(i / words.length) * 0.85}
            end={(i / words.length) * 0.85 + 0.15} reduced={reduced} />
        ))}
      </p>
    </section>
  );
}
