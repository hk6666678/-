import { CollegeSelect } from "./CollegeSelect";
import { useEffect, useRef, useState } from "react";
import { tongjiMajors } from "./tongjiMajors";

type Section =
  | { status: "ok"; [key: string]: unknown }
  | { status: "missing"; reason: string }
  | { status: "unauthorized"; reason: string };
type OutputItem = {
  record_id: number;
  business_key: string;
  title: string | null;
  version: number;
  year: string | null;
};
type StudentReport = {
  level: "student";
  generated_at: number;
  student: {
    id: number;
    research_id: string;
    student_number: string | null;
    name: string | null;
    college: string;
    major: string;
    level: string;
    entry_year: number;
    identity_masked: boolean;
  };
  sections: {
    courses: Section & {
      total?: number;
      passed?: number;
      failed?: number;
      unknown?: number;
      pass_ratio?: number | null;
      evidence?: unknown[];
    };
    milestones: { topic: Section; midterm: Section };
    research_papers?: Section & { count?: number; items?: OutputItem[] };
    patents?: Section & { count?: number; items?: OutputItem[] };
    awards?: Section & { count?: number; items?: OutputItem[] };
    conferences?: Section & { count?: number; items?: OutputItem[] };
    evaluation: Section & {
      snapshot_id?: number;
      total?: number | null;
      rule_version?: number;
      as_of?: number;
    };
  };
  basis: string;
};
type GroupReport = {
  level: "mentor_group";
  generated_at: number;
  mentor_id: number | null;
  group_id: number | null;
  as_of: string;
  student_count: number;
  relation_ids: number[];
  categories: Record<
    string,
    {
      student_count: number;
      distinct_outputs: number;
      items: { id: number; title: string; year: string | null }[];
    }
  >;
  graduation: { status: string; reason: string };
  delay: { status: string; reason: string };
  basis: string;
};
type CollegeReport = {
  level: "college";
  generated_at: number;
  scope: { college: string; major: string };
  sections: Record<
    string,
    Section & {
      count?: number;
      distinct_outputs?: number;
      personal_participations?: number;
      active_relations?: number;
      pass_ratio?: number | null;
    }
  >;
  basis: string;
};

const categoryNames: Record<string, string> = {
  research_papers: "科研论文",
  patents: "专利",
  awards: "获奖项目",
  conferences: "会议",
};
const tongjiMajorNames = new Set(tongjiMajors);
type DirectoryRow = {
  id: number;
  mentor_number?: string;
  group_number?: string;
  name?: string;
  college: string;
  major: string;
};

function StatusNote({ section }: { section: Section }) {
  if (section.status === "missing") return <p>缺失：{section.reason}，不填零。</p>;
  if (section.status === "unauthorized")
    return <p>{section.reason}。</p>;
  return null;
}

