import { CollegeSelect } from "./CollegeSelect";
import { useEffect, useState } from "react";
type Batch = {
  id: string;
  valid_count: number;
  errors: { row: number; message: string }[];
};
type Template = {
  version: string;
  state: string;
  simulation: boolean;
  items: Record<string, number>;
  confirmed_by?: string;
  basis?: string;
};
type Item = {
  id: number;
  category: string;
  paper_version_id: number;
  batch: string;
  anonymous_code: string;
  template_version: string;
  scores: Record<string, number>;
  comment?: string;
};
export function AssessmentPanel({ csrf }: { csrf: string }) {
  const [items, setItems] = useState<Item[]>([]),
    [batch, setBatch] = useState<Batch>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false),
    [notice, setNotice] = useState(""),
    [templates, setTemplates] = useState<Template[]>([]);
  const [keywordResult, setKeywordResult] = useState<{
    counts: Record<string, number>; scanned: number; skipped: number;
    categories?: Record<string, { review_id: number; quote: string }[]>;
  }>();
  const [keywordBusy, setKeywordBusy] = useState(false);
  const comparisons = new Map<string, { paper: number; template: string; item: string; blind: number[]; defense: number[] }>();
  for (const row of items) {
    for (const [item, score] of Object.entries(row.scores)) {
      const key = JSON.stringify([row.paper_version_id, row.template_version, item]);
      const pair = comparisons.get(key) ?? { paper: row.paper_version_id, template: row.template_version, item, blind: [], defense: [] };
      (row.category === "blind_reviews" ? pair.blind : pair.defense).push(score);
      comparisons.set(key, pair);
    }
  }
  const pairs = [...comparisons.values()].filter(({ blind, defense }) => blind.length && defense.length);
  const mean = (scores: number[]) => scores.reduce((sum, score) => sum + score, 0) / scores.length;
  async function call(url: string, init?: RequestInit) {
    const r = await fetch(url, init);
    const v = await r.json();
    if (!r.ok)
      throw Error(typeof v.detail === "string" ? v.detail : "字段校验失败");
    return v;
  }
  async function load() {
    const v = await call("/api/external-assessments");
    setItems(v.items);
    setLoaded(true);
    setTemplates((await call("/api/external-assessments/templates")).items);
  }
  useEffect(() => {
    void load().catch((e) => setError(String(e)));
  }, []);
  return (
    <section className="assessment-panel">
      <p className="assessment-note">
        评分模板默认使用模拟配置。
      </p>
      {error && (
        <p className="assessment-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="assessment-success" role="status">
          {notice}
        </p>
      )}
      <details className="card assessment-import task-details">
        <summary>导入考核记录</summary>
        <a
          className="secondary assessment-download"
          href="/api/external-assessments/template"
        >
          下载标准Excel模板 · simulation-v1
        </a>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            setBusy(true);
            setError("");
            setNotice("");
            setBatch(undefined);
            try {
              setBatch(
                await call("/api/external-assessments/import/preview", {
                  method: "POST",
                  headers: { "X-CSRF-Token": csrf },
                  body: data,
                }),
              );
            } catch (err) {
              setError(String(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            标准Excel文件
            <input
              name="file"
              type="file"
              accept=".xlsx"
              required
              onChange={() => setBatch(undefined)}
            />
          </label>
          <button disabled={busy}>上传并预览</button>
        </form>
      </details>
      <div className="card assessment-records">
        <h3>考核记录</h3>
        <button onClick={() => void load().catch((e) => setError(String(e)))}>
          刷新记录
        </button>
        {!loaded ? (
          <p>正在读取…</p>
        ) : items.length === 0 ? (
          <p>当前范围暂无可见记录。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>类别</th>
                <th>论文版本</th>
                <th>批次</th>
                <th>匿名编号</th>
                <th>模板版本</th>
                <th>分项成绩</th>
                <th>意见</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td>{i.category === "blind_reviews" ? "盲审" : "答辩"}</td>
                  <td>{i.paper_version_id}</td>
                  <td>{i.batch}</td>
                  <td>{i.anonymous_code}</td>
                  <td>{i.template_version}</td>
                  <td>
                    {Object.entries(i.scores)
                      .map(
                        ([key, value]) =>
                          `${key === "quality" ? "质量" : key}：${value}`,
                      )
                      .join("；")}
                  </td>
                  <td>{i.comment ?? "需原文读取授权"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <details className="card">
        <summary>盲审意见关键词统计</summary>
        <form onSubmit={async (e) => {
          e.preventDefault();
          const terms = String(new FormData(e.currentTarget).get("terms")).replaceAll("，", ",");
          setKeywordResult(undefined);
          setError("");
          setKeywordBusy(true);
          try {
            setKeywordResult(await call(`/api/external-assessments/keywords?${new URLSearchParams({ terms, classify: "true" })}`));
          } catch (err) {
            setError(String(err));
          } finally {
            setKeywordBusy(false);
          }
        }}>
          <label>关键词（逗号分隔）<input name="terms" required maxLength={1600}
            defaultValue="创新性,创新点,研究方法,数据不足,论证不足,写作规范,参考文献" /></label>
          <button disabled={keywordBusy}>统计关键词</button>
        </form>
        {keywordResult && <>
          <p>已统计 {keywordResult.scanned} 条，因评语下载未授权跳过 {keywordResult.skipped} 条。按字面匹配出现次数。</p>
          <ul>{Object.entries(keywordResult.counts).map(([word, count]) => <li key={word}>{word} · {count} 次</li>)}</ul>
          {keywordResult.categories && (
            <details>
              <summary>评语分类与原句</summary>
              <p>按关键字匹配原句，每类最多显示 20 条。涉及创新的句子也可能是负面评价。</p>
              {Object.entries(keywordResult.categories).map(([topic, excerpts]) => (
                <div key={topic}><h4>{topic}</h4>
                  {excerpts.length ? <ul>{excerpts.map((item, index) => (
                    <li key={`${item.review_id}-${index}`}>评语 #{item.review_id} · {item.quote}</li>
                  ))}</ul> : <p>暂无匹配原句。</p>}
                </div>
              ))}
            </details>
          )}
        </>}
      </details>
      <details className="card">
        <summary>盲审与答辩评分一致性</summary>
        <p>按同一论文版本、同一评分模板和评分项对比均值。差值为答辩减盲审。</p>
        {pairs.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>论文版本</th><th>模板与评分项</th><th>盲审均值</th><th>答辩均值</th><th>差值</th></tr></thead>
              <tbody>{pairs.map(({ paper, template, item, blind, defense }) => (
                <tr key={JSON.stringify([paper, template, item])}>
                  <td>{paper}</td><td>{template} · {item}</td>
                  <td>{mean(blind).toFixed(2)}（{blind.length} 条）</td>
                  <td>{mean(defense).toFixed(2)}（{defense.length} 条）</td>
                  <td>{(mean(defense) - mean(blind)).toFixed(2)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : <p>{loaded ? "暂无同模板的可比较评分。" : "正在读取评分。"}</p>}
      </details>

      {batch && (
        <section className="card assessment-preview">
          <h3>预览批次</h3>
          <p className="assessment-note" title={batch.id}>
            批次 {batch.id.slice(0, 8)}
          </p>
          <p>
            可导入 {batch.valid_count} 行 · 错误 {batch.errors.length} 行
          </p>
          {batch.errors.length > 0 && (
            <>
              <p className="assessment-error" role="alert">
                <strong>{batch.errors.length} 行错误，无法确认</strong>
                <br />
                请按行号修改Excel，再重新上传。
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Excel行号</th>
                    <th>错误原因</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.errors.map((e) => (
                    <tr key={e.row}>
                      <td>{e.row}</td>
                      <td>{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <a href={`/api/external-assessments/import/${batch.id}/errors`}>
                查看错误报告
              </a>
            </>
          )}
          <button
            disabled={
              busy || batch.errors.length > 0 || batch.valid_count === 0
            }
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                await call(
                  `/api/external-assessments/import/${batch.id}/confirm`,
                  { method: "POST", headers: { "X-CSRF-Token": csrf } },
                );
                setBatch(undefined);
                setNotice("批次已确认");
                await load();
              } catch (err) {
                setError(String(err));
              } finally {
                setBusy(false);
              }
            }}
          >
            确认导入本批次
          </button>
        </section>
      )}
      <details className="assessment-templates">
        <summary>评分模板版本管理</summary>
        <p>
          维护权限创建不可覆盖的新草稿；独立启用权限与业务确认后方可用于导入。旧记录继续引用原版本。
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setError("");
            try {
              await call("/api/external-assessments/templates", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "X-CSRF-Token": csrf,
                },
                body: JSON.stringify({
                  version: f.get("version"),
                  category: f.get("category"),
                  college: f.get("college"),
                  major: f.get("major"),
                  items: JSON.parse(String(f.get("items"))),
                  simulation: f.get("simulation") === "on",
                }),
              });
              setNotice("模板草稿已保存");
              await load();
            } catch (err) {
              setError(String(err));
            }
          }}
        >
          <label>
            版本号
            <input name="version" required />
          </label>
          <label>
            类别
            <select name="category">
              <option value="blind_reviews">盲审</option>
              <option value="defenses">答辩</option>
            </select>
          </label>
          <CollegeSelect label="学院" name="college" required />
          <label>
            专业
            <input name="major" required />
          </label>
          <label>
            分项上限JSON
            <input name="items" defaultValue={'{"quality":100}'} required />
          </label>
          <label>
            <input name="simulation" type="checkbox" defaultChecked />
            模拟配置
          </label>
          <button>保存新版本草稿</button>
        </form>
        <table>
          <thead>
            <tr>
              <th>版本</th>
              <th>状态</th>
              <th>配置</th>
              <th>业务确认</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.version}>
                <td>{t.version}</td>
                <td>
                  {t.simulation ? "模拟" : "正式"} ·{" "}
                  {t.state === "active" ? "已启用" : "草稿"}
                </td>
                <td>
                  {Object.entries(t.items)
                    .map(
                      ([key, value]) =>
                        `${key === "quality" ? "质量" : key}：上限 ${value}`,
                    )
                    .join("；")}
                </td>
                <td>
                  {t.state === "draft" ? (
                    <form
                      onSubmit={async (e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        try {
                          await call(
                            `/api/external-assessments/templates/${encodeURIComponent(t.version)}/activate`,
                            {
                              method: "POST",
                              headers: {
                                "Content-Type": "application/json",
                                "X-CSRF-Token": csrf,
                              },
                              body: JSON.stringify({
                                confirmed_by: f.get("confirmed_by"),
                                basis: f.get("basis"),
                              }),
                            },
                          );
                          setNotice("模板已启用");
                          await load();
                        } catch (err) {
                          setError(String(err));
                        }
                      }}
                    >
                      <label>
                        业务确认人
                        <input name="confirmed_by" required />
                      </label>
                      <label>
                        确认依据
                        <input name="basis" required />
                      </label>
                      <button>确认启用此版本</button>
                    </form>
                  ) : (
                    `${t.confirmed_by ?? "系统模拟配置"} · ${t.basis ?? "演示使用"}`
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
