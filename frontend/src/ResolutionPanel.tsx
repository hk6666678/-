import { useState } from "react";
type Revision = {
  version: number;
  data: Record<string, string>;
  state: string;
  error: string;
  evidence: string;
  actor_id: number;
  created_at: number;
  confirmed_at: number | null;
};
type Row = {
  id: number;
  row_number: number;
  state: string;
  error: string;
  original: Record<string, string>;
  data: Record<string, string>;
  revisions: Revision[];
};
type Batch = { id: number; category: string; rows: Row[] };
export function ResolutionPanel({ csrf }: { csrf: string }) {
  const [batchId, setBatchId] = useState(""),
    [batch, setBatch] = useState<Batch | null>(null),
    [selected, setSelected] = useState<Row | null>(null),
    [values, setValues] = useState<Record<string, string>>({}),
    [evidence, setEvidence] = useState(""),
    [error, setError] = useState("");
  async function call(url: string, body?: unknown) {
    setError("");
    try {
      const response = await fetch(url, {
        method: body ? "POST" : "GET",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: body ? JSON.stringify(body) : undefined,
      });
      const result = await response.json();
      if (!response.ok) throw Error(result.detail);
      setBatch(result);
      if (selected) {
        const row = result.rows.find((r: Row) => r.id === selected.id);
        setSelected(row);
      }
    } catch (e) {
      setError(String(e));
    }
  }
  function choose(row: Row) {
    setSelected(row);
    setValues({ ...row.data });
    setEvidence("");
  }
  const latest = selected?.revisions.at(-1);
  return (
    <section>
      <h2>在线纠错与身份确认</h2>
      <p>
        选择导入批次，保留原始行，填写修正值和人工核实依据，校验后再次确认。正式记录更正另行处理。
      </p>
      <label>
        待处理批次编号
        <input value={batchId} onChange={(e) => setBatchId(e.target.value)} />
      </label>
      <button onClick={() => void call(`/api/resolutions/${batchId}`)}>
        查看待处理记录
      </button>
      {error && <p role="alert">{error}</p>}
      {batch && (
        <>
          <p>类别：{batch.category}</p>
          <a href={`/api/resolutions/${batch.id}/errors.xlsx`}>
            下载授权范围错误报告
          </a>
          <ul>
            {batch.rows.map((row) => (
              <li key={row.id}>
                <button onClick={() => choose(row)}>
                  第{row.row_number}行 · {row.state} {row.error}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {selected && (
        <>
          <h3>原始行（只读）</h3>
          <pre>{JSON.stringify(selected.original, null, 2)}</pre>
          <h3>修正值</h3>
          {Object.entries(values).map(([key, value]) => (
            <label key={key}>
              {key}
              <input
                value={value}
                onChange={(e) =>
                  setValues({ ...values, [key]: e.target.value })
                }
              />
            </label>
          ))}
          <label>
            人工核实依据
            <textarea
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
            />
          </label>
          <button
            onClick={() =>
              void call(`/api/resolutions/rows/${selected.id}/validate`, {
                data: Object.fromEntries(
                  Object.entries(values).filter(
                    ([key, value]) => value !== selected.data[key],
                  ),
                ),
                evidence,
                version: latest?.version ?? 0,
              })
            }
          >
            保存并重新校验
          </button>
          {latest && (
            <>
              <p>
                校验版本{latest.version}：{latest.state} {latest.error}
              </p>
              <pre>{JSON.stringify(latest.data, null, 2)}</pre>
              <p>
                处理人{latest.actor_id}，时间
                {new Date(latest.created_at * 1000).toLocaleString()}，依据：
                {latest.evidence}
              </p>
              <button
                disabled={
                  !!latest.confirmed_at ||
                  !["ready", "pending"].includes(latest.state)
                }
                onClick={() =>
                  void call(`/api/resolutions/rows/${selected.id}/confirm`, {
                    version: latest.version,
                  })
                }
              >
                再次确认此修复行入库
              </button>
            </>
          )}
        </>
      )}
    </section>
  );
}
