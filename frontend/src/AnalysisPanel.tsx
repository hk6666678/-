import { useEffect, useRef, useState } from "react";
import { ProcessAlerts, ProcessAlertSummary } from "./ProcessAlerts";
import { CultivationOverview } from "./CultivationOverview";
type Group = {
  group_value: string;
  course_code: string;
  grading: string;
  term: string;
  assessment_count: number;
  student_count: number;
  missing_scores: number;
  passed: number;
  failed: number;
  unknown: number;
  pass_rate: number | null;
  mean: number | null;
  values: Record<string, number>;
};
export type Snapshot = {
  id: number;
  category: string;
  scope: {
    student_id?: number | null;
    college: string;
    major: string;
    course_code: string;
    term: string;
    grade: string;
    level: string;
    group_by: string;
  };
  stale: boolean;
  created_at: number;
  data_version: string;
  rule_version: string;
  result: Group & {
    known_count: number;
    groups: Group[];
    credit_progress?: {
      value: string | null;
      missing_conditions: string[];
      students?: {
        student_id: number;
        earned_credits: number;
        progress_percent: number;
      }[];
    };
    reminders: {
      record_id: number;
      overdue: boolean | null;
      missing_conditions: string[];
    }[];
  };
  evidence: {
    id: number;
    student_id: number;
    version: number;
    dependency_token: string;
    status: string;
    rule_id: number | null;
    payload: Record<string, string>;
    source_row_id: number;
    source: {
      batch_id: number;
      sheet: string;
      row_number: number;
      source_department: string;
    };
  }[];
};
export function AnalysisPanel({ csrf }: { csrf: string }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [showAlertSummary, setShowAlertSummary] = useState(false);
  const resultHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (snapshot) resultHeading.current?.focus();
  }, [snapshot]);

  return (
    <section className="card">
      <h2>培养过程分析</h2>
      <CultivationOverview csrf={csrf} showSnapshot={setSnapshot} />
      <details className="task-details" onToggle={(event) => {
        setShowAlertSummary(event.currentTarget.open);
      }}>
        <summary>培养预警汇总</summary>
        {showAlertSummary && <ProcessAlertSummary />}
      </details>
      {snapshot && (
        <>
          <h3 tabIndex={-1} ref={resultHeading}>
            分析版本 {snapshot.id} ·{" "}
            {snapshot.stale ? "已过时，请生成新版本" : "当前有效"}
          </h3>
          {snapshot.result.assessment_count === 0 && (
            <p>当前筛选范围内没有可分析的考核记录。可清空可选筛选，或检查对应环节的数据是否已导入。</p>
          )}
          <p>通过率按已知结果的考核记录计算。空成绩不计零；均值和分布按同课程、同学期、同评分制度计算。</p>
          <p>
            分析范围：{snapshot.scope.student_id && `研究记录 ${snapshot.scope.student_id} / `}
            {snapshot.scope.college} / {snapshot.scope.major || "授权范围内专业"} /{" "}
            {snapshot.scope.course_code || "全部课程"} /{" "}
            {snapshot.scope.term || "全部学期"} · 年级{" "}
            {snapshot.scope.grade || "全部"} · 培养层次{" "}
            {snapshot.scope.level || "全部"} · 分组{" "}
            {snapshot.scope.group_by || "无"} ·{" "}
            {new Date(snapshot.created_at * 1000).toLocaleString()} · 考核记录{" "}
            {snapshot.result.assessment_count} · 去重学生{" "}
            {snapshot.result.student_count} · 已知状态{" "}
            {snapshot.result.known_count} · 通过 {snapshot.result.passed} ·
            不通过 {snapshot.result.failed} · 未知 {snapshot.result.unknown} ·
            缺成绩 {snapshot.result.missing_scores} · 通过率{" "}
            {snapshot.result.pass_rate === null
              ? "不可计算"
              : `${snapshot.result.pass_rate}%`}
          </p>
          <ProcessAlerts snapshot={snapshot} />
          <h3>学分进度与条件提醒</h3>
          <p>
            {snapshot.result.credit_progress?.value == null
              ? `学分进度不可计算，缺少：${snapshot.result.credit_progress?.missing_conditions.join("、") || "历史分析未记录学分计算条件"}`
              : "学分进度已按确认规则计算"}
          </p>
          {snapshot.result.credit_progress?.students?.map((s) => (
            <p key={s.student_id}>
              研究记录 {s.student_id}：已获学分 {s.earned_credits}，进度{" "}
              {s.progress_percent}%
            </p>
          ))}
          {snapshot.result.reminders?.map((r) => (
            <p key={r.record_id}>
              记录 {r.record_id}：
              {r.overdue === null
                ? `无法判断超期，缺少：${r.missing_conditions.join("、")}`
                : r.overdue
                  ? "已超期（明确日期依据）"
                  : "未超期"}
            </p>
          ))}
          <details>
            <summary>
              学生通过画像（按学号聚合本快照证据，
              {snapshot.evidence.length} 条）
            </summary>
            <p className="muted">
              学号来自导入的业务字段；身份信息不在分析口径内。排序按"不通过＋未知"记录数从多到少，便于先看需要关注的学生。
            </p>
            {(() => {
              const rows = new Map<
                string,
                { passed: number; failed: number; unknown: number }
              >();
              for (const e of snapshot.evidence) {
                const key = e.payload["学号"] || `记录 ${e.id}`;
                const row =
                  rows.get(key) ?? { passed: 0, failed: 0, unknown: 0 };
                if (e.status === "通过") row.passed += 1;
                else if (e.status === "不通过") row.failed += 1;
                else row.unknown += 1;
                rows.set(key, row);
              }
              const sorted = [...rows.entries()].sort(
                (a, b) =>
                  b[1].failed +
                  b[1].unknown -
                  (a[1].failed + a[1].unknown),
              );
              return (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>学号</th>
                        <th>记录数</th>
                        <th>通过</th>
                        <th>不通过</th>
                        <th>未知</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map(([key, row]) => (
                        <tr key={key}>
                          <td>{key}</td>
                          <td>{row.passed + row.failed + row.unknown}</td>
                          <td>{row.passed}</td>
                          <td>{row.failed}</td>
                          <td>{row.unknown}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </details>
          <details>
            <summary>数据与规则版本</summary>
            <p>数据 {snapshot.data_version}</p>
            <p>规则 {snapshot.rule_version}</p>
          </details>
          <a
            href={`/api/analyses/${snapshot.id}/export`}
            target="_blank"
            rel="noreferrer"
          >
            下载分析 Excel（须导出权限）
          </a>
          <table>
            <thead>
              <tr>
                {[
                  "课程",
                  "学期",
                  "制度",
                  "记录/学生",
                  "缺成绩",
                  "不通过/未知",
                  "通过率",
                  "均值",
                ].map((t) => (
                  <th key={t}>{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {snapshot.result.groups.map((g, i) => (
                <tr key={i}>
                  <td>
                    {g.course_code} {g.group_value}
                  </td>
                  <td>{g.term}</td>
                  <td>{g.grading}</td>
                  <td>
                    {g.assessment_count}/{g.student_count}
                  </td>
                  <td>{g.missing_scores}</td>
                  <td>
                    {g.failed}/{g.unknown}
                  </td>
                  <td>
                    {g.pass_rate === null ? "不可计算" : `${g.pass_rate}%`}
                  </td>
                  <td>{g.mean ?? "不适用"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {snapshot.result.groups.map((g, i) => (
            <div key={i}>
              <h4>
                {g.course_code} · {g.term} · {g.grading} 成绩分布（含缺失）
              </h4>
              <table>
                <thead>
                  <tr>
                    <th>成绩</th>
                    <th>记录数</th>
                    <th>分布</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(g.values).map(([v, n]) => (
                    <tr key={v}>
                      <td>{v}</td>
                      <td>{n}</td>
                      <td>
                        <meter
                          min={0}
                          max={g.assessment_count}
                          value={n}
                          aria-label={`${v} ${n}条`}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          <details>
            <summary>来源下钻与逐条证据</summary>
            {snapshot.evidence.map((e) => (
              <article key={e.id}>
                <p>
                  {e.dependency_token} · {e.status} ·{" "}
                  {e.rule_id ? `规则 ${e.rule_id}` : "业务结果或未知"} · 来源行{" "}
                  {e.source_row_id} · 批次 {e.source.batch_id} ·{" "}
                  {e.source.sheet} 第 {e.source.row_number} 行 ·{" "}
                  {e.source.source_department}
                </p>
                <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                <a href={`/api/imports/${e.source.batch_id}/download`}>下载原始 Excel（全文件范围及身份授权）</a>
                <a
                  href={`/api/records/${snapshot.category}/${e.id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  记录版本和来源历史
                </a>
              </article>
            ))}
          </details>
        </>
      )}
    </section>
  );
}
