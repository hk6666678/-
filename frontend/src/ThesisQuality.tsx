import { useRef, useState } from "react";
import { CandidatePanel } from "./CandidatePanel";
import { ComparisonPanel } from "./ComparisonPanel";
export function ThesisQuality({ csrf }: { csrf: string }) {
  const [fresh, setFresh] = useState<{ id: number; key: number }>({
    id: 0,
    key: 0,
  });
  const recommendation = useRef<HTMLDetailsElement>(null);
  return (
    <>
      <ComparisonPanel
        csrf={csrf}
        onCreated={(id) => {
          setFresh((prev) => ({ id, key: prev.key + 1 }));
          if (recommendation.current) recommendation.current.open = true;
        }}
      />
      <details className="card task-details" ref={recommendation}>
        <summary>优秀论文候选推荐</summary>
        <CandidatePanel csrf={csrf} freshComparison={fresh} />
      </details>
    </>
  );
}
