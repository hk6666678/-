import { useEffect, useState } from "react";

type CohortRow = {
  research_id: string;
  college: string;
  major: string;
  entry_year: number;
  outputs: { id: number; title: string; date: string; topic: string; midterm: string }[];
};

export function OutputCohorts({ endpoint }: { endpoint: string }) {
  const [rows, setRows] = useState<CohortRow[] | null>(null);
  const [cohort, setCohort] = useState("");
  const [error, setError] = useState(false);
  const groups = new Map<string, CohortRow[]>();
  for (const row of rows ?? []) {
    const label = `${row.entry_year} · ${row.college} · ${row.major}`;
    const group = groups.get(label) ?? [];
    group.push(row);
    groups.set(label, group);
  }
  const labels = [...groups.keys()].sort().reverse();
  const selected = groups.get(cohort || labels[0]) ?? [];
  selected.sort((a, b) => b.outputs.length - a.outputs.length || a.research_id.localeCompare(b.research_id));
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`/api/${endpoint}/cohort`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(({ items }) => setRows(items))
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [endpoint]);
  let rank = 0;
  return (
    <section>
      <h3>同届成果排名与培养阶段</h3>
      <p>按学院、专业和入学年份比较当前类别的有效成果。共同成果按每位参与者各计一次，同数并列，授权范围内无成果的学生计零。阶段比较采用首次有实际日期的选题或中期记录。</p>
      {error ? <p role="alert">分析加载失败。</p> : rows === null ? <p>正在读取</p>
        : labels.length === 0 ? <p>授权范围内暂无学生。</p> : (
          <>
            <label>入学届别
              <select value={cohort || labels[0]} onChange={(e) => setCohort(e.target.value)}>
                {labels.map((label) => <option key={label}>{label}</option>)}
              </select>
            </label>
            <table>
              <thead><tr><th>排名</th><th>研究编号</th><th>成果数</th><th>成果与培养阶段</th></tr></thead>
              <tbody>
                {selected.map((row, i) => {
                  if (i === 0 || selected[i - 1].outputs.length !== row.outputs.length) rank = i + 1;
                  return (
                    <tr key={row.research_id}>
                      <td>{rank}</td><td>{row.research_id}</td><td>{row.outputs.length}</td>
                      <td>{row.outputs.map((output) => (
                        <div key={output.id}>{output.title} · {output.date || "日期缺失"} · 选题 {output.topic} · 中期 {output.midterm}</div>
                      ))}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
    </section>
  );
}
