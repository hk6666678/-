import { useState } from "react";

type DirectoryOption = {
  id: number;
  name?: string;
  mentor_number?: string;
  group_number?: string;
};

type ScaleOutputResult = {
  as_of: string;
  kind: string;
  units: { id: number; name: string | null; students: number; outputs_per_student: number }[];
  excluded_units: number;
  correlation: { r: number | null; count: number };
  note: string;
};

type MetricSummary = { count: number; mean: number | null };
type GrowthPathResult = {
  as_of: string;
  kind: string;
  unit_id: number;
  unit_name: string | null;
  students: number;
  excellent: { count: number; metrics: Record<string, MetricSummary> };
  ordinary: { count: number; metrics: Record<string, MetricSummary> };
  excluded: { unlabeled: number; unauthorized: number };
  differences: Record<string, number | null> | null;
  notice: string | null;
  basis: string;
};

const metricNames: Record<string, string> = {
  course_pass_ratio: "课程通过比例",
  topic_score: "选题成绩",
  midterm_score: "中期成绩",
  outputs_per_student: "人均成果参与",
  oral_reports: "人均国际口头报告",
};
const metricOrder = Object.keys(metricNames);
const unitKindNames: Record<string, string> = { mentor_id: "导师", group_id: "课题组" };

function today() {
  return new Date().toISOString().slice(0, 10);
}

function optionLabel(option: DirectoryOption, fallback: string) {
  const number = option.mentor_number ?? option.group_number;
  if (option.name && number) return `${option.name}（${number}）`;
  return option.name ?? `${fallback} #${option.id}`;
}

function formatMetric(name: string, value: number | null) {
  if (value === null) return "—";
  return name === "course_pass_ratio" ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
}

function formatDifference(name: string, value: number | null) {
  if (value === null) return "—";
  const magnitude = name === "course_pass_ratio" ? `${(Math.abs(value) * 100).toFixed(1)} 个百分点` : Math.abs(value).toFixed(2);
  if (value === 0) return "无差异";
  return value > 0 ? `优秀组高 ${magnitude}` : `优秀组低 ${magnitude}`;
}

function useResearchQuery<T>() {
  const [result, setResult] = useState<T>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function run(url: string) {
    setBusy(true);
    setError("");
    setResult(undefined);
    try {
      const response = await fetch(url);
      const value = await response.json();
      if (!response.ok) {
        throw Error(typeof value.detail === "string" ? value.detail : "请求失败，请稍后重试");
      }
      setResult(value as T);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }
  return { result, error, busy, run };
}

function ScaleOutput() {
  const [asOf, setAsOf] = useState(today);
  const [kind, setKind] = useState<"mentor" | "group">("mentor");
  const { result, error, busy, run } = useResearchQuery<ScaleOutputResult>();
  const unitWord = kind === "mentor" ? "导师" : "课题组";
  return (
    <details className="task-details">
      <summary>规模与产出：团队大小和人均成果的关系</summary>
      <p className="muted">
        对当前有学生的每位{unitWord}列出两项：团队人数和人均成果参与次数，看两者是否同涨同落。
        只描述当前授权范围内的样本，相关不代表团队大小决定了产出。
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void run(`/api/mentor-groups/scale-output?${new URLSearchParams({ as_of: asOf, kind })}`);
        }}
      >
        <label>
          统计日期
          <input aria-label="规模分析统计日期" type="date" required value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </label>
        <label>
          统计单位
          <select aria-label="规模分析统计单位" value={kind} onChange={(e) => setKind(e.target.value === "group" ? "group" : "mentor")}>
            <option value="mentor">按导师</option>
            <option value="group">按课题组</option>
          </select>
        </label>
        <button disabled={busy}>{busy ? "正在计算…" : "分析规模与产出"}</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <section aria-label="规模与产出结果">
          <p>
            纳入 {result.units.length} 位{unitWord}
            {result.excluded_units > 0 && `，另有 ${result.excluded_units} 位因部分成果类别无分析权限未纳入`}
            。
          </p>
          {result.correlation.r !== null ? (
            <p>
              相关系数 r = {result.correlation.r.toFixed(3)}（{result.correlation.count} 个单位）。
              {result.correlation.count < 10 && " 单位数量较少，这个数字只能作为参考。"}
            </p>
          ) : (
            <p>
              {result.units.length < 3
                ? "可比较的单位不足三个，不计算相关系数。"
                : "团队人数或人均成果没有变化，无法计算相关系数。"}
            </p>
          )}
          {result.units.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{unitWord}</th>
                    <th>团队人数</th>
                    <th>人均成果参与</th>
                  </tr>
                </thead>
                <tbody>
                  {result.units.map((unit) => (
                    <tr key={unit.id}>
                      <td>{unit.name ?? `${unitWord} #${unit.id}`}</td>
                      <td>{unit.students}</td>
                      <td>{unit.outputs_per_student.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>当前范围内没有可分析的单位。</p>
          )}
          <p className="muted">{result.note}</p>
        </section>
      )}
    </details>
  );
}

