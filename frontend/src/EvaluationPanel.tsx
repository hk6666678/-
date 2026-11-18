import { useState } from "react";
type Rule = {
  id: number;
  version: number;
  enabled: number;
  confirmed_by: string;
  basis: string;
  config: { name: string; college: string; major: string; mode: string };
};
type Snapshot = {
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

function Radar({ inputs }: { inputs: Snapshot["inputs"] }) {
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
              {features[v.feature]}
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
export function EvaluationPanel({ csrf }: { csrf: string }) {
  const [rules, setRules] = useState<Rule[]>([]),
    [selected, setSelected] = useState<number>(),
    [snapshot, setSnapshot] = useState<Snapshot>(),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [students, setStudents] = useState<
    { id: number; research_id: string }[]
  >([]);
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [studentTotal, setStudentTotal] = useState<number>();
  const [studentMajor, setStudentMajor] = useState("");
  const [metrics, setMetrics] = useState([
    { feature: "patent_count", weight: 1, minimum: 0, maximum: 10 },
  ]);
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
    setRules((await call("/api/evaluation-rules")).items);
  }
  async function loadSnapshots() {
    setSnapshots((await call("/api/evaluation-snapshots")).items);
  }
  const rule = rules.find((r) => r.id === selected);
  return (
    <section className="evaluation-panel">
      <p className="eyebrow">SIMULATION / 版本与证据</p>
      <p>
        当前只支持模拟演示，不构成正式人才识别。正式业务规则与业务验收尚未接入。权重和阈值由配置者明确提供，平台不预设官方权重。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p className="notice compact-notice" role="status">{notice}</p>}
      <article className="card">
        <h3>规则版本</h3>
        <button onClick={() => void perform(load)}>读取当前授权规则</button>
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
      </article>
      <article className="card">
        <details><summary>新建不可覆盖的规则草稿</summary>
        <p>
          选择已有规则后可另存下一版本；原版本保持不变。课程比例使用0—1，其他指标使用原始数量。
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void perform(async () => {
              const saved = await call("/api/evaluation-rules", {
                name: f.get("name"),
                college: f.get("college"),
                major: f.get("major"),
                mode: "simulation",
                metrics,
                expected_version: f.get("revise") && rule ? rule.version : 0,
                previous_id: f.get("revise") && rule ? rule.id : null,
              });
              await load();
              setSelected(saved.id);
              setNotice(`模拟草稿 #${saved.id} 已保存，尚未启用`);
            });
          }}
        >
          <label>
            规则名称
            <input name="name" required />
          </label>
          <label>
            学院
            <input list="tongji-colleges" name="college" required />
          </label>
          <label>
            专业
            <input name="major" required />
          </label>
          <label>
            <input type="checkbox" name="revise" disabled={!rule} />
            基于选中规则创建下一版本
          </label>
          <div className="evaluation-table"><p className="table-hint">可左右滑动查看完整表格</p><div className="table-wrap"><table>
            <thead>
              <tr>
                <th>指标</th>
                <th>权重</th>
                <th>归一化下限</th>
                <th>归一化上限</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((m, i) => (
                <tr key={i}>
                  <td>
                    <select
                      aria-label={`指标 ${i + 1}`}
                      value={m.feature}
                      onChange={(e) =>
                        setMetrics(
                          metrics.map((v, j) =>
                            j === i ? { ...v, feature: e.target.value } : v,
                          ),
                        )
                      }
                    >
                      {Object.entries(features).map(([v, label]) => (
                        <option key={v} value={v}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  {(["weight", "minimum", "maximum"] as const).map((key) => (
                    <td key={key}>
                      <input
                        aria-label={`${key} ${i + 1}`}
                        type="number"
                        step="any"
                        required
                        value={m[key]}
                        onChange={(e) =>
                          setMetrics(
                            metrics.map((v, j) =>
                              j === i
                                ? { ...v, [key]: Number(e.target.value) }
                                : v,
                            ),
                          )
                        }
                      />
                    </td>
                  ))}
                  <td>
                    <button
                      type="button"
                      disabled={metrics.length === 1}
                      onClick={() =>
                        setMetrics(metrics.filter((_, j) => i !== j))
                      }
                    >
                      移除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div></div>
          <button
            type="button"
            disabled={metrics.length >= 6}
            onClick={() =>
              setMetrics([
                ...metrics,
                {
                  feature: "research_paper_count",
                  weight: 1,
                  minimum: 0,
                  maximum: 10,
                },
              ])
            }
          >
            添加指标
          </button>
          <button>保存模拟草稿</button>
        </form>
        </details>
      </article>
      <article className="card">
        <h3>独立授权确认启用</h3>
        <p>
          当前选择：{rule ? `#${rule.id} / v${rule.version}` : "尚未选择"}
          。启用需要独立权限，填写业务确认人和依据。
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void perform(async () => {
              await call(`/api/evaluation-rules/${selected}/activate`, {
                expected_version: rule?.version,
                confirmed_by: f.get("confirmed_by"),
                basis: f.get("basis"),
                acknowledge_simulation: true,
              });
              await load();
              setNotice("已启用模拟版本；不构成正式人才识别");
            });
          }}
        >
          <label>
            业务确认人
            <input name="confirmed_by" required />
          </label>
          <label>
            确认依据
            <textarea name="basis" required />
          </label>
          <label>
            <input type="checkbox" required />
            确认仅用于模拟演示
          </label>
          <button disabled={!rule || !!rule.enabled}>确认启用模拟规则</button>
        </form>
      </article>
      <article className="card">
        <h3>按真实数据版本评分</h3>
        <label>
          学生列表专业筛选
          <input
            value={studentMajor}
            onChange={(e) => setStudentMajor(e.target.value)}
          />
        </label>
        <button
          type="button"
          onClick={() =>
            void perform(async () => {
              setStudents([]);
              setStudentTotal(undefined);
              const data = await call(
                `/api/students?limit=200&offset=0&major=${encodeURIComponent(studentMajor)}`,
              );
              setStudents(data.items);
              setStudentTotal(data.total);
            })
          }
        >
          读取当前授权学生
        </button>
        <p>
          {studentTotal === undefined
            ? "尚未读取学生列表"
            : `当前授权和专业筛选下共${studentTotal}人，仅显示前${students.length}人；超过200人请按专业缩小范围`}
          。列表沿用档案脱敏边界，评分时重新核验当前身份和数据权限。
        </p>
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
                  {student.research_id}
                </option>
              ))}
            </select>
          </label>
          <button disabled={!rule || !rule.enabled}>保存新评分快照</button>
        </form>
        <button type="button" onClick={() => void perform(loadSnapshots)}>
          读取历史快照列表
        </button>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setSnapshot(undefined);
            void perform(async () =>
              setSnapshot(
                await call(`/api/evaluation-snapshots/${f.get("snapshot_id")}`),
              ),
            );
          }}
        >
          <label>
            历史快照
            <select aria-label="历史快照" name="snapshot_id" required defaultValue="">
              <option value="">请选择已读取的历史快照</option>
              {snapshots.map((s) => (
                <option key={s.id} value={s.id}>
                  #{s.id} · {s.research_id} ·{" "}
                  {s.total === null ? "未形成总分" : s.total.toFixed(2)} ·{" "}
                  {new Date(s.as_of * 1000).toLocaleDateString()}
                </option>
              ))}
            </select>
          </label>
          <button disabled={!snapshots.length}>读取快照并重查当前授权</button>
        </form>
      </article>
      {snapshot && (
        <article className="card">
          <h3>
            快照 #{snapshot.id} ·{" "}
            {snapshot.total === null
              ? "数据不完整，未形成总分"
              : `${snapshot.total.toFixed(2)} / 100`}
          </h3>
          <p>{snapshot.notice}</p>
          <p>
            {snapshot.stale
              ? "来源已更新，请重新评分生成新快照"
              : "来源版本未变化"}{" "}
            · 规则 #{snapshot.rule_id} / v{snapshot.rule_version} ·{" "}
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
              <h4>指标雷达</h4>
              <Radar inputs={snapshot.inputs} />
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
          <div className="evaluation-table"><p className="table-hint">可左右滑动查看完整表格</p><div className="table-wrap"><table>
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
                      <pre>{JSON.stringify(v.evidence, null, 2)}</pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div></div>
          <details>
            <summary>数据版本摘要</summary>
            <code>{snapshot.data_digest}</code>
          </details>
        </article>
      )}
    </section>
  );
}
