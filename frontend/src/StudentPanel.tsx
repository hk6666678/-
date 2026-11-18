import { useCallback, useEffect, useRef, useState } from "react";
import { tongjiMajors } from "./tongjiMajors";
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
type Filters = { majors: string[]; levels: string[] };
type MilestoneItem = { category: string; data: Record<string, string> };
type ArchiveView = Row & {
  student_number?: string;
  milestones?: MilestoneItem[];
};
type AssessmentItem = {
  category: string;
  batch: string;
  scores: Record<string, number>;
  student_no?: string;
};
type Detail = {
  archive: ArchiveView;
  courses: { items: { data: Record<string, string> }[] };
  assessments?: { items: AssessmentItem[] };
  assessmentsNote?: string;
};
type TimelineEvent = {
  sort: string;
  year: string;
  title: string;
  meta: string;
};
const yearOf = (value: string | undefined) =>
  (String(value ?? "").match(/(19|20)\d{2}/) || [""])[0];
function timelineEvents(detail: Detail): TimelineEvent[] {
  const events: TimelineEvent[] = [];
  const data = (detail.archive.data ?? {}) as Record<string, string>;
  if (data["入学年份"])
    events.push({
      sort: `${data["入学年份"]}-0`,
      year: String(data["入学年份"]),
      title: "入学",
      meta: [
        data["培养层次"],
        data["学制"],
        data["入学方式"],
        data["学习形式"],
        data["学位类型"],
        data["学籍状态"],
        data["前置院校"] ? `前置院校：${data["前置院校"]}` : "",
      ]
        .filter(Boolean)
        .join(" · "),
    });
  if (data["学籍异动类型"])
    events.push({
      sort: `${yearOf(data["学籍异动时间"]) || data["入学年份"] || "9999"}-1`,
      year: yearOf(data["学籍异动时间"]) || "异动",
      title: `学籍异动：${data["学籍异动类型"]}`,
      meta: data["学籍异动时间"] || "异动时间缺失",
    });
  const terms: Record<string, number> = {};
  for (const course of detail.courses?.items ?? []) {
    const term = course.data?.["修读学期"] || "学期缺失";
    terms[term] = (terms[term] ?? 0) + 1;
  }
  for (const [term, count] of Object.entries(terms))
    events.push({
      sort: `${yearOf(term) || "9999"}-2-${term}`,
      year: yearOf(term) || "—",
      title: `修读课程 ${count} 门`,
      meta: term,
    });
  for (const milestone of detail.archive.milestones ?? []) {
    const m = milestone.data ?? {};
    events.push({
      sort: `${yearOf(m["实际日期"] || m["考核批次"]) || "9999"}-3-${m["考核批次"] ?? ""}`,
      year: yearOf(m["实际日期"] || m["考核批次"]) || "—",
      title: `${milestone.category === "topic" ? "选题" : "中期"} · ${
        m["考核批次"] || "批次缺失"
      }${m["选题标题"] ? ` · ${m["选题标题"]}` : ""}`,
      meta: [
        m["原始成绩"] ? `成绩 ${m["原始成绩"]}` : "",
        m["完成状态"],
        m["实际日期"],
      ]
        .filter(Boolean)
        .join(" · "),
    });
  }
  if (detail.archive.student_number && detail.assessments) {
    for (const item of detail.assessments.items ?? []) {
      if (item.student_no !== detail.archive.student_number) continue;
      events.push({
        sort: `${yearOf(item.batch) || "9999"}-4-${item.batch}`,
        year: yearOf(item.batch) || "—",
        title: `${
          item.category === "blind_reviews" ? "盲审" : "答辩"
        } · ${item.batch}`,
        meta: Object.entries(item.scores ?? {})
          .map(([key, value]) => `${key} ${value}`)
          .join(" · "),
      });
    }
  }
  return events.sort((a, b) => a.sort.localeCompare(b.sort));
}
const tongjiMajorNames = new Set(tongjiMajors);
export function StudentPanel({ csrf, fetcher }: Props) {
  const [error, setError] = useState(""),
    [department, setDepartment] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [batch, setBatch] = useState<Batch | null>(null),
    [students, setStudents] = useState<Row[]>([]),
    [detail, setDetail] = useState<Detail | null>(null),
    [busy, setBusy] = useState(false),
    [major, setMajor] = useState(""),
    [year, setYear] = useState(""),
    [level, setLevel] = useState(""),
    [mobilityOnly, setMobilityOnly] = useState(false),
    [filters, setFilters] = useState<Filters>({ majors: [], levels: [] });
  const [studentTotal, setStudentTotal] = useState<number>();
  const detailHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (detail) detailHeading.current?.focus(); }, [detail]);
  const currentYear = new Date().getFullYear();
  const recentYears = Array.from({ length: 10 }, (_, index) => currentYear - index);
  const otherMajors = filters.majors.filter((name) => !tongjiMajorNames.has(name));
  const refreshFilters = useCallback(async (showStudents = false) => {
    const result = (await fetcher(`/api/students?include_filters=true&limit=${showStudents ? 50 : 1}`)) as {
      filters: Filters; items: Row[]; total: number;
    };
    setFilters(result.filters);
    if (showStudents) {
      setStudents(result.items);
      setStudentTotal(result.total);
    }
  }, [fetcher]);
  useEffect(() => {
    void refreshFilters(true).catch((err) => setError(String(err)));
  }, [refreshFilters]);
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
        total: number;
      };
      setStudents(result.items);
      setStudentTotal(result.total);
      setDetail(null);
    });
  }
  return (
    <>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      <details className="card">
        <summary>导入学生档案</summary>
        <p>
          标准模板第1行记录类型与版本、第2行为字段名。导入预览不创建正式档案；学号必须以文本保存。
        </p>
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
                void act(async () => {
                  setBatch(
                    (await fetcher(
                      `/api/imports/${batch.id}/confirm`,
                      "POST",
                      undefined,
                      csrf,
                    )) as Batch,
                  );
                  await refreshFilters().catch(() => {});
                })
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
      </details>
      <section className="card">
        <h2>统一学生档案</h2>
        <details className="task-details">
        <summary>筛选学生</summary>
        <div className="account-form">
          <label>
            专业筛选
            <select aria-label="专业筛选" value={major} onChange={(e) => setMajor(e.target.value)}>
              <option value="">全部专业</option>
              <optgroup label="同济大学硕士招生专业">
                {tongjiMajors.map((option) => <option key={option}>{option}</option>)}
              </optgroup>
              {otherMajors.length > 0 && (
                <optgroup label="其他已导入专业">
                  {otherMajors.map((option) => <option key={option}>{option}</option>)}
                </optgroup>
              )}
            </select>
          </label>
          <label>
            入学年份筛选
            <select aria-label="入学年份筛选" value={year} onChange={(e) => setYear(e.target.value)}>
              <option value="">全部年份</option>
              {recentYears.map((option) => <option key={option}>{option}</option>)}
            </select>
          </label>
          <label>
            培养层次筛选
            <select aria-label="培养层次筛选" value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">全部培养层次</option>
              {filters.levels.map((option) => <option key={option}>{option}</option>)}
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input
              style={{ width: "auto" }}
              type="checkbox"
              checked={mobilityOnly}
              onChange={(e) => setMobilityOnly(e.target.checked)}
            />
            仅看有学籍异动记录的学生
          </label>
        </div>
        <button disabled={busy} onClick={() => void load()}>
          查询学生档案
        </button>
        </details>
        {studentTotal !== undefined && (studentTotal > students.length
          ? <p>当前显示前 {students.length} 人，共 {studentTotal} 人。可通过筛选缩小范围。</p>
          : studentTotal === 0 ? <p>当前范围暂无学生档案。</p> : null)}
        <table>
          <thead>
            <tr>
              <th>学生</th>
              <th>学院与专业</th>
              <th>入学与学籍</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {(mobilityOnly
              ? students.filter(
                  (student) =>
                    student.data &&
                    (student.data as Record<string, string>)["学籍异动类型"],
                )
              : students
            ).map((student) => (
              <tr key={student.id}>
                <td>{student.name ? <><strong>{student.name}</strong><br /></> : null}{student.research_id}</td>
                <td>{[student.data["所属学院"], student.data["专业"]].filter(Boolean).join(" · ") || "—"}</td>
                <td>{[student.data["入学年份"], student.data["培养层次"], student.data["学籍状态"]].filter(Boolean).join(" · ") || "—"}</td>
                <td>
                  <button
                    disabled={busy}
                    className="secondary"
                    onClick={() =>
                      void act(async () => {
                        const archive = (await fetcher(
                          `/api/students/${student.id}`,
                        )) as ArchiveView;
                        const courses = (await fetcher(
                          `/api/students/${student.id}/courses`,
                        )) as Detail["courses"];
                        let assessments: Detail["assessments"];
                        let assessmentsNote: string | undefined;
                        try {
                          assessments = (await fetcher(
                            "/api/external-assessments",
                          )) as Detail["assessments"];
                        } catch {
                          assessmentsNote = "盲审与答辩数据当前授权不可用，时间线不包含该段。";
                        }
                        setDetail({
                          archive,
                          courses,
                          assessments,
                          assessmentsNote,
                        });
                      })
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
          <>
            <h3 ref={detailHeading} tabIndex={-1}>培养时间线 · {detail.archive.name || detail.archive.research_id}</h3>
            <p className="muted">
              按年份汇总入学、学籍异动、修读学期、选题、中期、盲审与答辩；缺失字段如实留空。
              {detail.assessmentsNote ||
                (detail.archive.student_number
                  ? ""
                  : "身份未授权时无法把盲审答辩关联到本档案，该段不展示。")}
            </p>
            {timelineEvents(detail).length === 0 ? (
              <p>暂无可展示的时间线事件。</p>
            ) : (
              <ul className="timeline">
                {timelineEvents(detail).map((event, index) => (
                  <li key={`${event.sort}-${index}`}>
                    <span className="timeline-year">{event.year}</span>
                    <div>
                      <strong>{event.title}</strong>
                      {event.meta && <p className="muted">{event.meta}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <details>
              <summary>来源与原始依据（JSON）</summary>
              <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {JSON.stringify(detail, null, 2)}
              </pre>
            </details>
          </>
        )}
      </section>
    </>
  );
}
