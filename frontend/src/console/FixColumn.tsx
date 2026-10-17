import { MemoryList } from "./MemoryList";
import { PlanCard, ProposalCard, SimulationCard } from "./FixPanels";

/** The plan, its proof, the change record and the memory, in the order the story goes. */
export function FixPanelsColumn() {
  return (
    <>
      <PlanCard />
      <SimulationCard />
      <ProposalCard />
      <MemoryList />
    </>
  );
}
