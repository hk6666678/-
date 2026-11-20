import { EvidenceDetails } from "./EvidenceDetails";
import { useEffect, useRef, useState } from "react";
import { tongjiMajors } from "./tongjiMajors";
import { EvaluationDashboard } from "./EvaluationDashboard";
type Rule = {
  id: number;
  version: number;
  enabled: number;
  confirmed_by: string;
  basis: string;
  config: { name: string; college: string; major: string; mode: string };
};
type Snapshot = {
  screening?: { name: string; status: string; reason: string }[];
  signals?: { name: string; note: string; items: { feature: string; value: number | null; missing: string | null }[] }[];
  band?: string;
  rule_name?: string;
  ahp?: {
    matrix: number[][];
    consistency_ratio: number;
    dimensions: { name: string; weight: number; normalized: number | null }[];
  };
  id: number;
  student_id: number;
  rule_id: number;
  family_id: number;
  rule_version: number;
  mode: string;
  notice: string;
  stale: boolean;
  total: number | null;
  as_of: number;
  data_digest: string;
  inputs: {
    feature: string;
    value: number | null;
    normalized: number | null;
    weight: number;
    missing: string | null;
    evidence: unknown[];
  }[];
};
type SnapshotItem = {
  id: number;
  student_id: number;
  research_id: string;
  rule_id: number;
  family_id: number;
  rule_version: number;
  mode: string;
  total: number | null;
  as_of: number;
};
const features: Record<string, string> = {
  course_pass_ratio: "课程通过比例（0—1）",
  research_paper_count: "科研论文成果数",
  patent_count: "专利成果数",
  award_count: "获奖成果数",
  conference_count: "会议成果数",
  latest_citation_count: "最新引用总数",
};

type ClusterResult = {
  model_version: string;
  trained_at: number;
  recipe: { algorithm: string; distance_space: "latent" | "input"; training_seed: number; holdout_seed: number; calibration_seed?: number | null };
  inputs: Record<string, number | null>;
  cluster: { name: string; distance: number; threshold?: number | null; center: Record<string, number> } | null;
  validation: { training_count: number; holdout_count: number; matching_profiles: number; calibration_count?: number; false_positive?: number; false_negative?: number };
};

function StudentClusterDemo({ id }: { id: number }) {
  const [result, setResult] = useState<ClusterResult>();
  const [version, setVersion] = useState("synthetic-kmeans-v1");
  const [runs, setRuns] = useState<Record<string, ClusterResult>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <details className="task-details">
    <summary>学生分群训练与推理演练</summary>
    <p>使用合成评分向量训练。各版本使用同一份留出样本；One-class 和 Two-class 将这些样本分为参考类和对照类。</p>
    <label>学生分群模型版本<select value={version} disabled={busy} onChange={(e) => setVersion(e.target.value)}>
      <option value="synthetic-kmeans-v1">v1 · K-means</option>
      <option value="synthetic-autoencoder-v2">v2 · 自编码器 + K-means</option>
      <option value="synthetic-deep-one-class-v1">One-class · 参考类偏离检测</option>
      <option value="synthetic-deep-two-class-v1">Two-class · 参考类与对照类</option>
    </select></label>
    <button type="button" disabled={busy} onClick={async () => {
      setError("");
      setResult(undefined);
      setBusy(true);
      try {
        const response = await fetch(`/api/evaluation-snapshots/${id}/cluster-demo?model_version=${version}`);
        if (!response.ok) throw Error("无法读取分群结果，请检查授权或刷新页面。");
        const next: ClusterResult = await response.json();
        setResult(next);
        setRuns((saved) => ({ ...saved, [next.model_version]: next }));
      } catch (err) {
        setError(String(err));
      } finally {
        setBusy(false);
      }
    }}>运行模拟分群</button>
    {error && <p role="alert">{error}</p>}
    {result && <>
      <p>{result.cluster ? `模拟分组：${result.cluster.name} · 距离 ${result.cluster.distance}` : "维度缺失、快照过时或规则停用，暂不分群。"}</p>
      <p>训练 {result.validation.training_count} 条 · 留出 {result.validation.holdout_count} 条 · 与合成预设分组一致 {result.validation.matching_profiles} 条 · {result.model_version}</p>
      <p>{result.recipe.algorithm} · 训练种子 {result.recipe.training_seed} · 留出种子 {result.recipe.holdout_seed}</p>
      {result.cluster?.threshold != null && <p>参考类距离阈值 {result.cluster.threshold.toFixed(3)} · 独立校准样本 {result.validation.calibration_count} 条。</p>}
      {result.validation.false_positive !== undefined && <p>误判为参考类 {result.validation.false_positive} 条 · 漏判参考类 {result.validation.false_negative} 条。</p>}
      <p>训练档案保存于 {new Date(result.trained_at * 1000).toLocaleString()}。</p>
      <ul>{Object.entries(result.inputs).map(([name, value]) => (
        <li key={name}>{name} · 学生 {value?.toFixed(3) ?? "待核查"}{result.cluster && ` · 组中心 ${result.cluster.center[name]}`}</li>
      ))}</ul>
    </>}
    {Object.keys(runs).length > 1 && <table>
      <thead><tr><th>版本</th><th>同一学生的分组</th><th>同一留出集分组一致</th></tr></thead>
      <tbody>{Object.values(runs).map((run) => <tr key={run.model_version}>
        <td>{run.model_version}</td><td>{run.cluster?.name ?? "待核查"}</td>
        <td>{run.validation.matching_profiles}/{run.validation.holdout_count}{run.validation.false_positive !== undefined ? "（两类标签）" : "（三类标签）"}</td>
      </tr>)}</tbody>
    </table>}
  </details>;
}

