import { useEffect, useRef, useState } from "react";
import type { Snapshot } from "./AnalysisPanel";
import { CollegeSelect } from "./CollegeSelect";
import { StudentAlerts } from "./ProcessAlerts";

const stages = [
  { key: "courses", label: "课程" },
  { key: "topic", label: "选题" },
  { key: "midterm", label: "中期" },
];

type Outcome = { snapshot: Snapshot } | { error: string };
type Scope = { college: string; major: string; grade: string };

export function CultivationOverview({ csrf, onSnapshots, showSnapshot }: {
  csrf: string;
  onSnapshots: (snapshots: Snapshot[]) => void;
  showSnapshot: (snapshot: Snapshot) => void;
}) {
  const [college, setCollege] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ scope: Scope; outcomes: Outcome[] }>();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => { if (result) heading.current?.focus(); }, [result]);

  async function load(scope: Scope) {
    if (!scope.college) {
      setError("请先选择学院。");
      return;
    }
    setRunning(true);
    setError("");
    setResult(undefined);
    const outcomes: Outcome[] = [];
    for (const stage of stages) {
      try {
        const response = await fetch(`/api/analyses/${stage.key}`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify(scope),
        });
        const data = await response.json();
        outcomes.push(response.ok ? { snapshot: data } : {
          error: typeof data.detail === "string" ? data.detail : "分析失败，请检查所选范围。",
        });
      } catch {
        outcomes.push({ error: "加载失败，请稍后重试。" });
      }
    }
    onSnapshots(outcomes.flatMap((item) => "snapshot" in item ? [item.snapshot] : []));
    setResult({ scope, outcomes });
    setRunning(false);
  }

  const snapshots = result?.outcomes.flatMap((item) => "snapshot" in item ? [item.snapshot] : []) ?? [];
  return (
    <>
      <form className="cultivation-scope" onSubmit={(event) => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        void load({ college: college.trim(), major: String(fields.get("major")).trim(), grade: String(fields.get("grade")) });
      }}>
        <fieldset disabled={running}>
          <legend>选择要查看的学生范围</legend>
          <CollegeSelect label="学生所在学院" value={college} onChange={(value) => {
            setCollege(value);
            setError("");
          }} required />
          <label>专业（可选）<input name="major" placeholder="留空查看授权范围内的全部专业" /></label>
          <label>入学年份（可选）<input aria-label="总览入学年份" name="grade" type="number" min="1900" max="2100" /></label>
          <button>查看培养概况</button>
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
      {running && <p role="status">正在分析同一范围的课程、选题和中期。</p>}
      {result && (
        <>
          <h3 ref={heading} tabIndex={-1}>培养概况</h3>
          <p>{result.scope.college} · {result.scope.major || "授权范围内的专业"} · {result.scope.grade ? `${result.scope.grade} 级` : "全部年级"}</p>
          <div className="cultivation-stages">
            {result.outcomes.map((outcome, index) => {
              const stage = stages[index];
              return (
                <article className="card" key={stage.key}>
                  <h4>{stage.label}</h4>
                  {"error" in outcome ? <p>{outcome.error}</p> : (
                    <>
                      {outcome.snapshot.result.assessment_count === 0 ? <p>当前范围暂无可分析记录。</p> : (
                        <>
                          <p>{outcome.snapshot.result.student_count} 人 · {outcome.snapshot.result.assessment_count} 条考核记录</p>
                          <p>{outcome.snapshot.result.pass_rate === null ? "通过率暂无数据" : `通过率 ${outcome.snapshot.result.pass_rate}%`}</p>
                          <p>未通过 {outcome.snapshot.result.failed} 条 · 状态未知 {outcome.snapshot.result.unknown} 条</p>
                        </>
                      )}
                      <button type="button" className="secondary" onClick={() => showSnapshot(outcome.snapshot)}>查看{stage.label}明细</button>
                    </>
                  )}
                </article>
              );
            })}
          </div>
          {snapshots.length > 0 && (
            <>
              {snapshots.length < stages.length && <p>有环节未能完成分析，关注清单仅覆盖已返回的结果。</p>}
              <StudentAlerts snapshots={snapshots} />
            </>
          )}
        </>
      )}
    </>
  );
}
