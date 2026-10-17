import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Nav, REPO_URL } from "./landing/Nav";
import { Hero } from "./landing/Hero";
import { Statement } from "./landing/Statement";
import { Steps } from "./landing/Steps";

// The console (graph library, panels, chat) is a separate chunk, fetched shortly before it scrolls
// into view, so the first load only carries the landing section.
const Console = lazy(() => import("./console/Console"));

function ConsoleSlot() {
  const ref = useRef<HTMLElement>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.location.hash === "#console") setNear(true);
    const io = new IntersectionObserver(
      (entries) => entries.some((e) => e.isIntersecting) && (setNear(true), io.disconnect()),
      { rootMargin: "900px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <section ref={ref} id="console" className="console-slot">
      {near ? (
        <Suspense fallback={<div className="console-loading">Loading the console…</div>}>
          <Console />
        </Suspense>
      ) : (
        <div className="console-loading">Console</div>
      )}
    </section>
  );
}

export function App() {
  return (
    <>
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
    </>
  );
}