function SixSignalTrial({ id }: { id: number }) {
  const [result, setResult] = useState<{
    total: number | null; levels: { name: string; score: number | null; basis: string }[];
    screening: { name: string; status: string; reason: string }[]; decision: string;
    topic_evidence?: { record_id: number; title_revisions: number[] }[];
    additional_evidence?: { title: string; facts: string[] }[];
  }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <details className="task-details">
    <summary>六类识别信号模拟试算</summary>
    <p>六类等权。此处结合已保存的快照和当前选题、中期及课程时序。资源获得暂用获奖指标，六类都有数据才计算总分。</p>
    <button type="button" disabled={busy} onClick={async () => {
      setBusy(true);
      setError("");
      setResult(undefined);
      try {
        const response = await fetch(`/api/evaluation-snapshots/${id}/six-signal-trial`);
        const value = await response.json();
        if (!response.ok) throw Error(value.detail || "无法试算");
        setResult(value);
      } catch (err) {
        setError(String(err));
      } finally {
        setBusy(false);
      }
    }}>试算六类信号</button>
    {error && <p role="alert">{error}</p>}
    {result && <>
      <h4>模拟分层结论</h4>
      <p>{result.decision}</p>
      <ul>{result.screening?.map((check) => (
        <li key={check.name}>{check.name} · {check.status} · {check.reason}</li>
      ))}</ul>
      <p>试算总分 · {result.total?.toFixed(2) ?? "证据不全，暂不计分"}</p>
      <table>
        <thead><tr><th>信号</th><th>分数</th><th>依据</th></tr></thead>
        <tbody>{result.levels.map((level) => <tr key={level.name}>
          <th scope="row">{level.name}</th><td>{level.score == null ? "待核查" : (level.score * 100).toFixed(2)}</td>
          <td>{level.basis.split("、").map((key) => features[key] ?? key).join("、") || "快照缺少该类证据"}</td>
        </tr>)}</tbody>
      </table>
      {(result.topic_evidence?.length ?? 0) > 0 && <details>
        <summary>选题标题修订依据</summary>
        <p>显示有实际日期、当前可核查的百分制选题记录。记录修订次数供人工核查。</p>
        <ul>{result.topic_evidence?.map((record) => (
          <li key={record.record_id}><a href={`/api/records/topic/${record.record_id}`}>选题记录 #{record.record_id}</a>
            {" · "}{record.title_revisions.length ? `标题修订 ${record.title_revisions.length} 次（${record.title_revisions.map((version) => `v${version}`).join("、")}）` : "暂无可见的标题修订"}
          </li>
        ))}</ul>
      </details>}
      {!!result.additional_evidence?.length && <details>
        <summary>新增成果、影响力与资源依据</summary>
        <ul>{result.additional_evidence.map((item, index) => (
          <li key={index}>{item.title} · {item.facts.join("；")}</li>
        ))}</ul>
      </details>}
    </>}
  </details>;
}

