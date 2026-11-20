import { useEffect, useState } from "react";

type Row = {
  id: number;
  research_id: string;
  college: string;
  major: string;
  rule_id: number;
  rule_version: number;
  as_of: number;
  total: number | null;
  current: boolean;
  band?: string | null;
};
type Benchmark = { count: number; percentiles: { p50: number; p75: number; p90: number } | null };
type RollingBenchmark = Benchmark & {
  start_year: number; end_year: number; covered_years: number[];
  annual_counts: Record<number, number>; scenario?: string; excluded_incomplete?: number;
};

export function EvaluationDashboard({ refresh, openSnapshot }: {
  refresh: number;
  openSnapshot: (id: number) => void;
}) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [rule, setRule] = useState("");
  const [error, setError] = useState(false);
  const [benchmarks, setBenchmarks] = useState<Record<number, Benchmark>>({});
  const [rolling, setRolling] = useState<{ rule: number; result: RollingBenchmark }>();
  const [rollingError, setRollingError] = useState(false);
  const [rollingBusy, setRollingBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError(false);
    void fetch("/api/evaluation-snapshots/dashboard", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(({ items, benchmarks }) => { setRows(items); setBenchmarks(benchmarks ?? {}); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [refresh]);
  const rules = new Map<number, string>();
  for (const row of rows ?? []) {
    rules.set(row.rule_id, `${row.college} · ${row.major} · 规则 ${row.rule_id} / v${row.rule_version}`);
  }
  const selected = rules.has(Number(rule)) ? Number(rule) : rules.keys().next().value;
  const benchmark = selected === undefined ? undefined : benchmarks[selected];
  const ranked = (rows ?? []).filter((row) => row.rule_id === selected)
    .sort((a, b) => (b.total ?? -1) - (a.total ?? -1) || a.research_id.localeCompare(b.research_id));
  let rank = 0;
  return (
    <section className="card">
      <h3>拔尖人才模拟识别仪表盘</h3>
      <p>每位学生取最新模拟评价快照，在同一规则版本内按总分排序。仅供培养质量研究。</p>
      {error ? <p role="alert">仪表盘加载失败。</p>
        : rows === null ? <p>正在读取</p>
        : rows.length === 0 ? <p>暂无授权可见的模拟快照。请先生成模拟评价。</p>
        : <>
          <label>排序规则版本
            <select value={selected} onChange={(e) => setRule(e.target.value)}>
              {[...rules].map(([id, label]) => <option value={id} key={id}>{label}</option>)}
            </select>
          </label>
          {benchmark && <p>当前同规则有效快照 {benchmark.count} 份
            {benchmark.percentiles
              ? ` · P50 ${benchmark.percentiles.p50} · P75 ${benchmark.percentiles.p75} · P90 ${benchmark.percentiles.p90}`
              : " · 不足 5 份，暂不计算分位"}。</p>}
          {selected !== undefined && <details className="task-details">
            <summary>五年滚动基准</summary>
            <form onSubmit={async (event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              setRolling(undefined);
              setRollingError(false);
              setRollingBusy(true);
              try {
                const params = new URLSearchParams({ rule_id: String(selected), benchmark_year: String(data.get("benchmark_year")) });
                if (data.has("synthetic_history")) params.set("synthetic_history", "true");
                const response = await fetch(`/api/evaluation-snapshots/rolling-benchmark?${params}`);
                if (!response.ok) throw new Error();
                setRolling({ rule: selected, result: await response.json() });
              } catch {
                setRollingError(true);
              } finally {
                setRollingBusy(false);
              }
            }}>
              <label>基准年份<input name="benchmark_year" type="number" min={1905} max={2100} defaultValue={new Date().getFullYear()} required /></label>
              <label><input name="synthetic_history" type="checkbox" />使用多年度合成场景</label>
              <button disabled={rollingBusy}>计算往前五年</button>
            </form>
            <p>按同一规则版本，每名学生取窗口内最后一份快照。过时或缺分的快照不计入。</p>
            {rollingError && <p role="alert">五年滚动基准加载失败。</p>}
            {rolling?.rule === selected && <>
              {rolling.result.scenario && <p>合成历史演示，排除缺分样本 {rolling.result.excluded_incomplete} 人。</p>}
              <p>
              {rolling.result.start_year}–{rolling.result.end_year} 年 · 有效样本 {rolling.result.count} 人 · 有数据年份 {rolling.result.covered_years.join("、") || "无"}
              {rolling.result.percentiles
                ? ` · P50 ${rolling.result.percentiles.p50} · P75 ${rolling.result.percentiles.p75} · P90 ${rolling.result.percentiles.p90}`
                : " · 不足 5 人，暂不计算分位"}
              </p>
              {rolling.result.covered_years.length > 0 && <p>按快照年份计入人数 · {rolling.result.covered_years.map((year) =>
                `${year} 年 ${rolling.result.annual_counts[year]} 人`).join(" · ")}</p>}
            </>}
          </details>}
          <div className="table-wrap">
            <table>
              <thead><tr><th>排名</th><th>研究编号</th><th>模拟总分</th><th>模拟分层</th><th>评分时间</th><th>操作</th></tr></thead>
              <tbody>{ranked.map((row, i) => {
                if (i === 0 || ranked[i - 1].total !== row.total) rank = i + 1;
                return (
                  <tr key={row.id}>
                    <td>{row.total === null ? "—" : rank}</td>
                    <td>{row.research_id}</td>
                    <td>{!row.current ? "数据已变更或规则已停用" : row.total === null ? "数据不完整" : row.total.toFixed(2)}</td>
                    <td>{row.band ?? "—"}</td>
                    <td>{new Date(row.as_of * 1000).toLocaleString()}</td>
                    <td><button className="secondary" onClick={() => openSnapshot(row.id)}>查看快照 #{row.id} 的证据</button></td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        </>}
    </section>
  );
}
