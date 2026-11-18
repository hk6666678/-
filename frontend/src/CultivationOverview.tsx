import { useEffect, useRef, useState } from "react";
import type { Snapshot } from "./AnalysisPanel";
import { StudentAlerts } from "./ProcessAlerts";

const stages = [
  { key: "courses", label: "课程" },
  { key: "topic", label: "选题" },
  { key: "midterm", label: "中期" },
];

type Outcome = { snapshot: Snapshot } | { error: string };
type Scope = { college: string; major: string; student_id: number };
type Student = { id: number; research_id: string; name?: string; data: Record<string, string> };
const pageSize = 50;

function studentLabel(student: Student) {
  return [student.name, student.research_id, student.data["所属学院"], student.data["专业"]].filter(Boolean).join(" · ");
}

export function CultivationOverview({ csrf, showSnapshot }: {
  csrf: string;
  showSnapshot: (snapshot: Snapshot | null) => void;
}) {
  const [page, setPage] = useState(0);
  const [roster, setRoster] = useState<{ items: Student[]; total: number }>();
  const [rosterError, setRosterError] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ student: Student; outcomes: Outcome[] }>();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => { if (result) heading.current?.focus(); }, [result]);
  useEffect(() => {
    const controller = new AbortController();
    setRoster(undefined);
    setRosterError(false);
    void fetch(`/api/students?limit=${pageSize}&offset=${page * pageSize}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(setRoster)
      .catch(() => { if (!controller.signal.aborted) setRosterError(true); });
    return () => controller.abort();
  }, [page]);

  async function load(scope: Scope, student: Student) {
    setRunning(true);
    setResult(undefined);
    showSnapshot(null);
    const outcomes: Outcome[] = [];
    for (const stage of stages) {
      try {
        const response = await fetch(`/api/analyses/${stage.key}`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify(scope),
        });
        const data = await response.json();
        if (response.ok && data.scope?.student_id === scope.student_id) {
          outcomes.push({ snapshot: data });
        } else {
          outcomes.push({ error: typeof data.detail === "string" ? data.detail : "未取得该学生的分析结果，请刷新后重试。" });
        }
      } catch {
        outcomes.push({ error: "加载失败，请稍后重试。" });
      }
    }
    setResult({ student, outcomes });
    setRunning(false);
  }

  function changePage(next: number) {
    setStudentId("");
    setResult(undefined);
    showSnapshot(null);
    setPage(next);
  }

  const snapshots = result?.outcomes.flatMap((item) => "snapshot" in item ? [item.snapshot] : []) ?? [];
  return (
    <>
      <form className="cultivation-scope" onSubmit={(event) => {
        event.preventDefault();
        const student = roster?.items.find((item) => String(item.id) === studentId);
        if (student) void load({
          college: student.data["所属学院"], major: student.data["专业"], student_id: student.id,
        }, student);
      }}>
        <fieldset disabled={running}>
          <label>研究生
            <select aria-label="研究生" value={studentId} onChange={(event) => {
              setStudentId(event.target.value);
              setResult(undefined);
              showSnapshot(null);
            }} required disabled={!roster?.items.length}>
              <option value="">请选择研究生</option>
              {roster?.items.map((student) => <option key={student.id} value={student.id}>{studentLabel(student)}</option>)}
            </select>
          </label>
          {rosterError ? <p role="alert">无法读取学生档案，请核对账号是否有基础档案查看权限。</p>
            : !roster ? <p role="status">正在读取授权范围内的学生</p>
            : roster.total === 0 ? <p>授权范围内暂无学生档案。</p> : null}
          {roster && roster.total > pageSize && <div>
            <button type="button" disabled={page === 0} onClick={() => changePage(page - 1)}>上一页</button>
            <button type="button" disabled={(page + 1) * pageSize >= roster.total} onClick={() => changePage(page + 1)}>下一页</button>
            <p>第 {page + 1}/{Math.ceil(roster.total / pageSize)} 页</p>
          </div>}
          <button disabled={!studentId}>查看培养过程</button>
        </fieldset>
      </form>
      {running && <p role="status">正在分析课程、选题和中期。</p>}
      {result && (
        <>
          <h3 ref={heading} tabIndex={-1}>个人培养过程</h3>
          <p>{studentLabel(result.student)}</p>
          <div className="cultivation-stages">
            {result.outcomes.map((outcome, index) => {
              const stage = stages[index];
              return (
                <article className="card" key={stage.key}>
                  <h4>{stage.label}</h4>
                  {"error" in outcome ? <p>{outcome.error}</p> : (
                    <>
                      {outcome.snapshot.result.assessment_count === 0 ? <p>该学生暂无可分析记录。</p> : (
                        <>
                          <p>{outcome.snapshot.result.assessment_count} 条考核记录</p>
                          <p>{outcome.snapshot.result.pass_rate === null ? "通过率暂无数据" : `通过率 ${outcome.snapshot.result.pass_rate}%`}</p>
                          <p>未通过 {outcome.snapshot.result.failed} 条 · 状态未知 {outcome.snapshot.result.unknown} 条</p>
                          {stage.key === "courses" && (() => {
                            const progress = outcome.snapshot.result.credit_progress?.students?.[0];
                            return <p>{progress ? `已获 ${progress.earned_credits} 学分 · 完成 ${progress.progress_percent}%` : "学分进度暂不可计算，查看明细了解缺项。"}</p>;
                          })()}
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
