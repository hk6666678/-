import { useState } from "react";
type Batch = {
  id: number;
  total: number;
  counts: Record<string, number>;
  rows: {
    id: number;
    row_number: number;
    state: string;
    error: string;
    existing?: unknown;
    data: Record<string, unknown>;
  }[];
};
export function CoursePanel({ csrf }: { csrf: string }) {
  const [batch, setBatch] = useState<Batch | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function call(url: string, body?: FormData) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrf },
        body,
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string" ? result.detail : "请求失败",
        );
      setBatch(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>课程导入与待关联记录</h2>
      <p>
        记录键：学号、课程编号、修读学期、考核次数。空成绩保留为空。缺基础档案时须明确来源学院和专业；身份或范围冲突需人工确认。
      </p>
      <a href="/api/templates/courses">下载课程模板 v1</a>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setBatch(null);
          void call(
            "/api/imports/courses/preview",
            new FormData(e.currentTarget),
          );
        }}
      >
        <label>
          课程来源部门
          <input name="source_department" required maxLength={100} />
        </label>
        <label>
          来源学院
          <input name="college" />
        </label>
        <label>
          来源专业
          <input name="major" />
        </label>
        <label>
          课程 Excel
          <input name="file" type="file" accept=".xlsx" required />
        </label>
        <button disabled={busy}>预览课程</button>
      </form>
      {batch && (
        <>
          <h3>
            课程批次 {batch.id} · 共 {batch.total} 行
          </h3>
          <p>
            {Object.entries(batch.counts)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" / ")}
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void call(`/api/imports/courses/${batch.id}/confirm`)
            }
          >
            确认课程有效及待关联行
          </button>
          <table>
            <thead>
              <tr>
                <th>原始行</th>
                <th>状态</th>
                <th>课程数据</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              {batch.rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.row_number}</td>
                  <td>{row.state}</td>
                  <td>
                    {JSON.stringify(row.data)}
                    {row.existing !== undefined && (
                      <p>当前版本：{JSON.stringify(row.existing)}</p>
                    )}
                  </td>
                  <td>{row.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            disabled={busy}
            onClick={async () => {
              const r = await fetch(`/api/imports/courses/${batch.id}`);
              if (r.ok) setBatch(await r.json());
              else setError("批次不存在或权限已变化");
            }}
          >
            刷新关联状态
          </button>
        </>
      )}
    </section>
  );
}
