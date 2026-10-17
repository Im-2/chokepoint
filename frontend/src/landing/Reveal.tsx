import { createElement, useEffect, useRef, useState, type ReactNode } from "react";

/** Fade-up on first sight (opacity 0 to 1, 24px rise, about 700 ms). Plain IntersectionObserver + CSS. */
export function Reveal({ as = "div", className = "", children }: { as?: "div" | "h2" | "p"; className?: string; children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => entry.isIntersecting && (setSeen(true), io.disconnect()), { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return createElement(as, { ref, className: `reveal ${seen ? "reveal--in" : ""} ${className}` }, children);
}
