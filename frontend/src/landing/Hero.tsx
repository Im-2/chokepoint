import { useRef } from "react";
import { m, useReducedMotion, useScroll, useTransform } from "framer-motion";

/** A faint generated node-link drawing (no photography): a few fixed points joined by thin lines. */
const POINTS: [number, number][] = [
  [8, 62], [20, 38], [31, 70], [43, 28], [52, 55], [63, 34], [72, 66], [84, 42], [93, 58], [14, 84], [58, 82], [78, 20],
];
const LINKS: [number, number][] = [
  [0, 1], [1, 3], [0, 2], [2, 4], [3, 4], [4, 5], [5, 7], [4, 6], [6, 8], [7, 8], [2, 9], [4, 10], [5, 11], [7, 11],
];

function NetworkArt() {
  return (
    <svg className="hero__art" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      {LINKS.map(([a, b], i) => (
        <line key={i} x1={POINTS[a][0]} y1={POINTS[a][1]} x2={POINTS[b][0]} y2={POINTS[b][1]} />
      ))}
      {POINTS.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i === 4 ? 0.9 : 0.5} />
      ))}
    </svg>
  );
}

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  // scroll-linked: the hero pulls in from the edges into a rounded frame as you scroll past it
  const inset = useTransform(scrollYProgress, [0, 0.9], ["0px", "28px"]);
  const radius = useTransform(scrollYProgress, [0, 0.9], ["0px", "28px"]);
  const copyY = useTransform(scrollYProgress, [0, 1], ["0px", "-60px"]);
  const copyOpacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);

  return (
    <section ref={ref} className="hero" id="top">
      <m.div className="hero__frame" style={reduced ? undefined : { margin: inset, borderRadius: radius }}>
        <NetworkArt />
        <m.div className="hero__copy" style={reduced ? undefined : { y: copyY, opacity: copyOpacity }}>
          <h1 className="hero__title serif">
            <span className="line">Find the <em>chokepoint</em></span>
            <span className="line">between attackers and your data</span>
          </h1>
          <p className="hero__sub">
            Chokepoint maps every route into your crown-jewel data, picks the least disruptive fix, and
            proves it on a scratch copy of the graph before anyone changes a thing.
          </p>
          <a className="btn btn--cta" href="#console">Launch console</a>
        </m.div>
        <div className="hero__meta" aria-hidden="true">
          <span>Synthetic data · FalkorDB graph</span>
          <span>Scroll to explore</span>
          <span>Graph Hacks · Track 01</span>
        </div>
      </m.div>
    </section>
  );
}
