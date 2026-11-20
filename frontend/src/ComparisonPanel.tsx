import { useEffect, useState } from "react";

type Paper = { id: number; version: number; title?: string; level: string; discipline: string; year: string };
type Label = { version: number; label: string; basis: string; confirmed_by: string };
type History = { label: string; version: number; items: Label[] };
type Comparison = {
  id: number; stale?: boolean; notice: string;
  target_features: Record<string, number | null>;
  groups: Record<string, { sample_count: number; features: Record<string, { mean: number | null; denominator: number }> }>;
};
type TextComparison = {
  passage_counts: [number, number];
  matches: { left: { page: number; text: string }; right: { page: number; text: string }; similarity: number }[];
};
type Classification = {
  model_version: string; label: string | null; score: number | null;
  trained_at: number;
  recipe: { algorithm: string; l2: number; training_seed: number; holdout_seed: number };
  inputs: Record<string, number | null>;
  validation: { training_count: number; holdout_count: number; correct: number; false_positive: number; false_negative: number };
};
const features: Record<string, string> = {
  page_count: "页数", character_count: "字数", section_count: "章节数", reference_count: "参考文献数",
};

export function ComparisonPanel({ csrf, onCreated }: { csrf: string; onCreated?: (id: number) => void }) {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [id, setId] = useState("");
  const [history, setHistory] = useState<History>();
  const [error, setError] = useState("");
  const [labelError, setLabelError] = useState("");
  const [result, setResult] = useState<Comparison>();
  const [textResult, setTextResult] = useState<TextComparison>();
  const [classification, setClassification] = useState<Classification>();
  const [classifier, setClassifier] = useState("synthetic-logistic-v1");
  const [classificationRuns, setClassificationRuns] = useState<Record<string, Classification>>({});
  const [busy, setBusy] = useState(false);

  async function call(url: string, body?: unknown) {
    const response = await fetch(url, body === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === "string" ? data.detail : "请检查输入和权限");
    return data;
  }

  useEffect(() => {
    void call("/api/papers").then((data) => setPapers(data.items)).catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!id) return;
    let current = true;
    void call("/api/papers/" + id + "/labels").then((data) => {
      if (current) setHistory(data);
    }).catch((err) => { if (current) setLabelError(String(err)); });
    return () => { current = false; };
  }, [id]);

  return (
    <section className="card">
      <h2>专家样本标签与同类比较</h2>
      {error && <p role="alert">{error}</p>}
      <label>比较论文
        <select aria-label="比较论文" value={id} disabled={busy} onChange={(event) => {
          setId(event.target.value);
          setHistory(undefined);
          setLabelError("");
          setResult(undefined);
          setTextResult(undefined);
          setClassification(undefined);
          setClassificationRuns({});
          setError("");
        }}>
          <option value="">请选择论文</option>
          {papers.map((paper) => <option key={paper.id} value={paper.id}>
            {paper.title || "论文（身份已隐藏）"} · 版本 {paper.version} · {paper.discipline || "学科缺失"}
          </option>)}
        </select>
      </label>
      <form onSubmit={async (event) => {
        event.preventDefault();
        if (!id) return;
        const data = new FormData(event.currentTarget);
        setBusy(true);
        setError("");
        try {
          const comparison = await call("/api/papers/" + id + "/comparisons", { year: data.get("year") });
          setResult(comparison);
          onCreated?.(comparison.id);
        } catch (err) {
          setError(String(err));
        } finally {
          setBusy(false);
        }
      }}>
        <button disabled={!id || busy}>生成同类比较</button>
        <details className="task-details">
          <summary>限定比较年度</summary>
          <label>比较年度（留空全部）<input name="year" /></label>
        </details>
      </form>
      {id && <details className="task-details" key={`classify-${id}`}>
        <summary>优秀论文训练与推理演练</summary>
        <p>本地逻辑回归使用合成标签训练。仅供流程演示。</p>
        <label>论文分类模型版本<select value={classifier} disabled={busy} onChange={(e) => setClassifier(e.target.value)}>
          <option value="synthetic-logistic-v1">v1 · 基准正则化</option>
          <option value="synthetic-logistic-v2">v2 · 较强正则化</option>
        </select></label>
        <button type="button" disabled={busy} onClick={async () => {
          setBusy(true);
          setError("");
          setClassification(undefined);
          try {
            const next: Classification = await call(`/api/papers/${id}/classification-demo?model_version=${classifier}`);
            setClassification(next);
            setClassificationRuns((runs) => ({ ...runs, [next.model_version]: next }));
          } catch (err) {
            setError(String(err));
          } finally {
            setBusy(false);
          }
        }}>运行模拟分类</button>
        {classification && <>
          <p>{classification.label ?? "输入缺失"}{classification.score == null ? "" : ` · 模型输出 ${classification.score.toFixed(3)}`} · {classification.model_version}</p>
          <p>L2 {classification.recipe.l2} · 训练种子 {classification.recipe.training_seed} · 留出种子 {classification.recipe.holdout_seed}</p>
          <p>训练档案保存于 {new Date(classification.trained_at * 1000).toLocaleString()}。</p>
          <p>合成训练样本 {classification.validation.training_count} 条 · 合成留出样本 {classification.validation.holdout_count} 条 · 判对 {classification.validation.correct} 条 · 误判优秀 {classification.validation.false_positive} 条 · 漏判优秀 {classification.validation.false_negative} 条。</p>
          <ul>{Object.entries(classification.inputs).map(([key, value]) => (
            <li key={key}>{features[key] ?? key} · {value ?? "缺失"}</li>
          ))}</ul>
        </>}
        {Object.keys(classificationRuns).length > 1 && <table>
          <thead><tr><th>版本</th><th>同一论文的输出</th><th>同一留出集判对</th><th>误判优秀</th><th>漏判优秀</th></tr></thead>
          <tbody>{Object.values(classificationRuns).map((run) => <tr key={run.model_version}>
            <td>{run.model_version}</td><td>{run.score?.toFixed(3) ?? "缺失"}</td><td>{run.validation.correct}/{run.validation.holdout_count}</td>
            <td>{run.validation.false_positive}</td><td>{run.validation.false_negative}</td>
          </tr>)}</tbody>
        </table>}
      </details>}
      {id && (
        <details className="task-details" key={`text-${id}`}>
          <summary>论文正文片段比对</summary>
          <form onSubmit={async (event) => {
            event.preventDefault();
            const other = String(new FormData(event.currentTarget).get("other"));
            setBusy(true);
            setError("");
            setTextResult(undefined);
            try {
              setTextResult(await call(`/api/papers/${id}/text-comparison?${new URLSearchParams({ other_id: other })}`));
            } catch (err) {
              setError(String(err));
            } finally {
              setBusy(false);
            }
          }}>
            <label>对照论文
              <select name="other" required disabled={busy} onChange={() => setTextResult(undefined)}>
                <option value="">请选择另一论文版本</option>
                {papers.filter((paper) => String(paper.id) !== id).map((paper) => (
                  <option key={paper.id} value={paper.id}>{paper.title || "论文（身份已隐藏）"} · 版本 {paper.version} · #{paper.id}</option>
                ))}
              </select>
            </label>
            <button disabled={busy}>比对正文片段</button>
          </form>
          <p>按已解析文字的字面重合度匹配，参考文献标题之后的内容排除。每篇最多取 120 个片段，结果供人工查阅。</p>
          {textResult && (
            <>
              <p>取样 {textResult.passage_counts[0]} / {textResult.passage_counts[1]} 个片段。</p>
              {textResult.matches.length ? <table>
                <thead><tr><th>当前论文</th><th>对照论文</th><th>字面相似度</th></tr></thead>
                <tbody>{textResult.matches.map((match, index) => (
                  <tr key={index}>
                    <td>第 {match.left.page} 页 · {match.left.text}</td>
                    <td>第 {match.right.page} 页 · {match.right.text}</td>
                    <td>{(match.similarity * 100).toFixed(1)}%</td>
                  </tr>
                ))}</tbody>
              </table> : <p>未找到达到 40% 字面相似度的片段。</p>}
            </>
          )}
        </details>
      )}
      {result && (
        <>
          <h3>同类论文比较结果</h3><p>{papers.find(paper => String(paper.id) === id)?.title || "论文（身份已隐藏）"}</p>
          <p>{result.stale ? "比较结果已过时，请重新生成。" : result.notice}</p>
          {Object.keys(result.groups).length > 0 && <div className="table-wrap comparison-result"><table>
            <thead><tr><th>指标</th><th>当前论文</th>{Object.entries(result.groups).map(([name, group]) =>
              <th key={name}>{name}组均值（{group.sample_count} 篇）</th>)}</tr></thead>
            <tbody>{Object.entries(result.target_features).map(([key, value]) => (
              <tr key={key}><th scope="row">{features[key] ?? key}</th><td>{value ?? "缺失"}</td>
                {Object.entries(result.groups).map(([name, group]) => {
                  const feature = group.features[key];
                  return <td key={name}>{feature?.mean == null ? "缺失" : feature.mean.toFixed(1) + "（" + feature.denominator + " 篇）"}</td>;
                })}
              </tr>
            ))}</tbody>
          </table></div>}
          <details className="task-details">
            <summary>比较版本与导出</summary>
            <button className="secondary" onClick={() => void call("/api/paper-comparisons/" + result.id).then(setResult).catch((err) => setError(String(err)))}>检查历史比较是否过时</button>
            <a href={"/api/paper-comparisons/" + result.id + "/export"}>下载比较 Excel</a>
          </details>
        </>
      )}
      {id && (
        <details className="task-details" key={id}>
          <summary>样本标签{history ? " · " + history.label : ""}</summary>
          {labelError && <p role="alert">{labelError}</p>}
          {history && <>
            <form onSubmit={async (event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              try {
                await call("/api/papers/" + id + "/labels", {
                  label: fields.get("label"), confirmed_by: fields.get("confirmed_by"), basis: fields.get("basis"), expected_version: history.version,
                });
                setHistory(await call("/api/papers/" + id + "/labels"));
                setLabelError("");
              } catch (err) {
                setLabelError(String(err));
              }
            }}>
              <label>样本标签<select name="label" aria-label="样本标签" defaultValue={history.label}><option>待评</option><option>优秀</option><option>普通</option></select></label>
              <label>业务确认人<input name="confirmed_by" required /></label>
              <label>确认依据<input name="basis" required /></label>
              <button>保存标签新版本</button>
            </form>
            {history.items.length > 0 && <ul>{history.items.map((item) => (
              <li key={item.version}>v{item.version} · {item.label} · {item.confirmed_by} · {item.basis}</li>
            ))}</ul>}
          </>}
        </details>
      )}
    </section>
  );
}