function GrowthPath({ mentors, groups }: { mentors: DirectoryOption[]; groups: DirectoryOption[] }) {
  const [asOf, setAsOf] = useState(today);
  const [kind, setKind] = useState<"mentor" | "group">("mentor");
  const [selected, setSelected] = useState("");
  const { result, error, busy, run } = useResearchQuery<GrowthPathResult>();
  const options = kind === "mentor" ? mentors : groups;
  const unitWord = kind === "mentor" ? "导师" : "课题组";
  const differences = result?.differences ?? null;
  const metricCell = (summary: MetricSummary, name: string) =>
    summary.mean === null ? "—" : `${formatMetric(name, summary.mean)}（${summary.count} 人）`;
  return (
    <details className="task-details">
      <summary>成长路径：优秀论文学生与其他学生的差别</summary>
      <p className="muted">
        取这位{unitWord}指导过的历届学生（包括关系已结束的），按学位论文上的专家样本标签分成两组：
        标注“优秀”的和标注“普通”的；标注“待评”或没有标签的学生不参与比较。
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!selected) return;
          void run(
            `/api/mentor-groups/growth-path?${new URLSearchParams({
              as_of: asOf,
              [kind === "mentor" ? "mentor_id" : "group_id"]: selected,
            })}`,
          );
        }}
      >
        <label>
          统计日期
          <input aria-label="成长路径统计日期" type="date" required value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </label>
        <label>
          按导师还是课题组
          <select
            aria-label="成长路径单位类型"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value === "group" ? "group" : "mentor");
              setSelected("");
            }}
          >
            <option value="mentor">按导师</option>
            <option value="group">按课题组</option>
          </select>
        </label>
        <label>
          {unitWord}
          <select aria-label="成长路径单位" required value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">请选择{unitWord}</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {optionLabel(option, unitWord)}
              </option>
            ))}
          </select>
        </label>
        <button disabled={busy || !selected}>{busy ? "正在计算…" : "比较成长路径"}</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <section aria-label="成长路径结果">
          <p>
            {unitKindNames[result.kind] ?? unitWord} {result.unit_name ?? `#${result.unit_id}`} ·
            历届学生 {result.students} 人 · 优秀组 {result.excellent.count} 人 · 对照组 {result.ordinary.count} 人
            {result.excluded.unlabeled > 0 && ` · 未标注或待评 ${result.excluded.unlabeled} 人`}
            {result.excluded.unauthorized > 0 && ` · 标签无权读取 ${result.excluded.unauthorized} 人`}
          </p>
          {result.notice && <p className="reading-note">{result.notice}</p>}
          {differences && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>维度</th>
                    <th>优秀组</th>
                    <th>对照组</th>
                    <th>差别</th>
                  </tr>
                </thead>
                <tbody>
                  {metricOrder.map((name) => (
                    <tr key={name}>
                      <td>{metricNames[name]}</td>
                      <td>{metricCell(result.excellent.metrics[name], name)}</td>
                      <td>{metricCell(result.ordinary.metrics[name], name)}</td>
                      <td>{formatDifference(name, differences[name])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {result.excellent.count + result.ordinary.count > 0 && !result.differences && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>维度</th>
                    <th>优秀组</th>
                    <th>对照组</th>
                  </tr>
                </thead>
                <tbody>
                  {metricOrder.map((name) => (
                    <tr key={name}>
                      <td>{metricNames[name]}</td>
                      <td>{metricCell(result.excellent.metrics[name], name)}</td>
                      <td>{metricCell(result.ordinary.metrics[name], name)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted">{result.basis}</p>
        </section>
      )}
    </details>
  );
}

export function MentorResearch({ mentors, groups }: { mentors: DirectoryOption[]; groups: DirectoryOption[] }) {
  return (
    <>
      <ScaleOutput />
      <GrowthPath mentors={mentors} groups={groups} />
    </>
  );
}
