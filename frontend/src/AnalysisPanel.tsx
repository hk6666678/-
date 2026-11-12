import { useState } from "react";
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
type Snapshot = {
  id: number;
  category: string;
  scope: {
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
  const [category, setCategory] = useState("courses"),
    [grade, setGrade] = useState(""),
    [level, setLevel] = useState(""),
    [groupBy, setGroupBy] = useState(""),
    [requiredCredits, setRequiredCredits] = useState("");
  const [college, setCollege] = useState(""),
    [major, setMajor] = useState(""),
    [course, setCourse] = useState(""),
    [term, setTerm] = useState("");
  const [grading, setGrading] = useState("百分制"),
    [condition, setCondition] = useState(""),
    [reason, setReason] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null),
    [history, setHistory] = useState<Snapshot[]>([]),
    [error, setError] = useState(""),
    [rules, setRules] = useState("");
  async function call(url: string, body?: unknown) {
    setError("");
    try {
      const r = await fetch(url, {
        method: body ? "POST" : "GET",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await r.json();
      if (!r.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "请检查完整条件及授权",
        );
      return data;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }
  const scope = {
    college,
    major,
    course_code: course,
    term,
    category,
    grade,
    level,
    group_by: groupBy,
  };
  return (
    <section className="card">
      <h2>课程分析与通过规则</h2>
      <label>
        分析环节
        <select
          aria-label="分析环节"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setSnapshot(null);
          }}
        >
          <option value="courses">课程</option>
          <option value="topic">选题</option>
          <option value="midterm">中期</option>
        </select>
      </label>
      <label>
        年级（入学年份）
        <input value={grade} onChange={(e) => setGrade(e.target.value)} />
      </label>
      <label>
        培养层次
        <input value={level} onChange={(e) => setLevel(e.target.value)} />
      </label>
      <label>
        对比分组
        <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
          <option value="">不分组</option>
          <option value="grade">年级</option>
          <option value="major">专业</option>
          <option value="level">培养层次</option>
        </select>
      </label>
      <p>
        通过率＝通过考核记录／已知状态考核记录。未知不进入分母，空成绩不计零；学生人数去重。仅同课程、同学期、同评分制度展示均值和分布。
      </p>
      <label>
        学院
        <input value={college} onChange={(e) => setCollege(e.target.value)} />
      </label>
      <label>
        专业
        <input value={major} placeholder="分析留空表示当前授权专业；规则须具体专业" onChange={(e) => setMajor(e.target.value)} />
      </label>
      <label>
        {category === "courses"
          ? "课程编号（分析可留空）"
          : "考核批次（分析可留空）"}
        <input value={course} onChange={(e) => setCourse(e.target.value)} />
      </label>
      <label>
        学期（留空表示全部）
        <input value={term} onChange={(e) => setTerm(e.target.value)} />
      </label>
      <button
        onClick={async () => {
          const r = await call(`/api/analyses/${category}`, scope);
          if (r) setSnapshot(r);
        }}
      >
        生成新分析版本
      </button>
      <button
        onClick={async () => {
          const r = await call("/api/analyses");
          if (r) setHistory(r.items);
        }}
      >
        读取分析历史
      </button>
      {history.map((h) => (
        <button
          key={h.id}
          onClick={async () => {
            const r = await call(`/api/analyses/${h.id}`);
            if (r) setSnapshot(r);
          }}
        >
          分析 {h.id} {h.stale ? "过时" : "有效"}
        </button>
      ))}
      <details>
        <summary>业务确认通过规则（独立授权）</summary>
        <p>
          没有默认分数线。规则按学院、专业、课程、评分制度和可选学期适用；保存生成新版本。
        </p>
        <label>
          评分制度
          <select value={grading} onChange={(e) => setGrading(e.target.value)}>
            {["百分制", "五级制", "二级制"].map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <label>
          {grading === "百分制" ? "最低通过分数" : "通过等级（逗号分隔）"}
          <input
            value={condition}
            onChange={(e) => setCondition(e.target.value)}
          />
        </label>
        <label>
          业务确认依据
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          业务人员已确认适用范围及规则
        </label>
        <button
          onClick={async () => {
            const r = await call("/api/pass-rules", {
              ...scope,
              grading,
              threshold:
                grading === "百分制" && condition.trim()
                  ? Number(condition)
                  : null,
              passing_values:
                grading === "百分制"
                  ? []
                  : condition.split(/[,，]/).map((v) => v.trim()),
              reason,
              confirmed,
            });
            if (r) setRules(JSON.stringify(r));
          }}
        >
          确认新规则版本
        </button>
        <button
          onClick={async () => {
            const r = await call(
              `/api/pass-rules?category=${category}&college=${encodeURIComponent(college)}&major=${encodeURIComponent(major)}`,
            );
            if (r) setRules(JSON.stringify(r, null, 2));
          }}
        >
          查看规则历史
        </button>
        {category === "courses" && (
          <>
            <label>
              培养要求总学分
              <input
                type="number"
                value={requiredCredits}
                onChange={(e) => setRequiredCredits(e.target.value)}
              />
            </label>
            <p>
              适用于本学院、专业所有年级与培养层次。重复修读计入规则：每门课程只计一次，通过考核中取最大学分。仅业务确认此规则适用时保存。
            </p>
            <button
              onClick={async () => {
                const r = await call("/api/training-requirements", {
                  ...scope,
                  required_credits: Number(requiredCredits),
                  repeat_policy: "max_passed_credits",
                  reason,
                  confirmed,
                });
                if (r) setRules(JSON.stringify(r));
              }}
            >
              确认培养要求版本
            </button>
          </>
        )}
        <pre>{rules}</pre>
      </details>
      {error && <p role="alert">{error}</p>}
      {snapshot && (
        <>
          <h3>
            分析版本 {snapshot.id} ·{" "}
            {snapshot.stale ? "已过时，请生成新版本" : "当前有效"}
          </h3>
          <p>
            分析范围：{snapshot.scope.college} / {snapshot.scope.major || "授权范围内专业"} /{" "}
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
            <summary>数据与规则版本</summary>
            <p>数据 {snapshot.data_version}</p>
            <p>规则 {snapshot.rule_version}</p>
          </details>
          <a
            href={`/api/analyses/${snapshot.id}/export`}
            target="_blank"
            rel="noreferrer"
          >
            导出分析与证据（须导出权限）
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
