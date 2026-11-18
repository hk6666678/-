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
};

export function EvaluationDashboard({ refresh, openSnapshot }: {
  refresh: number;
  openSnapshot: (id: number) => void;
}) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [rule, setRule] = useState("");
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError(false);
    void fetch("/api/evaluation-snapshots/dashboard", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(({ items }) => setRows(items))
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [refresh]);
  const rules = new Map<number, string>();
  for (const row of rows ?? []) {
    rules.set(row.rule_id, `${row.college} · ${row.major} · 规则 ${row.rule_id} / v${row.rule_version}`);
  }
  const selected = rules.has(Number(rule)) ? Number(rule) : rules.keys().next().value;
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
          <div className="table-wrap">
            <table>
              <thead><tr><th>排名</th><th>研究编号</th><th>模拟总分</th><th>评分时间</th><th>操作</th></tr></thead>
              <tbody>{ranked.map((row, i) => {
                if (i === 0 || ranked[i - 1].total !== row.total) rank = i + 1;
                return (
                  <tr key={row.id}>
                    <td>{row.total === null ? "—" : rank}</td>
                    <td>{row.research_id}</td>
                    <td>{!row.current ? "数据已变更或规则已停用" : row.total === null ? "数据不完整" : row.total.toFixed(2)}</td>
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
