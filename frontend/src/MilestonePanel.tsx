import { EvidenceDetails, evidenceValue } from "./EvidenceDetails";
import { CollegeSelect } from "./CollegeSelect";
import { AttachmentPanel } from "./AttachmentPanel";
import { useState } from "react";
type Props = {
  csrf: string;
  fetcher: (
    url: string,
    method?: string,
    body?: unknown,
    csrf?: string,
  ) => Promise<unknown>;
};
type Batch = {
  id: number;
  total: number;
  counts: Record<string, number>;
  rows: {
    id: number;
    row_number: number;
    state: string;
    error: string;
    data: Record<string, unknown>;
  }[];
};
export function MilestonePanel({ csrf, fetcher }: Props) {
  const [category, setCategory] = useState("topic");
  const [college, setCollege] = useState("");
  const [sourceMajor, setSourceMajor] = useState("");
  const [error, setError] = useState(""),
    [department, setDepartment] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [batch, setBatch] = useState<Batch | null>(null),
    [busy, setBusy] = useState(false);
  async function act(action: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function upload() {
    if (!file) return;
    await act(async () => {
      setBatch(null);
      const body = new FormData();
      body.append("file", file);
      body.append("source_department", department);
      body.append("source_college", college);
      body.append("source_major", sourceMajor);
      const response = await fetch(`/api/milestones/${category}/preview`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrf },
        body,
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string" ? result.detail : "导入失败",
        );
      setBatch(result);
    });
  }
  return (
    <>
      <section className="card">
        <h2>选题与中期导入</h2>
        <label>
          培养环节
          <select
            aria-label="培养环节"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setBatch(null);
            }}
          >
            <option value="topic">选题</option>
            <option value="midterm">中期</option>
          </select>
        </label>
        <p>
          先选「选题」或「中期」，用对应模板上传。核对预览后再确认。
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <a href={`/api/templates/milestones/${category}`}>下载环节模板 v1</a>
        <p>
          <a href={`/api/templates/milestones/${category}?sample=true`}>
            下载明确标注的合成样例（含错误行）
          </a>
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void upload();
          }}
        >
          <CollegeSelect label="来源学院" value={college} onChange={setCollege} />
          <label>
            来源专业
            <input
              value={sourceMajor}
              onChange={(e) => setSourceMajor(e.target.value)}
            />
          </label>
          <label>
            来源部门
            <input
              required
              maxLength={100}
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            />
          </label>
          <label>
            选题与中期 Excel
            <input
              required
              type="file"
              accept=".xlsx"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <button disabled={busy}>上传并预览</button>
        </form>
        {batch && (
          <>
            <h3>
              批次 {batch.id} · 共 {batch.total} 行
            </h3>
            <p>
              {Object.entries(batch.counts)
                .map(([state, count]) => `${evidenceValue(state)} ${count} 条`)
                .join(" / ")}
            </p>
            <button
              disabled={busy}
              onClick={() =>
                void act(async () =>
                  setBatch(
                    (await fetcher(
                      `/api/milestone-imports/${batch.id}/confirm`,
                      "POST",
                      undefined,
                      csrf,
                    )) as Batch,
                  ),
                )
              }
            >
              确认导入有效行
            </button>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>原始行</th>
                    <th>状态</th>
                    <th>数据</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.rows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.row_number}</td>
                      <td>{evidenceValue(row.state)}</td>
                      <td><EvidenceDetails data={row.data} /></td>
                      <td>{row.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
      <AttachmentPanel csrf={csrf} />
    </>
  );
}
