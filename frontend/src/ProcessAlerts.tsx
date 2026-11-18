import { useEffect, useState } from "react";
import type { Snapshot } from "./AnalysisPanel";

type Evidence = Snapshot["evidence"][number];

function courseCharts(snapshot: Snapshot) {
  const students = new Map<number, Map<string, { score: number; evidence: Evidence }[]>>();
  if (snapshot.category === "courses") {
    for (const row of snapshot.evidence) {
      const term = /^(\d{4})(春|秋)$/.exec(row.payload["修读学期"]);
      const raw = row.payload["原始成绩"];
      if (!term || !raw?.trim() || row.payload["评分制度"] !== "百分制") continue;
      const score = Number(raw);
      if (!Number.isFinite(score)) continue;
      const label = term[1] + (term[2] === "春" ? "1" : "2");
      const terms = students.get(row.student_id) ?? new Map<string, { score: number; evidence: Evidence }[]>();
      const scores = terms.get(label) ?? [];
      scores.push({ score, evidence: row });
      terms.set(label, scores);
      students.set(row.student_id, terms);
    }
  }
  return [...students].flatMap(([student, terms]) => {
    const points = [...terms].sort(([a], [b]) => a.localeCompare(b)).map(
      ([term, scores]) => ({ term, score: scores.reduce((a, b) => a + b.score, 0) / scores.length }),
    );
    if (points.length < 6) return [];
    const baseline = points.slice(0, -1);
    const center = baseline.reduce((sum, point) => sum + point.score, 0) / baseline.length;
    const movingRange = baseline.slice(1).reduce(
      (sum, point, i) => sum + Math.abs(point.score - baseline[i].score), 0,
    ) / (baseline.length - 1);
    if (movingRange === 0) return [];
    const lower = Math.max(0, center - 2.66 * movingRange);
    const upper = Math.min(100, center + 2.66 * movingRange);
    const latest = points[points.length - 1].score;
    return [{ student, points, center, lower, upper, latest, evidence: [...terms.values()].flat().map((row) => row.evidence) }];
  });
}

export function ProcessAlerts({ snapshot }: { snapshot: Snapshot }) {
  if (snapshot.stale) return <p>分析已过时，重新生成后查看预警。</p>;
  const charts = courseCharts(snapshot);
  const overdue = (snapshot.result.reminders ?? []).filter((row) => row.overdue === true);
  const outside = charts.filter(({ latest, lower, upper }) => latest < lower || latest > upper);
  return (
    <section>
      <h4>培养过程预警 · 分析 {snapshot.id}</h4>
      {snapshot.category === "courses" ? (
        <>
          <p>课程控制图越界 {outside.length} 人，可计算 {charts.length} 人。</p>
          <p>按学生和学期汇总百分制成绩。至少五个历史学期用于估计个体值控制限，比较最近学期。历史波动为零或数据不足时跳过。仅识别变化信号，课程难度、选课组合和缺失数据均可能影响结果。</p>
          {charts.map(({ student, points, center, lower, upper, latest }) => (
            <details key={student}>
              <summary>研究记录 {student} · {latest < lower ? "低于下限" : latest > upper ? "高于上限" : "限内"}</summary>
              <svg viewBox="0 0 440 120" width="440" style={{ maxWidth: "100%" }}
                role="img" aria-label="百分制课程学期均分控制图">
                {[lower, center, upper].map((line, i) => (
                  <line key={i} x1="20" x2="420" y1={110 - line} y2={110 - line}
                    stroke="currentColor" strokeDasharray="4 4" />
                ))}
                <polyline fill="none" stroke="#2563eb" strokeWidth="2"
                  points={points.map((p, i) => `${20 + 400 * i / (points.length - 1)},${110 - p.score}`).join(" ")} />
              </svg>
              <p>下限 {lower.toFixed(1)} · 中心 {center.toFixed(1)} · 上限 {upper.toFixed(1)}</p>
              <p>{points.map(({ term, score }) => `${term.slice(0, 4)}${term.endsWith("1") ? "春" : "秋"} ${score.toFixed(1)}`).join(" · ")}</p>
            </details>
          ))}
        </>
      ) : (
        <p>有明确日期依据的超期记录 {overdue.length} 条
          {overdue.length > 0 && `（记录 ${overdue.map((row) => row.record_id).join("、")}）`}</p>
      )}
    </section>
  );
}