function Bars({ data, unit }: { data: { label: string; value: number }[]; unit: string }) {
  if (!data.length) return <p>暂无图表数据。</p>;
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <svg
      viewBox={`0 0 ${data.length * 64 + 16} 130`}
      width="100%"
      height="130"
      role="img"
      aria-label={`${unit}柱状图`}
      className="report-bars"
    >
      {data.map((d, i) => {
        const h = (d.value / max) * 84;
        return (
          <g key={d.label}>
            <rect
              x={i * 64 + 16}
              y={96 - h}
              width="44"
              height={h}
              fill="#2563eb"
              opacity="0.85"
            >
              <title>{`${d.label}：${d.value}${unit}`}</title>
            </rect>
            <text x={i * 64 + 38} y={92 - h} fontSize="12" textAnchor="middle">
              {d.value}
            </text>
            <text
              x={i * 64 + 38}
              y={112}
              fontSize="11"
              textAnchor="middle"
            >
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function ReportsPanel({ csrf }: { csrf: string }) {
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [studentReport, setStudentReport] = useState<StudentReport>();
  const [groupReport, setGroupReport] = useState<GroupReport>();
  const [collegeReport, setCollegeReport] = useState<CollegeReport>();
  const [students, setStudents] = useState<{ id: number; research_id: string; name?: string; student_number?: string }[]>([]);
  const studentRequest = useRef(0);
  const [studentMajor, setStudentMajor] = useState("");
  const [majorFilters, setMajorFilters] = useState<{ majors: string[]; levels: string[] }>({ majors: [], levels: [] });
  const [mentors, setMentors] = useState<DirectoryRow[]>([]);
  const [groups, setGroups] = useState<DirectoryRow[]>([]);
  const [groupDate, setGroupDate] = useState(new Date().toISOString().slice(0, 10));
  const [college, setCollege] = useState("");
  const [major, setMajor] = useState("");

  async function get(url: string): Promise<Response> {
    const response = await fetch(url);
    if (!response.ok) {
      const value = await response.json().catch(() => ({}));
      throw Error(
        typeof value.detail === "string" ? value.detail : "请求失败，请检查授权与输入",
      );
    }
    return response;
  }
  async function perform(action: () => Promise<void>) {
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(String(e));
    }
  }
  async function download(url: string, filename: string) {
    const response = await fetch(url);
    if (!response.ok) {
      const value = await response.json().catch(() => ({}));
      throw Error(
        typeof value.detail === "string" ? value.detail : "导出失败，请检查导出授权",
      );
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(objectUrl);
    setNotice(`${filename} 已导出`);
  }

  async function fetchStudents(major: string) {
    const requestId = ++studentRequest.current;
    setStudents([]);
    const response = await get(
      `/api/students?limit=200&offset=0&major=${encodeURIComponent(major)}`,
    );
    const data = await response.json();
    if (requestId === studentRequest.current) setStudents(data.items);
  }
  const otherMajors = majorFilters.majors.filter(
    (name) => !tongjiMajorNames.has(name),
  );
  useEffect(() => {
    void fetchStudents("").catch(() => {});
    void (async () => {
      try {
        const filters = await (
          await get("/api/students?include_filters=true&limit=1")
        ).json();
        setMajorFilters(filters.filters);
      } catch {
        /* 过滤器加载失败不阻塞页面 */
      }
      try {
        // 目录接口返回裸数组（无权行已由服务端过滤）
        const mentorRows = await (
          await get("/api/mentor-groups/directory/mentors")
        ).json();
        setMentors(mentorRows);
      } catch {
        /* 目录加载失败不阻塞页面 */
      }
      try {
        const groupRows = await (
          await get("/api/mentor-groups/directory/groups")
        ).json();
        setGroups(groupRows);
      } catch {
        /* 目录加载失败不阻塞页面 */
      }
    })();
  }, []);
  const outputSections = studentReport
    ? (["research_papers", "patents", "awards", "conferences"] as const).map(
        (key) => ({ key, section: studentReport.sections[key] }),
      )
    : [];

  return (
    <section className="reports-panel" aria-label="三级报告">
      <details className="report-guidance"><summary>报告范围与导出细则</summary><p>
        三级报告按读取时当前权限现算：无授权段落仅标注不计数，缺数据标注缺失不填零，每项数值保留记录与版本依据。导出需要相应类别的独立导出授权。
      </p>
      </details>
      {error && <p role="alert">{error}</p>}
      {notice && <p className="notice compact-notice" role="status">{notice}</p>}

      <article className="card">
        <h3>学生发展报告</h3>
        <details className="task-details"><summary>按专业缩小学生列表</summary>
        <label>
          学生列表专业筛选
          <select
            aria-label="学生列表专业筛选"
            value={studentMajor}
            onChange={(e) => {
              setStudentMajor(e.target.value);
              void perform(() => fetchStudents(e.target.value));
            }}
          >
            <option value="">全部专业（超过200人时请选择具体专业）</option>
            <optgroup label="同济大学硕士招生专业">
              {tongjiMajors.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </optgroup>
            {otherMajors.length > 0 && (
              <optgroup label="其他已导入专业">
                {otherMajors.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        </details>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setStudentReport(undefined);
            void perform(async () => {
              const response = await get(`/api/reports/students/${f.get("student_id")}`);
              setStudentReport(await response.json());
            });
          }}
        >
          <label>
            学生研究编号
            <select aria-label="学生研究编号" name="student_id" required defaultValue="">
              <option value="">请选择已读取的授权学生</option>
              {students.map((s) => (
                <option key={s.id} value={s.id}>
                  {[s.name, s.student_number].filter(Boolean).join(" · ") || s.research_id}
                </option>
              ))}
            </select>
          </label>
          <div className="action-row">
          <button disabled={!students.length}>查看学生报告</button>
          {studentReport && (
            <button className="secondary"
              type="button"
              onClick={() =>
                void perform(() =>
                  download(
                    `/api/reports/students/${studentReport.student.id}/export`,
                    `report-student-${studentReport.student.id}.xlsx`,
                  ),
                )
              }
            >
              导出学生报告（需独立导出授权）
            </button>
          )}
          </div>
        </form>
        {studentReport && (
          <div className="report-body">
            <p>
              {studentReport.student.identity_masked
                ? `研究编号 ${studentReport.student.research_id}（身份未授权，姓名学号不显示）`
                : `${studentReport.student.student_number} ${studentReport.student.name}`}{" "}
              · {studentReport.student.college} / {studentReport.student.major} ·{" "}
              {studentReport.student.level} {studentReport.student.entry_year}级
            </p>
            <h4>课程</h4>
            <StatusNote section={studentReport.sections.courses} />
            {studentReport.sections.courses.status === "ok" && (
              <>
                <p>
                  共{studentReport.sections.courses.total}门，通过
                  {studentReport.sections.courses.passed}，不通过
                  {studentReport.sections.courses.failed}，未知
                  {studentReport.sections.courses.unknown}
                  {studentReport.sections.courses.pass_ratio == null
                    ? "；存在未知，不计算通过比例"
                    : `；通过比例 ${(studentReport.sections.courses.pass_ratio ?? 0).toFixed(2)}`}
                </p>
                <details>
                  <summary>课程依据</summary>
                  <pre>{JSON.stringify(studentReport.sections.courses.evidence, null, 2)}</pre>
                </details>
              </>
            )}
            <h4>里程碑</h4>
            {(["topic", "midterm"] as const).map((key) => (
              <div key={key} className="report-subsection">
                <strong>{key === "topic" ? "选题" : "中期"}</strong>
                <StatusNote section={studentReport.sections.milestones[key]} />
                {studentReport.sections.milestones[key].status === "ok" && (
                  <details>
                    <summary>批次依据</summary>
                    <pre>
                      {JSON.stringify(studentReport.sections.milestones[key], null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
            <h4>成果参与（按年度）</h4>
            <div className="report-charts">
              {outputSections.map(({ key, section }) => (
                <div key={key} className="report-subsection">
                  <strong>{categoryNames[key]}</strong>
                  <StatusNote section={section ?? { status: "unauthorized", reason: "当前授权不足，该段未纳入" }} />
                  {section && section.status === "ok" && section.items && (
                    <>
                      <Bars
                        data={Object.entries(
                          section.items.reduce<Record<string, number>>((acc, item) => {
                            const bucket = item.year ?? "年份缺失";
                            acc[bucket] = (acc[bucket] ?? 0) + 1;
                            return acc;
                          }, {}),
                        ).map(([label, value]) => ({ label, value }))}
                        unit="项"
                      />
                      <details>
                        <summary>成果依据（{section.count}项）</summary>
                        <pre>{JSON.stringify(section.items, null, 2)}</pre>
                      </details>
                    </>
                  )}
                </div>
              ))}
            </div>
            <h4>人才评价快照</h4>
            <StatusNote section={studentReport.sections.evaluation} />
            {studentReport.sections.evaluation.status === "ok" && (
              <p>
                最新快照 #{studentReport.sections.evaluation.snapshot_id} ·{" "}
                {studentReport.sections.evaluation.total == null
                  ? "数据不完整，未形成总分"
                  : `${(studentReport.sections.evaluation.total ?? 0).toFixed(2)} / 100`}{" "}
                · 规则 v{studentReport.sections.evaluation.rule_version} ·
                明细见人才指标模拟评价
              </p>
            )}
          </div>
        )}
      </article>

      <details className="card task-details"><summary>导师课题组报告</summary>
        <p>
          按指定日期统计当前有效导师课题组关系下的学生与成果事实；毕业与延期缺少确认口径时标注缺失，不作优劣排名。
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setGroupReport(undefined);
            const query = new URLSearchParams({ as_of: String(f.get("as_of")) });
            const mentor = String(f.get("mentor_id") ?? "");
            const group = String(f.get("group_id") ?? "");
            if (mentor) query.set("mentor_id", mentor);
            if (group) query.set("group_id", group);
            void perform(async () => {
              const response = await get(`/api/reports/mentor-groups?${query}`);
              setGroupReport(await response.json());
            });
          }}
        >
          <label>
            导师（可空，进入本页自动读取目录）
            <select
              name="mentor_id"
              aria-label="导师（可空，进入本页自动读取目录）"
            >
              <option value="">全部授权导师</option>
              {mentors.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name && m.mentor_number
                    ? `${m.name}（${m.mentor_number}）`
                    : m.name || `导师 #${m.id}（${m.college}/${m.major}）`}
                </option>
              ))}
            </select>
          </label>
          <label>
            课题组（可空）
            <select name="group_id" aria-label="课题组（可空）">
              <option value="">全部授权课题组</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name && g.group_number
                    ? `${g.name}（${g.group_number}）`
                    : g.name || `课题组 #${g.id}（${g.college}/${g.major}）`}
                </option>
              ))}
            </select>
          </label>
          <label>
            统计日期
            <input
              name="as_of"
              type="date"
              required
              value={groupDate}
              onChange={(e) => setGroupDate(e.target.value)}
            />
          </label>
          <div className="action-row">
          <button>查看课题组报告</button>
          {groupReport && (
            <button className="secondary"
              type="button"
              onClick={() =>
                void perform(() => {
                  const query = new URLSearchParams({ as_of: groupReport.as_of });
                  if (groupReport.mentor_id) query.set("mentor_id", String(groupReport.mentor_id));
                  if (groupReport.group_id) query.set("group_id", String(groupReport.group_id));
                  return download(
                    `/api/reports/mentor-groups/export?${query}`,
                    `report-group-${groupReport.mentor_id ?? groupReport.group_id ?? "all"}.xlsx`,
                  );
                })
              }
            >
              导出课题组报告（需独立导出授权）
            </button>
          )}
          </div>
        </form>
        {groupReport && (
          <div className="report-body">
            <p>
              统计日期 {groupReport.as_of} · 当前授权范围内学生
              {groupReport.student_count}人 · 关系{groupReport.relation_ids.length}条
            </p>
            <div className="report-charts">
              {Object.entries(groupReport.categories).map(([key, value]) => (
                <div key={key} className="report-subsection">
                  <strong>{categoryNames[key] ?? key}</strong>
                  <p>
                    成果去重{value.distinct_outputs}项，参与学生{value.student_count}人
                  </p>
                  <Bars
                    data={Object.entries(
                      value.items.reduce<Record<string, number>>((acc, item) => {
                        const bucket = item.year ?? "年份缺失";
                        acc[bucket] = (acc[bucket] ?? 0) + 1;
                        return acc;
                      }, {}),
                    ).map(([label, count]) => ({ label, value: count }))}
                    unit="项"
                  />
                  <details>
                    <summary>成果依据</summary>
                    <pre>{JSON.stringify(value.items, null, 2)}</pre>
                  </details>
                </div>
              ))}
            </div>
            <p>毕业：{groupReport.graduation.reason}。</p>
            <p>延期：{groupReport.delay.reason}。</p>
          </div>
        )}
      </details>

      <details className="card task-details"><summary>学院学科报告</summary>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setCollegeReport(undefined);
            void perform(async () => {
              const response = await get(
                `/api/reports/colleges?college=${encodeURIComponent(String(f.get("college")))}&major=${encodeURIComponent(String(f.get("major")))}`,
              );
              setCollegeReport(await response.json());
            });
          }}
        >
          <CollegeSelect label="学院" name="college" required value={college} onChange={setCollege} />
          <label>
            专业
            <input
              name="major"
              required
              value={major}
              onChange={(e) => setMajor(e.target.value)}
            />
          </label>
          <div className="action-row">
          <button>查看学院报告</button>
          {collegeReport && (
            <button className="secondary"
              type="button"
              onClick={() =>
                void perform(() =>
                  download(
                    `/api/reports/colleges/export?college=${encodeURIComponent(collegeReport.scope.college)}&major=${encodeURIComponent(collegeReport.scope.major)}`,
                    "report-college.xlsx",
                  ),
                )
              }
            >
              导出学院报告（需独立导出授权）
            </button>
          )}
          </div>
        </form>
        {collegeReport && (
          <div className="report-body">
            <p>
              {collegeReport.scope.college} / {collegeReport.scope.major}
            </p>
            {Object.entries(collegeReport.sections).map(([key, section]) => (
              <div key={key} className="report-subsection">
                <strong>
                  {
                    {
                      students: "在册学生",
                      courses: "课程",
                      mentor_groups: "导师关系",
                      ...categoryNames,
                    }[key] ?? key
                  }
                </strong>
                <StatusNote section={section} />
                {section.status === "ok" && (
                  <p>
                    {key === "students" && `当前授权可见${section.count}人`}
                    {key === "courses" &&
                      `记录${(section as { records?: number }).records ?? ""}条，通过${section.passed ?? ""}次${
                        section.pass_ratio == null
                          ? "；存在未知，不计算通过比例"
                          : `；通过比例 ${(section.pass_ratio ?? 0).toFixed(2)}`
                      }`}
                    {key === "mentor_groups" &&
                      `当前有效关系${section.active_relations}条`}
                    {categoryNames[key] &&
                      `成果去重${section.distinct_outputs}项，个人参与${section.personal_participations}人次`}
                  </p>
                )}
              </div>
            ))}
            {collegeReport.sections.students.status === "ok" && (
              <Bars
                data={(["research_papers", "patents", "awards", "conferences"] as const)
                  .map((key) => ({
                    label: categoryNames[key],
                    value:
                      collegeReport.sections[key].status === "ok"
                        ? (collegeReport.sections[key].distinct_outputs ?? 0)
                        : 0,
                  }))
                  .filter((d) => d.value > 0)}
                unit="项"
              />
            )}
          </div>
        )}
      </details>
    </section>
  );
}
