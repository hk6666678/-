import { useEffect, useRef, useState } from "react";
import type { Snapshot } from "./AnalysisPanel";
import { StudentAlerts } from "./ProcessAlerts";
import { MentorCourseComparison } from "./MentorCourseComparison";

const stages = [
  { key: "courses", label: "课程" },
  { key: "topic", label: "选题" },
  { key: "midterm", label: "中期" },
];

type Outcome = { snapshot: Snapshot } | { error: string };
type Scope = { college: string; major: string; student_id: number };
type Student = { id: number; research_id: string; name?: string; student_number?: string; data: Record<string, string> };
type Signals = {
  course_trend?: { signal: string; baseline_count: number; limits?: [number, number]; observations: { term: string; mean: number; records: number }[] };
  milestone_trends?: { label: string; signal: string; limits?: [number, number]; observations: { date: string; mean: number; record_ids: number[] }[] }[];
  blind_review?: { batch: string; due: string; status: string };
  mobility?: { type: string; date?: string } | null;
  peer_outputs?: { count: number; peer_median: number; peer_count: number; below: boolean; sources: string[] };
  notice?: string;
};
const pageSize = 50;

function studentLabel(student: Student) {
  return [student.name, student.student_number || student.research_id, student.data["所属学院"], student.data["专业"]].filter(Boolean).join(" · ");
}

export function CultivationOverview({ csrf, showSnapshot }: {
  csrf: string;
  showSnapshot: (snapshot: Snapshot | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [roster, setRoster] = useState<{ items: Student[]; total: number }>();
  const [rosterError, setRosterError] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ student: Student; outcomes: Outcome[]; signals: Signals }>();
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => { if (result) heading.current?.focus(); }, [result]);
  useEffect(() => {
    const controller = new AbortController();
    setRoster(undefined);
    setRosterError(false);
    const timer = window.setTimeout(() => {
      void fetch(`/api/students?${new URLSearchParams({ limit: String(pageSize), q: query.trim() })}`, { signal: controller.signal })
        .then((response) => {
          if (!response.ok) throw new Error();
          return response.json();
        })
        .then(setRoster)
        .catch(() => { if (!controller.signal.aborted) setRosterError(true); });
    }, query ? 250 : 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  async function load(scope: Scope, student: Student) {
    setRunning(true);
    setResult(undefined);
    showSnapshot(null);
    const signalsRequest = fetch(`/api/cultivation/students/${student.id}/signals`)
      .then(async (response) => {
        if (!response.ok) throw Error();
        return await response.json() as Signals;
      })
      .catch(() => ({ notice: "暂时无法读取补充预警信号。" }));
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
    setResult({ student, outcomes, signals: await signalsRequest });
    setRunning(false);
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
          <label>查找研究生
            <input placeholder="输入姓名、学号或研究编号" value={query} onChange={(event) => {
              setQuery(event.target.value);
              setStudentId("");
              setResult(undefined);
              showSnapshot(null);
            }} />
          </label>
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
            : roster.total === 0 ? <p>{query.trim() ? "未找到匹配的学生。" : "授权范围内暂无学生档案。"}</p>
            : roster.total > pageSize ? <p>共 {roster.total} 人，输入姓名或编号缩小范围。</p> : null}
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
          <MentorCourseComparison key={result.student.id} studentId={result.student.id} />
          {snapshots.length > 0 && (
            <>
              {snapshots.length < stages.length && <p>有环节未能完成分析，关注清单仅覆盖已返回的结果。</p>}
              <StudentAlerts snapshots={snapshots} />
            </>
          )}
          <details className="task-details" open={Boolean(result.signals.blind_review || result.signals.mobility || result.signals.peer_outputs?.below)}>
            <summary>盲审送审、学籍与成果关注信号</summary>
            {result.signals.blind_review && (
              <p>盲审送审 · {result.signals.blind_review.batch} · 应交日期 {result.signals.blind_review.due || "待补充"} · {result.signals.blind_review.status}</p>
            )}
            {result.signals.mobility ? <p>学籍异动 · {result.signals.mobility.type}
              {result.signals.mobility.date ? ` · ${result.signals.mobility.date}` : ""} ·
              <a href={`/api/students/${result.student.id}`} target="_blank" rel="noreferrer">查看档案来源</a>
            </p> : result.signals.mobility === null && <p>当前档案未记录学籍异动。</p>}
            {result.signals.peer_outputs ? (
              <>
                <p>已登记成果 {result.signals.peer_outputs.count} 项 · 同届同专业中位数 {result.signals.peer_outputs.peer_median} 项（{result.signals.peer_outputs.peer_count} 人）
                  {result.signals.peer_outputs.below ? " · 低于同届中位数" : ""}</p>
                <p>按当前授权可见的四类有效成果统计，供人工核查。</p>
                {result.signals.peer_outputs.sources.map((source, index) => (
                  <span key={source}><a href={source} target="_blank" rel="noreferrer">成果来源 {index + 1}</a>{" "}</span>
                ))}
              </>
            ) : <p>{result.signals.notice}</p>}
          </details>
          {result.signals.course_trend && (
            <details className="task-details">
              <summary>个人课程趋势 · {result.signals.course_trend.signal}</summary>
              <p>按百分制学期均分比较，最近一学期与至少 5 个历史学期的均值 ± 3σ 比对，只用于核查。</p>
              {result.signals.course_trend.limits && <p>控制限 {result.signals.course_trend.limits.join(" 至 ")} 分</p>}
              <table>
                <thead><tr><th>学期</th><th>平均分</th><th>成绩条数</th></tr></thead>
                <tbody>{result.signals.course_trend.observations.map((row) => (
                  <tr key={row.term}><td>{row.term}</td><td>{row.mean}</td><td>{row.records}</td></tr>
                ))}</tbody>
              </table>
            </details>
          )}
          {result.signals.milestone_trends?.map((trend) => (
            <details className="task-details" key={trend.label}>
              <summary>个人{trend.label}趋势 · {trend.signal}</summary>
              <p>使用有实际日期的百分制记录，同日取均分。至少需要 5 个历史观测日。</p>
              {trend.limits && <p>控制限 {trend.limits.join(" 至 ")} 分</p>}
              {trend.observations.length > 0 && <table>
                <thead><tr><th>考核日期</th><th>平均分</th><th>记录编号</th></tr></thead>
                <tbody>{trend.observations.map((row) => (
                  <tr key={row.date}><td>{row.date}</td><td>{row.mean}</td><td>{row.record_ids.join("、")}</td></tr>
                ))}</tbody>
              </table>}
            </details>
          ))}
        </>
      )}
    </>
  );
}