export function StudentAlerts({ snapshots }: { snapshots: Snapshot[] }) {
  type Signal = { label: string; snapshot: number; category: string; evidence: Evidence[] };
  const students = new Map<number, Signal[]>();
  function add(student: number, signal: Signal) {
    const signals = students.get(student) ?? [];
    signals.push(signal);
    students.set(student, signals);
  }
  for (const snapshot of snapshots) {
    if (snapshot.stale) continue;
    if (snapshot.category === "courses") {
      for (const chart of courseCharts(snapshot)) {
        const direction = chart.latest < chart.lower ? "低于下限" : chart.latest > chart.upper ? "高于上限" : "";
        if (direction) add(chart.student, { label: `课程均分${direction}`, snapshot: snapshot.id, category: snapshot.category, evidence: chart.evidence });
      }
      continue;
    }
    const overdue = new Set((snapshot.result.reminders ?? []).filter((row) => row.overdue === true).map((row) => row.record_id));
    for (const row of snapshot.evidence) {
      if (overdue.has(row.id))
        add(row.student_id, { label: snapshot.category === "topic" ? "选题超期" : "中期超期", snapshot: snapshot.id, category: snapshot.category, evidence: [row] });
      if (snapshot.category === "midterm" && row.status === "不通过")
        add(row.student_id, { label: "中期未通过", snapshot: snapshot.id, category: snapshot.category, evidence: [row] });
    }
  }
  const ordered = [...students].sort(([a, left], [b, right]) => right.length - left.length || a - b);
  return (
    <section aria-label="逐生预警清单">
      <h4>逐生预警清单（{ordered.length} 人）</h4>
      <p>按学生合并本次所列分析中的信号。超期以生成分析当天的判断为准，未知状态不计入预警。</p>
      {ordered.length === 0 && <p>所列分析未发现已确认的预警信号。</p>}
      {ordered.map(([student, signals]) => (
        <details key={student}>
          <summary>研究记录 {student} · {signals.length} 条信号</summary>
          <ul>{signals.map((signal) => (
            <li key={JSON.stringify([signal.snapshot, signal.label, signal.evidence.map((row) => row.id)])}>
              {signal.label} · 分析 #{signal.snapshot}
              <details>
                <summary>查看来源记录（{signal.evidence.length} 条）</summary>
                <ul>{signal.evidence.map((row) => (
                  <li key={row.id}>
                    <a href={`/api/records/${signal.category}/${row.id}`} target="_blank" rel="noreferrer">记录 #{row.id} v{row.version}</a>
                    {" · "}批次 #{row.source.batch_id} · {row.source.source_department} · {row.source.sheet} 第 {row.source.row_number} 行
                  </li>
                ))}</ul>
              </details>
            </li>
          ))}</ul>
        </details>
      ))}
    </section>
  );
}

export function ProcessAlertSummary() {
  const [snapshots, setSnapshots] = useState<Snapshot[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const read = async (path: string) => {
      const response = await fetch(path, { signal: controller.signal });
      if (!response.ok) throw new Error();
      return response.json();
    };
    async function load() {
      const { items } = await read("/api/analyses") as { items: Snapshot[] };
      const selected = ["courses", "topic", "midterm"].flatMap((category) => {
        const item = items.find((snapshot) => snapshot.category === category && !snapshot.stale && !snapshot.scope.student_id);
        return item ? [item] : [];
      });
      setSnapshots(await Promise.all(selected.map((item) => read(`/api/analyses/${item.id}`))));
    }
    void load().catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, []);
  return (
    <section className="card">
      <h3>培养过程预警</h3>
      <p>每个环节显示当前授权范围内最新的有效分析。各分析范围可能不同。</p>
      {snapshots && snapshots.length > 0 && <StudentAlerts snapshots={snapshots} />}
      {error ? <p role="alert">预警加载失败，请刷新重试。</p>
        : snapshots === null ? <p>正在读取分析</p>
        : snapshots.length === 0 ? <p>暂无有效分析，请先生成分析。</p>
        : snapshots.map((snapshot) => (
          <details key={snapshot.id} open>
            <summary>{({ courses: "课程", topic: "选题", midterm: "中期" } as Record<string, string>)[snapshot.category]} · {snapshot.scope.college} · {snapshot.scope.major || "授权专业"} · {snapshot.scope.term || "全部学期"} · {snapshot.scope.grade || "全部年级"} · {snapshot.scope.level || "全部层次"} · {snapshot.scope.course_code || "全部课程或批次"}</summary>
            <ProcessAlerts snapshot={snapshot} />
          </details>
        ))}
    </section>
  );
}
