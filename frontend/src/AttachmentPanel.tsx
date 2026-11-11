import { useState } from "react";
type RecordItem = {
  id: number;
  category: string;
  student_id: number | null;
  data: Record<string, unknown>;
};
type Version = {
  id: number;
  version: number;
  original_filename: string;
  sha256?: string;
};
export function AttachmentPanel({ csrf }: { csrf: string }) {
  const [records, setRecords] = useState<RecordItem[]>([]),
    [selected, setSelected] = useState<RecordItem | null>(null),
    [versions, setVersions] = useState<Version[]>([]),
    [file, setFile] = useState<File | null>(null),
    [coverage, setCoverage] = useState(""),
    [error, setError] = useState(""),
    [preview, setPreview] = useState("");
  async function request(url: string, init?: RequestInit) {
    const response = await fetch(url, init);
    if (!response.ok) {
      const result = await response.json();
      throw new Error(
        typeof result.detail === "string" ? result.detail : "操作失败",
      );
    }
    return response;
  }
  async function load(record: RecordItem) {
    setError("");
    setPreview("");
    setSelected(record);
    setCoverage(record.student_id ? String(record.student_id) : "");
    setVersions([]);
    try {
      setVersions(
        (
          await (
            await request(`/api/milestones/${record.id}/attachments`)
          ).json()
        ).items,
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="card">
      <h2>选题与中期正文附件</h2>
      <p>
        后补 PDF、DOCX；每次上传保留独立版本。请核对文件涉及的全体学生
        ID；待关联记录须先核对身份。预览为文字，不执行文档内容。
      </p>
      {error && <p role="alert">{error}</p>}
      <button
        onClick={() =>
          void (async () => {
            try {
              setRecords(
                (await (await request("/api/milestones?limit=200")).json())
                  .items,
              );
            } catch (e) {
              setError((e as Error).message);
            }
          })()
        }
      >
        加载环节记录
      </button>
      <ul>
        {records.map((record) => (
          <li key={record.id}>
            <button onClick={() => void load(record)}>
              记录 {record.id} · {record.category === "topic" ? "选题" : "中期"}{" "}
              · {String(record.data["学号"] || "身份已脱敏")} ·{" "}
              {String(record.data["考核批次"] || "")}{" "}
              {record.student_id === null ? "（待关联）" : ""}
            </button>
          </li>
        ))}
      </ul>
      {selected && (
        <>
          <h3>记录 {selected.id} 的附件历史</h3>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void (async () => {
                setError("");
                try {
                  if (!file) return;
                  const body = new FormData();
                  body.append("file", file);
                  body.append(
                    "expected_version",
                    String(versions[0]?.version || 0),
                  );
                  body.append(
                    "covered_student_ids",
                    JSON.stringify(
                      coverage.split(",").map((s) => Number(s.trim())),
                    ),
                  );
                  await request(`/api/milestones/${selected.id}/attachments`, {
                    method: "POST",
                    headers: { "X-CSRF-Token": csrf },
                    body,
                  });
                  await load(selected);
                } catch (e) {
                  setError((e as Error).message);
                }
              })();
            }}
          >
            <label>
              正文文件
              <input
                type="file"
                required
                accept=".pdf,.docx"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <label>
              文件涉及的全体学生 ID（逗号分隔）
              <input
                required
                value={coverage}
                onChange={(e) => setCoverage(e.target.value)}
              />
            </label>
            <button disabled={selected.student_id === null}>上传新版本</button>
          </form>
          <ul>
            {versions.map((version) => (
              <li key={version.id}>
                版本 {version.version} · {version.original_filename}{" "}
                <a href={`/api/attachments/${version.id}/download`}>下载</a>{" "}
                <button
                  onClick={() =>
                    void (async () => {
                      try {
                        setPreview(
                          await (
                            await request(
                              `/api/attachments/${version.id}/preview`,
                            )
                          ).text(),
                        );
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    })()
                  }
                >
                  预览文字
                </button>
              </li>
            ))}
          </ul>
          <pre>{preview}</pre>
        </>
      )}
    </section>
  );
}
