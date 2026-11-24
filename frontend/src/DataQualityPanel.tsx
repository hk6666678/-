import { CollegeSelect } from "./CollegeSelect";
import { useEffect, useState } from "react";

type CheckItem = {
  code: string;
  title: string;
  hint: string;
  status: "ok" | "found" | "skipped" | "partial";
  reason: string | null;
  count: number | null;
  items: { research_id: string; detail: string }[];
  truncated: boolean;
  courses?: number | null;
  topic?: number | null;
  midterm?: number | null;
  skipped_categories?: string[];
};
type Result = {
  college: string;
  major: string;
  students: number;
  generated_at: number;
  items: CheckItem[];
  basis: string;
};
type Classification = {
  status: string;
  principle: string;
  levels: { level: string; protection: string; items: { category: string; name: string; note: string }[] }[];
};

const kindNames: Record<string, string> = { courses: "课程", topic: "选题", midterm: "中期" };
const levelBadges: Record<string, string> = { 公开: "公开", 内部: "内部", 敏感: "敏感" };

function outcomeText(item: CheckItem) {
  if (item.status === "skipped") return "未核对";
  if (item.code === "pending_records") {
    return item.status === "ok" ? "没有待关联记录" : item.status === "partial" ? "部分核对" : `发现 ${item.count} 条`;
  }
  return item.status === "ok" ? "未发现差异" : `涉及 ${item.count} 名学生`;
}

function pendingBreakdown(item: CheckItem) {
  return (["courses", "topic", "midterm"] as const)
    .map((kind) => `${kindNames[kind]} ${item.skipped_categories?.includes(kind) ? "未核对" : `${item[kind]} 条`}`)
    .join(" · ");
}

function ConsistencyChecks() {
  const [college, setCollege] = useState("");
  const [major, setMajor] = useState("");
  const [result, setResult] = useState<Result>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function run(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(undefined);
    try {
      const params = new URLSearchParams({ college, major });
      const response = await fetch(`/api/consistency/checks?${params}`);
      const value = await response.json();
      if (!response.ok) {
        throw Error(typeof value.detail === "string" ? value.detail : "核对失败，请稍后重试");
      }
      setResult(value as Result);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }
  const found = result?.items.filter((item) => item.status === "found").length ?? 0;
  return (
    <section className="card" aria-label="数据一致性核对">
      <h2>数据一致性核对</h2>
      <p className="muted">
        交叉比对同一个学生在不同部门登记的数据是否对得上：课程成绩、选题中期、学位论文、指导关系和档案里的日期。
        这里只指出差异，不会改动任何记录。
      </p>
      <form onSubmit={(event) => void run(event)}>
        <CollegeSelect label="核对学院" name="college" required value={college} onChange={setCollege} />
        <label>
          核对专业
          <input name="major" required maxLength={100} value={major} onChange={(e) => setMajor(e.target.value)} />
        </label>
        <button disabled={busy}>{busy ? "正在核对…" : "开始核对"}</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <section aria-label="核对结果">
          <p>
            {result.college}／{result.major} · 共核对 {result.students} 名在册学生 ·{" "}
            {found > 0 ? `有 ${found} 项发现差异` : "各项均未发现差异"} ·{" "}
            {new Date(result.generated_at * 1000).toLocaleString()}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>核对内容</th>
                  <th>结果</th>
                  <th>明细</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((item) => (
                  <tr key={item.code}>
                    <td>
                      {item.title}
                      {item.status === "found" && item.hint && <p className="muted small">{item.hint}</p>}
                    </td>
                    <td>{outcomeText(item)}</td>
                    <td className="evidence-value">
                      {item.status === "skipped" && item.reason}
                      {item.code === "pending_records" && item.status !== "skipped" && pendingBreakdown(item)}
                      {item.status === "found" && item.code !== "pending_records" && (
                        <details>
                          <summary>查看 {item.count} 名学生</summary>
                          <ul>
                            {item.items.map((entry) => (
                              <li key={entry.research_id}>
                                {entry.research_id}：{entry.detail}
                              </li>
                            ))}
                          </ul>
                          {item.truncated && <p className="muted">差异较多，仅列出前 {item.items.length} 名；可缩小核对范围后再次核对。</p>}
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">{result.basis}</p>
        </section>
      )}
    </section>
  );
}

function DataClassification() {
  const [data, setData] = useState<Classification>();
  useEffect(() => {
    void fetch("/api/data-classification")
      .then(async (response) => {
        if (!response.ok) throw new Error();
        return (await response.json()) as Classification;
      })
      .then(setData)
      .catch(() => {});
  }, []);
  if (!data) return null;
  return (
    <details className="card" open>
      <summary>数据分级</summary>
      <p className="muted">{data.principle}</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>分级</th>
              <th>数据</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            {data.levels.map((level) =>
              level.items.map((item, index) => (
                <tr key={`${level.level}-${item.category}-${index}`}>
                  {index === 0 ? (
                    <td rowSpan={level.items.length}>
                      <span className="badge">{levelBadges[level.level] ?? level.level}</span>
                      <p className="muted small">{level.protection}</p>
                    </td>
                  ) : null}
                  <td>{item.name}</td>
                  <td className="evidence-value">{item.note}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
      <p className="muted">这是按方案第四节的分级要求整理的建议映射（{data.status}）。</p>
    </details>
  );
}

export function DataQualityPanel() {
  return (
    <>
      <ConsistencyChecks />
      <DataClassification />
    </>
  );
}
