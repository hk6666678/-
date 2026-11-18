import { useState } from "react";
import { CandidatePanel } from "./CandidatePanel";
import { ComparisonPanel } from "./ComparisonPanel";
export function ThesisQuality({ csrf }: { csrf: string }) {
  const [fresh, setFresh] = useState<{ id: number; key: number }>({
    id: 0,
    key: 0,
  });
  return (
    <>
      <ComparisonPanel
        csrf={csrf}
        onCreated={(id) => setFresh((prev) => ({ id, key: prev.key + 1 }))}
      />
      <CandidatePanel csrf={csrf} freshComparison={fresh} />
    </>
  );
}