function Radar({ inputs }: { inputs: { feature: string; normalized: number | null }[] }) {
  if (inputs.length < 3)
    return (
      <p>
        指标少于3个时不绘制雷达图，避免退化为直线造成误读；请直接查看下方指标表。
      </p>
    );
  const size = 260,
    center = size / 2,
    radius = 92;
  const angle = (i: number) => -Math.PI / 2 + (2 * Math.PI * i) / inputs.length;
  const at = (i: number, ratio: number) => {
    const a = angle(i);
    return [center + radius * ratio * Math.cos(a), center + radius * ratio * Math.sin(a)];
  };
  return (
    <svg
      viewBox={`-45 -8 ${size + 90} ${size + 16}`}
      width={size + 90}
      height={size + 16}
      role="img"
      aria-label="指标雷达图"
      className="evaluation-radar"
    >
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon
          key={ring}
          points={inputs.map((_, i) => at(i, ring).join(",")).join(" ")}
          fill="none"
          stroke="#d0d7de"
          strokeWidth="1"
        />
      ))}
      {inputs.map((v, i) => {
        const [x, y] = at(i, 1);
        const [lx, ly] = at(i, 1.22);
        return (
          <g key={v.feature}>
            <line x1={center} y1={center} x2={x} y2={y} stroke="#d0d7de" />
            <text
              x={lx}
              y={ly}
              fontSize="10"
              textAnchor={lx > center + 4 ? "start" : lx < center - 4 ? "end" : "middle"}
              dominantBaseline="middle"
            >
              {features[v.feature] ?? v.feature}
              {v.normalized === null ? "（缺失）" : ""}
            </text>
          </g>
        );
      })}
      <polygon
        points={inputs.map((_, i) => at(i, inputs[i].normalized ?? 0).join(",")).join(" ")}
        fill="rgba(59,130,246,0.25)"
        stroke="#2563eb"
      />
      {inputs.map((v, i) => {
        const [x, y] = at(i, v.normalized ?? 0);
        return <circle key={v.feature} cx={x} cy={y} r="3" fill="#2563eb" />;
      })}
    </svg>
  );
}

