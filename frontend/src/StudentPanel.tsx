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
type Row = {
  id: number;
  research_id: string;
  name?: string;
  data: Record<string, unknown>;
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
export function StudentPanel({ csrf, fetcher }: Props) {
  const [error, setError] = useState(""),
    [department, setDepartment] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [batch, setBatch] = useState<Batch | null>(null),
    [students, setStudents] = useState<Row[]>([]),
    [detail, setDetail] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [major, setMajor] = useState(""),
    [year, setYear] = useState(""),
    [level, setLevel] = useState("");
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
      const response = await fetch("/api/imports/basic/preview", {
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
  async function load() {
    await act(async () => {
      const query = new URLSearchParams();
      if (major) query.set("major", major);
      if (year) query.set("entry_year", year);
      if (level) query.set("level", level);
      const result = (await fetcher("/api/students?" + query)) as {
        items: Row[];
      };
      setStudents(result.items);
      setDetail(null);
    });
  }
  return (
    <>
      <section className="card">
        <h2>基础信息导入</h2>
        <p>
          标准模板第1行记录类型与版本、第2行为字段名。导入预览不创建正式档案；学号必须以文本保存。
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <a href="/api/templates/basic">下载基础信息模板 v1</a>
        <p>
          <a href="/api/templates/basic?sample=true">
            下载明确标注的合成样例（含错误行）
          </a>
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void upload();
          }}
        >
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
            基础信息 Excel
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
                .map(([state, count]) => `${state}: ${count}`)
                .join(" / ")}
            </p>
            <button
              disabled={busy}
              onClick={() =>
                void act(async () =>
                  setBatch(
                    (await fetcher(
                      `/api/imports/${batch.id}/confirm`,
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
                      <td>{row.state}</td>
                      <td>{JSON.stringify(row.data)}</td>
                      <td>{row.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
      <section className="card">
        <h2>统一学生档案</h2>
        <div className="account-form">
          <label>
            专业筛选
            <input value={major} onChange={(e) => setMajor(e.target.value)} />
          </label>
          <label>
            入学年份筛选
            <input
              type="number"
              value={year}
              onChange={(e) => setYear(e.target.value)}
            />
          </label>
          <label>
            培养层次筛选
            <input value={level} onChange={(e) => setLevel(e.target.value)} />
          </label>
        </div>
        <button disabled={busy} onClick={() => void load()}>
          查询学生档案
        </button>
        <table>
          <thead>
            <tr>
              <th>研究编号</th>
              <th>基础资料</th>
              <th>追溯</th>
            </tr>
          </thead>
          <tbody>
            {students.map((student) => (
              <tr key={student.id}>
                <td>{student.research_id}</td>
                <td>{JSON.stringify(student.data)}</td>
                <td>
                  <button
                    disabled={busy}
                    className="secondary"
                    onClick={() =>
                      void act(async () =>
                        setDetail(await fetcher(`/api/students/${student.id}`)),
                      )
                    }
                  >
                    查看来源
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {detail !== null && (
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(detail, null, 2)}
          </pre>
        )}
      </section>
    </>
  );
}
