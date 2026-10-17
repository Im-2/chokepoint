import { LazyMotion } from "framer-motion";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Nav, REPO_URL } from "./landing/Nav";
import { Hero } from "./landing/Hero";
import { Statement } from "./landing/Statement";
import { Steps } from "./landing/Steps";

// The console (graph library, panels, chat) is a separate chunk, fetched shortly before it scrolls
// into view, so the first load only carries the landing section.
const Console = lazy(() => import("./console/Console"));
// The lightweight `m` components need their animation features loaded; they arrive as a small
// separate chunk right after first paint, so the landing page itself stays light.
const loadMotionFeatures = () => import("framer-motion").then((mod) => mod.domAnimation);

function ConsoleSlot() {
  const ref = useRef<HTMLElement>(null);
  const [near, setNear] = useState(false);
  const wantScroll = useRef(false);
  // when the page was opened at #console, or a "Launch console" link was used before the console had
  // loaded, scroll to it once it exists (otherwise the layout shift leaves you above it)
  const onReady = useCallback(() => {
    if (wantScroll.current) {
      wantScroll.current = false;
      requestAnimationFrame(() => ref.current?.scrollIntoView());
    }
  }, []);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const request = () => { wantScroll.current = true; setNear(true); };
    if (window.location.hash === "#console") request();
    const onClick = (e: MouseEvent) => {
      if ((e.target as HTMLElement).closest('a[href="#console"]')) request();
    };
    document.addEventListener("click", onClick);
    const io = new IntersectionObserver(
      (entries) => entries.some((e) => e.isIntersecting) && (setNear(true), io.disconnect()),
      { rootMargin: "900px 0px" },
    );
    io.observe(el);
    return () => { io.disconnect(); document.removeEventListener("click", onClick); };
  }, []);
  return (
    <section ref={ref} id="console" className="console-slot">
      {near ? (
        <Suspense fallback={<div className="console-loading">Loading the console…</div>}>
          <Console onReady={onReady} />
        </Suspense>
      ) : (
        <div className="console-loading">Console</div>
      )}
    </section>
  );
}

export function App() {
  return (
    <LazyMotion features={loadMotionFeatures} strict>
      <Nav />
      <main>
        <Hero />
        <Statement />
        <Steps />
        <ConsoleSlot />
      </main>
      <footer className="footer">
        Chokepoint · Graph Hacks Track 01 · synthetic data only ·{" "}
        <a href={REPO_URL} target="_blank" rel="noreferrer">source on GitHub</a>
      </footer>
    </LazyMotion>
  );
}
