import { useEffect, useState } from "react";

export const REPO_URL = "https://github.com/Im-2/chokepoint";

/** Full-width transparent bar at the top; after a little scrolling it condenses into a floating pill. */
export function Nav() {
  const [condensed, setCondensed] = useState(false);
  useEffect(() => {
    const onScroll = () => setCondensed(window.scrollY > 80);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={`nav ${condensed ? "nav--pill" : ""}`}>
      <nav className="nav__inner" aria-label="Main">
        <a className="nav__logo" href="#top" aria-label="Chokepoint home"><em>Chokepoint</em></a>
        <div className="nav__links">
          <a href="#how">How it works</a>
          <a href="#console">Console</a>
          <a href={REPO_URL} target="_blank" rel="noreferrer">GitHub</a>
        </div>
        <a className="btn btn--cta btn--small" href="#console">Launch console</a>
      </nav>
    </header>
  );
}
