import { useEffect, useState } from "react";

type Paper = { id: number; version: number; title?: string; level: string; discipline: string; year: string };
type Label = { version: number; label: string; basis: string; confirmed_by: string };
type History = { label: string; version: number; items: Label[] };
type Comparison = {
  id: number; stale?: boolean; notice: string;
  target_features: Record<string, number | null>;
  groups: Record<string, { sample_count: number; features: Record<string, { mean: number | null; denominator: number }> }>;
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
      {result && (
        <>
          <p>{result.stale ? "比较结果已过时，请重新生成。" : result.notice}</p>
          {Object.keys(result.groups).length > 0 && <div className="table-wrap"><table>
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
