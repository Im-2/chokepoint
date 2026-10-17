import { useEffect } from "react";
import "../styles/console.css";
import { StoreProvider } from "../store";
import { ChatDock } from "./ChatDock";
import { ChokeTable, PathList } from "./ResultPanels";
import { Controls } from "./Controls";
import { ConsoleHeader } from "./Header";
import { FixPanelsColumn } from "./FixColumn";
import { GraphCanvas } from "./GraphCanvas";
import { TracePanel } from "./TracePanel";

export default function Console({ onReady }: { onReady?: () => void }) {
  useEffect(() => { onReady?.(); }, [onReady]);
  return (
    <StoreProvider>
      <div className="console">
        <ConsoleHeader />
        <div className="console__grid">
          <aside className="console__left" aria-label="Controls"><Controls /></aside>
          <div className="console__centre">
            <GraphCanvas />
            <TracePanel />
          </div>
          <aside className="console__right" aria-label="Results">
            <PathList />
            <ChokeTable />
            <FixPanelsColumn />
          </aside>
        </div>
        <ChatDock />
      </div>
    </StoreProvider>
  );
}