function Growth({ snapshots }: { snapshots: SnapshotItem[] }) {
  const points = snapshots
    .filter((s) => s.total !== null)
    .sort((a, b) => a.as_of - b.as_of);
  const width = 360,
    height = 170,
    left = 44,
    bottom = 140;
  const times = points.map((p) => p.as_of);
  const span = Math.max(...times) - Math.min(...times) || 1;
  const x = (t: number) => left + ((t - Math.min(...times)) / span) * (width - left - 16);
  const y = (total: number) => bottom - (total / 100) * (bottom - 20);
  return (
    <div className="evaluation-growth">
      <p>
        仅绘制同一学生同一规则族的真实保存快照点，未形成总分的快照与缺失年份不补点、不外推；不同规则族的分数不可比，不混绘。
        {points.length < 2
          ? "有效快照不足两个，暂不绘制连线。"
          : `共${points.length}个有效快照点。`}
      </p>
      {points.length > 0 && (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          role="img"
          aria-label="总分成长曲线"
        >
          <line x1={left} y1={y(0)} x2={width - 8} y2={y(0)} stroke="#d0d7de" />
          <line x1={left} y1={y(100)} x2={width - 8} y2={y(100)} stroke="#d0d7de" />
          <text x={left - 6} y={y(100) + 4} fontSize="10" textAnchor="end">
            100
          </text>
          <text x={left - 6} y={y(0) + 4} fontSize="10" textAnchor="end">
            0
          </text>
          {points.length > 1 && (
            <polyline
              points={points.map((p) => `${x(p.as_of)},${y(p.total ?? 0)}`).join(" ")}
              fill="none"
              stroke="#2563eb"
            />
          )}
          {points.map((p) => (
            <circle key={p.id} cx={x(p.as_of)} cy={y(p.total ?? 0)} r="3.5" fill="#2563eb">
              <title>
                {`#${p.id} · ${p.total?.toFixed(2)} · ${new Date(p.as_of * 1000).toLocaleDateString()}`}
              </title>
            </circle>
          ))}
          {points.map((p) => (
            <text
              key={`label-${p.id}`}
              x={Math.min(Math.max(x(p.as_of), left + 26), width - 26)}
              y={bottom + 14}
              fontSize="9"
              textAnchor="middle"
            >
              {new Date(p.as_of * 1000).toLocaleDateString()}
            </text>
          ))}
        </svg>
      )}
      <div className="evaluation-table"><p className="table-hint">可左右滑动查看完整表格</p><div className="table-wrap"><table>
        <thead>
          <tr>
            <th>快照</th>
            <th>日期</th>
            <th>总分</th>
          </tr>
        </thead>
        <tbody>
          {snapshots.map((s) => (
            <tr key={s.id}>
              <td>#{s.id}</td>
              <td>{new Date(s.as_of * 1000).toLocaleDateString()}</td>
              <td>{s.total === null ? "数据不完整，未形成总分" : s.total.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table></div></div>
    </div>
  );
}
const tongjiMajorNames = new Set(tongjiMajors);
export function EvaluationPanel({ csrf }: { csrf: string }) {
  const [rules, setRules] = useState<Rule[]>([]),
    [selected, setSelected] = useState<number>(),
    [snapshot, setSnapshot] = useState<Snapshot>(),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [students, setStudents] = useState<
    { id: number; research_id: string; name?: string }[]
  >([]);
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [studentTotal, setStudentTotal] = useState<number>();
  const studentRequest = useRef(0);
  const [studentMajor, setStudentMajor] = useState("");
  const [majorFilters, setMajorFilters] = useState<{
    majors: string[];
    levels: string[];
  }>({ majors: [], levels: [] });
  async function call(url: string, body?: unknown) {
    const response = await fetch(
      url,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": csrf,
            },
            body: JSON.stringify(body),
          },
    );
    const value = await response.json();
    if (!response.ok)
      throw Error(
        typeof value.detail === "string"
          ? value.detail
          : "输入无效，请检查必填项与数值范围",
      );
    return value;
  }
  async function perform(action: () => Promise<void>) {
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(String(e));
    }
  }
  async function load() {
    const items = (await call("/api/evaluation-rules")).items;
    setRules(items);
  }
  async function loadSnapshots() {
    setSnapshots((await call("/api/evaluation-snapshots")).items);
  }
  async function fetchStudents(major: string) {
    const requestId = ++studentRequest.current;
    setStudents([]);
    setStudentTotal(undefined);
    const data = await call(
      `/api/students?limit=200&offset=0&major=${encodeURIComponent(major)}`,
    );
    if (requestId === studentRequest.current) {
      setStudents(data.items);
      setStudentTotal(data.total);
    }
  }
  const otherMajors = majorFilters.majors.filter(
    (name) => !tongjiMajorNames.has(name),
  );
  useEffect(() => {
    void perform(load);
    void perform(loadSnapshots);
    void fetchStudents("").catch(() => {});
    void call("/api/students?include_filters=true&limit=1")
      .then((value: { filters: { majors: string[]; levels: string[] } }) =>
        setMajorFilters(value.filters),
      )
      .catch(() => {});
  }, []);
  const rule = rules.find((r) => r.id === selected);
  return (
    <section className="evaluation-panel">
      <p>
        评分仅供模拟研究。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p className="notice compact-notice" role="status">{notice}</p>}

      <article className="card">
        <h3>为学生生成模拟评分</h3>
        <p>{rule ? `当前规则：${rule.config.name} / v${rule.version}` : "自动使用该生适用的规则。首次可直接使用内置模拟方案。"}</p>
        <details className="task-details"><summary>按专业缩小学生列表</summary>
        <label>
          学生列表专业筛选
          <select
            aria-label="学生列表专业筛选"
            value={studentMajor}
            onChange={(e) => {
              setStudentMajor(e.target.value);
              void perform(() => fetchStudents(e.target.value));
            }}
          >
            <option value="">全部专业（超过200人时请选择具体专业）</option>
            <optgroup label="同济大学硕士招生专业">
              {tongjiMajors.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </optgroup>
            {otherMajors.length > 0 && (
              <optgroup label="其他已导入专业">
                {otherMajors.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        </details>
        {studentTotal !== undefined && studentTotal > students.length && (
          <p>目前显示前 {students.length} 人，可按专业缩小范围。</p>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setSnapshot(undefined);
            void perform(async () => {
              const saved = await call("/api/evaluation-snapshots", {
                student_id: Number(f.get("student_id")),
                rule_id: selected,
              });
              setSnapshot(saved);
              await loadSnapshots();
            });
          }}
        >
          <label>
            学生研究编号
            <select aria-label="学生研究编号" name="student_id" required defaultValue="">
              <option value="">请选择已读取的授权学生</option>
              {students.map((student) => (
                <option key={student.id} value={student.id}>
                  {student.name ? `${student.name} · ${student.research_id}` : student.research_id}
                </option>
              ))}
            </select>
          </label>
          <button disabled={!!rule && !rule.enabled}>保存新评分快照</button>
        </form>
        <details className="task-details"><summary>查看历史评分</summary>
        <label>
          历史快照（进入本页自动读取，选中即重查当前授权）
          <select
            aria-label="历史快照"
            value={snapshot?.id ?? ""}
            onChange={(e) => {
              if (!e.target.value) return;
              setSnapshot(undefined);
              void perform(async () =>
                setSnapshot(
                  await call(`/api/evaluation-snapshots/${e.target.value}`),
                ),
              );
            }}
          >
            <option value="">请选择历史快照</option>
            {snapshots.map((s) => (
              <option key={s.id} value={s.id}>
                #{s.id} · {s.research_id} ·{" "}
                {s.total === null ? "未形成总分" : s.total.toFixed(2)} ·{" "}
                {new Date(s.as_of * 1000).toLocaleDateString()}
              </option>
            ))}
          </select>
        </label>
        </details>
      </article>
      <details className="card task-details"><summary>查看或更换评分规则</summary>
        <p>
          规则草稿与独立授权启用已集中到「业务规则管理」；本页选择已授权规则进行评分。
        </p>
        <div className="evaluation-table"><p className="table-hint">可左右滑动查看完整表格</p><div className="table-wrap"><table>
          <thead>
            <tr>
              <th>选择</th>
              <th>名称 / 版本</th>
              <th>范围</th>
              <th>状态</th>
              <th>业务确认</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><input type="radio" name="evaluation-rule" aria-label="自动匹配评分规则"
                checked={selected === undefined} onChange={() => setSelected(undefined)} /></td>
              <td colSpan={4}>按所选学生自动匹配</td>
            </tr>
            {rules.map((r) => (
              <tr key={r.id}>
                <td>
                  <input
                    type="radio"
                    name="evaluation-rule"
                    aria-label={`选择规则 ${r.id}`}
                    checked={selected === r.id}
                    onChange={() => setSelected(r.id)}
                  />
                </td>
                <td>
                  {r.config.name} / v{r.version}（#{r.id}）
                </td>
                <td>
                  {r.config.college} / {r.config.major}
                </td>
                <td>{r.enabled ? "模拟已启用" : "草稿或已替换"}</td>
                <td>
                  {r.confirmed_by || "未确认"}：{r.basis || "未提供依据"}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div></div>
      </details>
      <EvaluationDashboard refresh={snapshots[0]?.id ?? 0} openSnapshot={(id) => {
        setSnapshot(undefined);
        void perform(async () => {
          setSnapshot(await call(`/api/evaluation-snapshots/${id}`));
          window.requestAnimationFrame(() => document.getElementById("evaluation-evidence")?.scrollIntoView());
        });
      }} />
      {snapshot && (
        <article className="card" id="evaluation-evidence">
          <h3>
            快照 #{snapshot.id} ·{" "}
            {snapshot.total === null
              ? "数据不完整，未形成总分"
              : `${snapshot.total.toFixed(2)} / 100`}
          </h3>
          {snapshot.total === null && (
            <section aria-label="评分缺项">
              <h4>补齐以下指标后重新保存评分</h4>
              <ul>
                {snapshot.inputs.filter((input) => input.value === null).map((input) => (
                  <li key={input.feature}>{features[input.feature] ?? input.feature} · {input.missing || "缺少有效记录"}</li>
                ))}
              </ul>
            </section>
          )}
          <p>{snapshot.notice}</p>
          <StudentClusterDemo key={snapshot.id} id={snapshot.id} />
          <SixSignalTrial key={`trial-${snapshot.id}`} id={snapshot.id} />
          {snapshot.screening && <details className="task-details">
            <summary>前置条件核查</summary>
            <p>按当前登记数据核查。学分以完成培养要求总学分为通过条件，核查结果供模拟研究。</p>
            <ul>{snapshot.screening.map((item) => (
              <li key={item.name}>{item.name} · {item.status} · {item.reason}</li>
            ))}</ul>
          </details>}
          {snapshot.signals && <details className="task-details">
            <summary>六类识别信号与证据覆盖</summary>
            <p>以下依据来自这份快照，点击下方指标表可核对来源。</p>
            <table>
              <thead><tr><th>信号</th><th>可见证据</th><th>待核查项</th></tr></thead>
              <tbody>{snapshot.signals.map(({ name, items, note }) => (
                <tr key={name}><th scope="row">{name}</th>
                  <td>{items.length ? items.map((item) => (
                    <div key={item.feature}>{features[item.feature] ?? item.feature} · {item.value ?? item.missing ?? "待核查"}</div>
                  )) : "待核查"}</td>
                  <td>{note}</td>
                </tr>
              ))}</tbody>
            </table>
          </details>}
          {snapshot.band && snapshot.total !== null && (
            <p>{snapshot.band} · 70–85 分段按至少两个维度达到 80% 判定。前置条件核查单独显示。</p>
          )}
          <p>
            {snapshot.stale
              ? "来源已更新，请重新评分生成新快照"
              : "来源版本未变化"}{" "}
            · {snapshot.rule_name || "评分规则"} #{snapshot.rule_id} / v{snapshot.rule_version} ·{" "}
            {new Date(snapshot.as_of * 1000).toLocaleString()}
          </p>
          <button
            type="button"
            onClick={() =>
              void perform(async () => {
                const response = await fetch(
                  `/api/evaluation-snapshots/${snapshot.id}/export`,
                );
                if (!response.ok) {
                  const value = await response.json().catch(() => ({}));
                  throw Error(
                    typeof value.detail === "string"
                      ? value.detail
                      : "导出失败，请检查导出授权",
                  );
                }
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = `evaluation-snapshot-${snapshot.id}.xlsx`;
                link.click();
                URL.revokeObjectURL(url);
                setNotice(`快照 #${snapshot.id} 报告已导出`);
              })
            }
          >
            导出评分报告（需独立导出授权）
          </button>
          <div className="evaluation-charts">
            <div>
              <h4>{snapshot.ahp ? "维度雷达" : "指标雷达"}</h4>
              <Radar inputs={snapshot.ahp?.dimensions.map((dimension) => ({
                feature: dimension.name, normalized: dimension.normalized,
              })) ?? snapshot.inputs} />
              <p>缺失指标的顶点收至中心仅为闭合图形，数值不是0分。</p>
            </div>
            <div>
              <h4>总分成长（真实快照）</h4>
              <Growth
                snapshots={snapshots.filter(
                  (s) =>
                    s.student_id === snapshot.student_id &&
                    s.family_id === snapshot.family_id,
                )}
              />
            </div>
          </div>
          {snapshot.ahp && (
            <>
              <h4>模拟维度得分</h4>
              <ul>{snapshot.ahp.dimensions.map((dimension) => (
                <li key={dimension.name}>{dimension.name} · 权重 {(dimension.weight * 100).toFixed(0)}% · {
                  dimension.normalized === null ? "资料不足" : `${(dimension.normalized * 100).toFixed(1)} 分`
                }</li>
              ))}</ul>
              <p>创新活跃度、成长潜力需更多可靠数据和评价口径，暂不计分。</p>
              <details className="task-details">
                <summary>查看 AHP 权重依据</summary>
                <p>内置演示判断矩阵。每个维度内的指标等权，一致性比率 CR = {snapshot.ahp.consistency_ratio.toFixed(3)}，通过 0.10 阈值。</p>
                <div className="table-wrap"><table>
                  <thead><tr><th>维度</th>{snapshot.ahp.dimensions.map(({ name }) => <th key={name}>{name}</th>)}</tr></thead>
                  <tbody>{snapshot.ahp.matrix.map((row, index) => (
                    <tr key={snapshot.ahp?.dimensions[index].name}>
                      <th scope="row">{snapshot.ahp?.dimensions[index].name}</th>
                      {row.map((value, column) => <td key={column}>{value}</td>)}
                    </tr>
                  ))}</tbody>
                </table></div>
              </details>
            </>
          )}
          <details className="reading-note"><summary>查看各指标原值、权重与依据</summary><div className="evaluation-table"><div className="table-wrap"><table>
            <thead>
              <tr>
                <th>指标</th>
                <th>原值</th>
                <th>归一化值</th>
                <th>权重</th>
                <th>缺失原因与原始依据</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.inputs.map((v) => (
                <tr key={v.feature}>
                  <td>{features[v.feature]}</td>
                  <td>{v.value ?? "缺失"}</td>
                  <td>{v.normalized ?? "缺失"}</td>
                  <td>{v.weight}</td>
                  <td>
                    {v.missing || "无缺失"}
                    <details>
                      <summary>记录与版本依据</summary>
                      <EvidenceDetails data={v.evidence} />
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div></div></details>
          <details>
            <summary>数据版本摘要</summary>
            <code>{snapshot.data_digest}</code>
          </details>
        </article>
      )}
    </section>
  );
}
