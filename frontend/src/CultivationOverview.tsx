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
  course_notice?: string;
  course_trend?: { description?: string; signal: string; baseline_count: number; limits?: [number, number]; observations: { term: string; mean: number; records: number }[] };
  milestone_trends?: { description?: string; label: string; signal: string; limits?: [number, number]; observations: { date: string; mean: number; record_ids: number[] }[] }[];
  output_trend?: { signal: string; declining?: boolean; limits?: [number, number]; observations: { term: string; count: number | null }[] };
  blind_review?: { batch: string; due: string; status: string };
  mobility?: { type: string; date?: string } | null;
  peer_outputs?: { count: number; peer_median: number; peer_count: number; below: boolean; sources: string[] };
  notice?: string;
};
const pageSize = 50;

function studentLabel(student: Student) {
  return [student.name, student.student_number || student.research_id, student.data["所属学院"], student.data["专业"]].filter(Boolean).join(" · ");
}

export type EvidenceTarget = { student: number; kind: "courses" | "topic"; record?: number; actual?: string; date?: string };

function changed(target:EvidenceTarget, row:Snapshot["evidence"][number]) {
  return target.actual !== undefined && (target.actual !== (row.payload["实际日期"] || "") || target.date !== row.payload["计划日期"]);
}

export function CultivationOverview({ csrf, showSnapshot, target, onTopicChanged, onTopicDenied }: {
  csrf: string;
  showSnapshot: (snapshot: Snapshot | null) => void;
  target?: EvidenceTarget;
  onTopicChanged?: () => void;
  onTopicDenied?: (student: Student) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [roster, setRoster] = useState<{ items: Student[]; total: number }>();
  const [rosterError, setRosterError] = useState(false);
  const [studentId, setStudentId] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ student: Student; outcomes: Outcome[]; signals: Signals }>();
  const [view, setView] = useState("培养概况");
  const heading = useRef<HTMLHeadingElement>(null);
  const [targetError, setTargetError] = useState("");
  useEffect(() => {
    if (!target) return;
    let active = true;
    void (async () => {
      const response = await fetch(`/api/students/${target.student}`);
      if (!response.ok) throw Error();
      const student: Student = await response.json();
      if (student.id !== target.student) throw Error();
      if (active) await load({college: student.data["所属学院"], major: student.data["专业"], student_id:student.id}, student);
    })().catch(() => { if (active) setTargetError("当前无法读取这名学生的依据，请核对权限。"); });
    return () => { active = false; };
  }, [target]);

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
    setView(target ? "个人趋势" : "培养概况");
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
        if (target?.kind === "topic" && stage.key === "topic" && response.status === 403) {
          await onTopicDenied?.(student);
        }
        const data = await response.json();
        if (response.ok && data.scope?.student_id === scope.student_id) {
          if (stage.key === "topic" && target?.kind === "topic") {
            const row = (data as Snapshot).evidence.find(e => e.id === target.record);
            if (row && changed(target,row)) onTopicChanged?.();
          }
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
  const hasNoStageRecords = snapshots.length === stages.length && snapshots.every(s => s.result.assessment_count === 0);
  return (
    <>
      {targetError && <p role="alert">{targetError}</p>}
      {!target && <form className="cultivation-scope" onSubmit={(event) => {
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
      </form>}
      {running && <p role="status">正在分析课程、选题和中期。</p>}
      {result && (
        <>
          <h3 ref={heading} tabIndex={-1}>个人培养过程</h3>
          <p className="cultivation-student">{studentLabel(result.student)}</p>
          <section className="student-brief">
          {!target && <div className="brief-switch" role="group" aria-label="个人培养视图">
            {["培养概况", "个人趋势", "对比与来源"].map((name) => <button type="button" key={name}
              aria-pressed={view === name} onClick={() => { setView(name); showSnapshot(null); }}>{name}</button>)}
          </div>}
          {view === "培养概况" && <>
          {snapshots.length > 0 && (
            <>
              {snapshots.length < stages.length && <p>有环节未能完成分析，关注清单仅覆盖已返回的结果。</p>}
              {hasNoStageRecords
                ? <p className="reading-note">这名学生暂无课程、选题和中期记录，暂无法判断这三个环节是否触发预警。可到「课程导入与待关联」或「选题与中期导入」核对并补录。</p>
                : <StudentAlerts snapshots={snapshots} individual />}
            </>
          )}
          {result.signals.blind_review && <p>盲审送审　<strong>{result.signals.blind_review.status}</strong></p>}
          {result.signals.mobility && <p>学籍异动　<strong>{result.signals.mobility.type}</strong></p>}
          {result.signals.peer_outputs?.below && <p>科研成果低于同届同专业中位数，可在「对比与来源」查看。</p>}
          {result.signals.notice && <p>{result.signals.notice}</p>}
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

                          <p className="brief-rate"><strong>{outcome.snapshot.result.pass_rate === null ? "—" : `${outcome.snapshot.result.pass_rate}%`}</strong> 通过率</p>
                          <p>{outcome.snapshot.result.assessment_count} 条考核记录</p>
                          {(outcome.snapshot.result.failed > 0 || outcome.snapshot.result.unknown > 0) && <p>未通过 {outcome.snapshot.result.failed} 条 · 状态未知 {outcome.snapshot.result.unknown} 条</p>}
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
          </>}
          {view === "对比与来源" && <>
          <MentorCourseComparison key={result.student.id} studentId={result.student.id} />
          <section className="brief-context">
            <h4>盲审、学籍与科研成果</h4>
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
                <details><summary>查看成果来源（{result.signals.peer_outputs.sources.length}）</summary>
                {result.signals.peer_outputs.sources.map((source, index) => (
                  <span key={source}><a href={source} target="_blank" rel="noreferrer">成果来源 {index + 1}</a>{" "}</span>
                ))}</details>
              </>
            ) : <p>{result.signals.notice}</p>}
          </section></>}
          {view === "个人趋势" && <>
          {target?.kind === "topic" && (() => {
            const topic = snapshots.find(s => s.category === "topic");
            const row = topic?.evidence.find(e => e.id === target.record);
            return row ? <section><h4>选题日期依据</h4>
              {changed(target,row) && <p>{row.payload["实际日期"] && topic?.result.reminders?.some(r => r.record_id === row.id && r.overdue === false) ? "记录已更正，现在按期完成。" : "记录已更正，请核对最新日期。"}</p>}
              <p>{row.payload["选题标题"]} · 计划 {row.payload["计划日期"]} · 实际 {row.payload["实际日期"] || "尚未完成"}</p>
              <a href={`/api/records/topic/${row.id}`} target="_blank" rel="noreferrer">查看此条来源记录</a></section>
              : <p>当前无法核对这条选题记录。</p>;
          })()}
          {result.signals.course_notice && <p>{result.signals.course_notice}</p>}
          {result.outcomes.map((outcome, i) => "error" in outcome
            ? <p key={i}>{stages[i].label} · {outcome.error}</p>
            : outcome.snapshot.category !== "courses" && outcome.snapshot.result.reminders?.filter(r => r.overdue && r.timing_note).map(r =>
                <p key={r.record_id}>{stages[i].label}超期：{r.timing_note} <a href={`/api/records/${outcome.snapshot.category}/${r.record_id}`}>查看日期来源</a></p>))}

          {!result.signals.course_trend && !result.signals.milestone_trends?.length && !result.signals.output_trend && <p>{result.signals.notice || "暂无个人趋势记录。"}</p>}
          {result.signals.course_trend && (
            <details className="task-details" open={target?.kind === "courses" || undefined}>
              <summary>{result.signals.course_trend.description ?? `个人课程趋势 · ${result.signals.course_trend.signal}`} · 查看依据</summary>
              <p>{result.signals.course_trend.signal}。按百分制学期均分比较，最近一学期与至少 5 个历史学期的均值 ± 3σ 比对，只用于核查。</p>
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
              <summary>{trend.description ?? `个人${trend.label}趋势 · ${trend.signal}`} · 查看依据</summary>
              <p>{trend.signal}。使用有实际日期的百分制记录，同日取均分。至少需要 5 个历史观测日。</p>
              {trend.limits && <p>控制限 {trend.limits.join(" 至 ")} 分</p>}
              {trend.observations.length > 0 && <table>
                <thead><tr><th>考核日期</th><th>平均分</th><th>记录编号</th></tr></thead>
                <tbody>{trend.observations.map((row) => (
                  <tr key={row.date}><td>{row.date}</td><td>{row.mean}</td><td>{row.record_ids.join("、")}</td></tr>
                ))}</tbody>
              </table>}
            </details>
          ))}
          {result.signals.output_trend && (
            <details className="task-details">
              <summary>个人成果增量 · {result.signals.output_trend.signal}</summary>
              <p>只统计已核对完成的学期。日期不足以确认学期时显示待核查。</p>
              {result.signals.output_trend.declining && <p>最近三个学期新增成果连续下降。</p>}
              {result.signals.output_trend.limits && <p>控制限 {result.signals.output_trend.limits.join(" 至 ")} 项</p>}
              {result.signals.output_trend.observations.length > 0 && <table>
                <thead><tr><th>学期</th><th>新增成果</th></tr></thead>
                <tbody>{result.signals.output_trend.observations.map((row) => (
                  <tr key={row.term}><td>{row.term}</td><td>{row.count ?? "待核查"}</td></tr>
                ))}</tbody>
              </table>}
            </details>
          )}
          </>}
          </section>
        </>
      )}
    </>
  );
}
