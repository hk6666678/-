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
  rule_id: number;
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
const features: Record<string, string> = {
  course_pass_ratio: "课程通过比例（0—1）",
  research_paper_count: "科研论文成果数",
  patent_count: "专利成果数",
  award_count: "获奖成果数",
  conference_count: "会议成果数",
  latest_citation_count: "最新引用总数",
};
export function EvaluationPanel({ csrf }: { csrf: string }) {
  const [rules, setRules] = useState<Rule[]>([]),
    [selected, setSelected] = useState<number>(),
    [snapshot, setSnapshot] = useState<Snapshot>(),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [students, setStudents] = useState<
    { id: number; research_id: string }[]
  >([]);
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
  const rule = rules.find((r) => r.id === selected);
  return (
    <section className="evaluation-panel">
      <p className="eyebrow">SIMULATION / 版本与证据</p>
      <h2>人才指标模拟评价</h2>
      <p>
        当前只支持模拟演示，不构成正式人才识别。正式业务规则与业务验收尚未接入。权重和阈值由配置者明确提供，平台不预设官方权重。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <article className="card">
        <h3>规则版本</h3>
        <button onClick={() => void perform(load)}>读取当前授权规则</button>
        <table>
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
        </table>
      </article>
      <article className="card">
        <h3>新建不可覆盖的规则草稿</h3>
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
            <input name="college" required />
          </label>
          <label>
            专业
            <input name="major" required />
          </label>
          <label>
            <input type="checkbox" name="revise" disabled={!rule} />
            基于选中规则创建下一版本
          </label>
          <table>
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
          </table>
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
            void perform(async () =>
              setSnapshot(
                await call("/api/evaluation-snapshots", {
                  student_id: Number(f.get("student_id")),
                  rule_id: selected,
                }),
              ),
            );
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
            历史快照编号
            <input name="snapshot_id" type="number" min="1" required />
          </label>
          <button>读取快照并重查当前授权</button>
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
          <table>
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
          </table>
          <details>
            <summary>数据版本摘要</summary>
            <code>{snapshot.data_digest}</code>
          </details>
          <p>成长曲线尚未接入；年份不足不生成虚构历史。</p>
        </article>
      )}
    </section>
  );
}
