import { CollegeSelect } from "./CollegeSelect";
import { useEffect, useState } from "react";

type Rule = {
  id: number;
  version: number;
  enabled: number;
  confirmed_by: string;
  basis: string;
  config: { name: string; college: string; major: string; mode: string };
};
type CandidateRule = {
  id: number;
  version: number;
  enabled: number;
  confirmed_by: string;
  basis: string;
  config: { name: string; synthetic: boolean };
};
const features: Record<string, string> = {
  course_pass_ratio: "课程通过比例（0—1）",
  research_paper_count: "科研论文成果数",
  patent_count: "专利成果数",
  award_count: "获奖成果数",
  conference_count: "会议成果数",
  latest_citation_count: "最新引用总数",
};

async function call(url: string, body: unknown | undefined, csrf: string) {
  const response = await fetch(
    url,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
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

function PassRules({ csrf }: { csrf: string }) {
  const [category, setCategory] = useState("courses"),
    [grading, setGrading] = useState("百分制"),
    [condition, setCondition] = useState(""),
    [reason, setReason] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [requiredCredits, setRequiredCredits] = useState(""),
    [college, setCollege] = useState(""),
    [major, setMajor] = useState(""),
    [course, setCourse] = useState(""),
    [term, setTerm] = useState(""),
    [rules, setRules] = useState(""),
    [error, setError] = useState("");
  async function request(url: string, body?: unknown) {
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
          typeof data.detail === "string" ? data.detail : "请检查完整条件及授权",
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
    grade: "",
    level: "",
    group_by: "",
  };
  return (
    <article className="card">
      <h3>课程通过规则与培养要求</h3>
      <p>
        没有默认分数线。规则按学院、专业、课程、评分制度和可选学期适用；保存生成新版本。通过规则在「培养过程分析」中只读引用。
      </p>
      {error && <p role="alert">{error}</p>}
      <label>
        规则环节
        <select
          aria-label="规则环节"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="courses">课程</option>
          <option value="topic">选题</option>
          <option value="midterm">中期</option>
        </select>
      </label>
      <CollegeSelect label="学院" value={college} onChange={setCollege} />
      <label>
        专业（须具体专业）
        <input value={major} onChange={(e) => setMajor(e.target.value)} />
      </label>
      <label>
        {category === "courses" ? "课程编号" : "考核批次"}
        <input value={course} onChange={(e) => setCourse(e.target.value)} />
      </label>
      <label>
        学期（可选）
        <input value={term} onChange={(e) => setTerm(e.target.value)} />
      </label>
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
          const r = await request("/api/pass-rules", {
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
          const r = await request(
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
              const r = await request("/api/training-requirements", {
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
    </article>
  );
}

function EvaluationRules({ csrf }: { csrf: string }) {
  const [rules, setRules] = useState<Rule[]>([]),
    [selected, setSelected] = useState<number>(),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [metrics, setMetrics] = useState([
      { feature: "patent_count", weight: 1, minimum: 0, maximum: 10 },
    ]);
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
    setRules((await call("/api/evaluation-rules", undefined, csrf)).items);
  }
  useEffect(() => {
    void perform(load); // eslint-disable-line react-hooks/exhaustive-deps
  }, []);
  const rule = rules.find((r) => r.id === selected);
  return (
    <article className="card">
      <h3>人才评价规则（模拟）</h3>
      <p>
        当前只支持模拟演示，不构成正式人才识别。评分入口在「拔尖人才模拟评价」，本页只负责规则版本。选择已有规则后可另存下一版本；原版本保持不变。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p className="notice compact-notice" role="status">{notice}</p>}
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
                  name="business-evaluation-rule"
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
      <details>
        <summary>新建不可覆盖的规则草稿</summary>
        <p>课程比例使用0—1，其他指标使用原始数量。</p>
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
              }, csrf);
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
          <CollegeSelect label="学院" name="college" required />
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
      <h4>独立授权确认启用</h4>
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
            }, csrf);
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
  );
}

function CandidateRules({ csrf }: { csrf: string }) {
  const [conditions, setConditions] = useState([
    { feature: "page_count", operator: "gte", value: 1 },
  ]);
  const [rules, setRules] = useState<CandidateRule[]>([]),
    [error, setError] = useState("");
  async function request(url: string, body?: unknown) {
    const r = await fetch(
      url,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
            body: JSON.stringify(body),
          },
    );
    const v = await r.json();
    if (!r.ok)
      throw Error(typeof v.detail === "string" ? v.detail : "输入无效");
    return v;
  }
  async function load() {
    setRules(await request("/api/candidate-rules"));
  }
  useEffect(() => {
    void load().catch((e) => setError(String(e)));
  }, []);
  return (
    <article className="card">
      <h3>优秀论文候选规则</h3>
      <p>
        辅助推荐供专家人工复核，不是正式评审结果或概率。默认无启用规则；合成规则仅用于软件验证。候选结果在「学位论文质量」中生成与复核。
      </p>
      {error && <p role="alert">{error}</p>}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          try {
            await request("/api/candidate-rules", {
              name: f.get("name"),
              college: f.get("college"),
              major: f.get("major"),
              level: f.get("level"),
              conditions,
              required_evidence: ["pages"],
              minimum_samples: Number(f.get("minimum_samples")),
              missing_policy: "insufficient",
              synthetic: f.get("synthetic") === "on",
              previous_id: f.get("previous_id")
                ? Number(f.get("previous_id"))
                : null,
            });
            await load();
            setError("");
          } catch (err) {
            setError(String(err));
          }
        }}
      >
        <h4>保存规则草稿新版本</h4>
        {[["name", "规则名称"], ["major", "适用专业／学科"], ["level", "培养层次"]].map(
          ([name, label]) => (
            <label key={name}>
              {label}
              <input name={name} required />
            </label>
          ),
        )}
        <CollegeSelect label="适用学院" name="college" required />
        <label>
          前一规则ID（新规则留空）
          <input name="previous_id" type="number" min="1" />
        </label>
        <label>
          优秀、普通组最小有效样本数
          <input
            name="minimum_samples"
            type="number"
            min="1"
            max="10000"
            defaultValue="1"
            required
          />
        </label>
        <label>
          <input name="synthetic" type="checkbox" />
          合成验证规则
        </label>
        <p>
          必要证据：可读原页；缺失策略：证据不足。所有条件须同时命中。特征仅支持
          page_count、character_count、section_count、reference_count，运算符仅支持
          gte、lte、eq；服务端拒绝任意代码和未知字段。
        </p>
        {conditions.map((c, i) => (
          <fieldset key={i}>
            <legend>特征条件 {i + 1}</legend>
            <select
              aria-label={`特征${i + 1}`}
              value={c.feature}
              onChange={(e) =>
                setConditions(
                  conditions.map((v, j) =>
                    j === i ? { ...v, feature: e.target.value } : v,
                  ),
                )
              }
            >
              {["page_count", "character_count", "section_count", "reference_count"].map(
                (k) => (
                  <option key={k}>{k}</option>
                ),
              )}
            </select>
            <select
              aria-label={`运算符${i + 1}`}
              value={c.operator}
              onChange={(e) =>
                setConditions(
                  conditions.map((v, j) =>
                    j === i ? { ...v, operator: e.target.value } : v,
                  ),
                )
              }
            >
              <option value="gte">大于等于</option>
              <option value="lte">小于等于</option>
              <option value="eq">等于</option>
            </select>
            <input
              aria-label={`阈值${i + 1}`}
              type="number"
              min="0"
              value={c.value}
              onChange={(e) =>
                setConditions(
                  conditions.map((v, j) =>
                    j === i ? { ...v, value: Number(e.target.value) } : v,
                  ),
                )
              }
            />
            {conditions.length > 1 && (
              <button
                type="button"
                onClick={() => setConditions(conditions.filter((_, j) => i !== j))}
              >
                移除条件
              </button>
            )}
          </fieldset>
        ))}
        <button
          type="button"
          disabled={conditions.length >= 20}
          onClick={() =>
            setConditions([...conditions, { feature: "page_count", operator: "gte", value: 1 }])
          }
        >
          添加条件
        </button>
        <button>保存候选规则草稿</button>
      </form>
      {rules.map((r) => (
        <article key={r.id}>
          <h3>
            {r.config.name} · ID {r.id} / v{r.version}
          </h3>
          <p>
            {r.enabled ? "已启用" : r.confirmed_by ? "历史确认版本" : "草稿"}
            · {r.config.synthetic ? "合成验证规则" : "业务规则"}
          </p>
          <pre>{JSON.stringify(r.config, null, 2)}</pre>
          {r.confirmed_by ? (
            <p>
              确认人：{r.confirmed_by}；依据：{r.basis}
            </p>
          ) : (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                try {
                  await request(`/api/candidate-rules/${r.id}/enable`, {
                    confirmed_by: f.get("confirmed_by"),
                    basis: f.get("basis"),
                  });
                  await load();
                  setError("");
                } catch (err) {
                  setError(String(err));
                }
              }}
            >
              <label>
                专家确认人
                <input name="confirmed_by" required />
              </label>
              <label>
                书面确认来源
                <input name="basis" required />
              </label>
              <button>确认启用此规则版本</button>
            </form>
          )}
        </article>
      ))}
    </article>
  );
}

export function BusinessRulesPanel({ csrf }: { csrf: string }) {
  return (
    <section className="business-rules-panel" aria-label="业务规则管理">
      <p className="eyebrow">BUSINESS RULES / 版本 · 确认 · 启用</p>
      <p className="muted">
        本页集中管理通过规则、培养要求、评价规则与候选规则的业务确认与启用；各分析页只读引用，不再混入写操作。写操作需要对应独立授权。
      </p>
      <PassRules csrf={csrf} />
      <EvaluationRules csrf={csrf} />
      <CandidateRules csrf={csrf} />
    </section>
  );
}
