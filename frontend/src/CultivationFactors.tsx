import { useState } from "react";
import { CollegeSelect } from "./CollegeSelect";

type Result = {
  sample_size: number;
  excluded: number;
  notice?: string;
  factors?: { factor: string; coefficient: number; interval: [number, number] | null; p_value: number | null }[];
  rank_correlations?: { factor: string; rho: number | null }[];
  logistic?: { positive: number; negative: number; notice?: string; factors?: { factor: string; odds_ratio: number }[] };
  midterm_thesis?: {
    sample_size: number; excluded: number; pearson_r: number | null;
    points: { midterm: number; quality: number; paper_version_id: number }[];
  } | null;
};

export function CultivationFactors() {
  const [college, setCollege] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result>();
  return (
    <section className="card">
      <p>查看同届学生的选题、中期成绩与模拟评分之间的关联。</p>
      <form onSubmit={async (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const query = new URLSearchParams({
          college: college.trim(), major: String(data.get("major")).trim(), entry_year: String(data.get("entry_year")),
        });
        setBusy(true);
        setError("");
        setResult(undefined);
        try {
          const response = await fetch(`/api/cultivation/factors?${query}`);
          const body = await response.json();
          if (!response.ok) throw Error(typeof body.detail === "string" ? body.detail : "请检查所选范围");
          setResult(body);
        } catch (err) {
          setError(String(err));
        } finally {
          setBusy(false);
        }
      }}>
        <CollegeSelect label="学院" value={college} onChange={setCollege} required />
        <label>专业<input name="major" required /></label>
        <label>入学年份<input name="entry_year" type="number" min="1900" max="2100" required /></label>
        <button disabled={busy || !college.trim()}>{busy ? "正在计算…" : "分析影响因素"}</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <h3>影响因素分析结果</h3>
          <p>完整样本 {result.sample_size} 人 · 排除 {result.excluded} 人</p>
          {result.notice && <p>{result.notice}</p>}
          {result.factors && <div className="table-wrap"><table>
            <thead><tr><th>因素</th><th>回归系数</th><th>95% 置信区间</th><th>p 值</th></tr></thead>
            <tbody>{result.factors.map((row) => (
              <tr key={row.factor}><th scope="row">{row.factor}</th>
                <td>{row.coefficient.toFixed(3)}</td>
                <td>{row.interval?.map((value) => value.toFixed(3)).join(" 至 ") ?? "不可估计"}</td>
                <td>{row.p_value?.toPrecision(3) ?? "不可估计"}</td>
              </tr>
            ))}</tbody>
          </table></div>}
          {result.rank_correlations && (
            <p>Spearman 秩相关 · {result.rank_correlations.map(({ factor, rho }) => `${factor} ${rho?.toFixed(3) ?? "不可估计"}`).join(" · ")}</p>
          )}
          {result.logistic && (
            <>
              <h4>85 分模拟达标关联</h4>
              <p>达标 {result.logistic.positive} 人 · 未达标 {result.logistic.negative} 人</p>
              {result.logistic.notice && <p>{result.logistic.notice}</p>}
              {result.logistic.factors && <p>每增加 10 分的优势比 · {result.logistic.factors.map(({ factor, odds_ratio }) => `${factor} ${odds_ratio.toFixed(3)}`).join(" · ")}。采用带 L2 惩罚的 Logistic 回归，仅供探索。</p>}
            </>
          )}
          {result.midterm_thesis && (
            <details className="task-details">
              <summary>中期成绩与学位论文盲审质量</summary>
              <p>完整样本 {result.midterm_thesis.sample_size} 人 · 排除 {result.midterm_thesis.excluded} 人 · Pearson r {result.midterm_thesis.pearson_r?.toFixed(3) ?? "不可估计"}</p>
              <p>取最新论文版本中同一模拟模板的盲审质量分均值。至少 3 个可比样本才计算相关系数。</p>
              <table>
                <thead><tr><th>论文版本</th><th>中期成绩</th><th>盲审质量均分</th></tr></thead>
                <tbody>{result.midterm_thesis.points.map((point) => (
                  <tr key={point.paper_version_id}><td>#{point.paper_version_id}</td><td>{point.midterm}</td><td>{point.quality.toFixed(2)}</td></tr>
                ))}</tbody>
              </table>
            </details>
          )}
          <details className="task-details">
            <summary>计算口径</summary>
            <p>以最近录入的有效百分制选题、中期成绩为自变量，以最新有效且同一规则版本的模拟总分为因变量。系数表示另一因素固定时，成绩每增加一分对应的模拟总分差异。缺分、过时或无权读取的快照不进入计算。区间与 p 值基于线性回归的常规假设，仅用于探索变量关联。</p>
          </details>
        </>
      )}
    </section>
  );
}
