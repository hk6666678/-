import { useState } from "react";
import { ResearchOutputs } from "./ResearchOutputs";
const CATEGORIES: [string, string][] = [
  ["research_outputs", "科研论文"],
  ["patents", "专利"],
  ["awards", "获奖项目"],
  ["conferences", "会议"],
];
export function OutputsTabs({ csrf }: { csrf: string }) {
  const [category, setCategory] = useState("research_outputs");
  return (
    <>
      <div className="outputs-tabs" role="tablist" aria-label="成果类别">
        {CATEGORIES.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={category === key}
            className={category === key ? "active" : ""}
            onClick={() => setCategory(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <ResearchOutputs key={category} category={category} csrf={csrf} />
    </>
  );
}
