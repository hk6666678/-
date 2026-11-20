import { CollegeSelect } from "./CollegeSelect";
import { useEffect, useState } from "react";
type Directory = {
  id: number;
  name?: string;
  mentor_number?: string;
  group_number?: string;
  college: string;
  major: string;
  version: number;
};
type Relation = {
  id: number;
  student_id?: number;
  mentor_id: number;
  group_id: number;
  start_date: string;
  end_date: string | null;
  source_department: string;
  version: number;
};
type Facts = {
  as_of: string;
  student_count: number;
  relation_ids: number[];
  categories: Record<
    string,
    {
      student_count: number;
      distinct_outputs: number;
      participations_per_student?: number | null;
      items: {
        id: number;
        version: number;
        business_key: string;
        title: string;
        participant_count: number;
      }[];
    }
  >;
  graduation: { reason: string; due?: number; completed?: number; destinations?: Record<string, number> };
  delay: { reason: string; late?: number; on_time?: number; unknown?: number };
  basis: string;
  effectiveness?: {
    rate?: number | null;
    acceleration?: number | null;
    stability?: number | null;
    scored: number;
    students: number;
    cohorts: number;
    annual_counts: Record<string, number>;
    benchmark: Record<string, { mean: number | null; count: number; rank?: number }>;
    matched_benchmark?: {
      reason?: string;
      profile?: { direction: string; title: string; effective_on: string };
      peer_count?: number;
      current?: { outputs: number | null; graduation: number | null; delay: number | null; due: number; verified: number };
      peers?: Record<string, { count: number; mean: number | null }>;
    };
  };
};
const labels: Record<string, string> = {
  research_papers: "科研论文",
  patents: "专利",
  awards: "获奖项目",
  conferences: "会议",
};
function GroupGraph({
  mentors,
  groups,
  relations,
  students,
}: {
  mentors: Directory[];
  groups: Directory[];
  relations: Relation[];
  students: { id: number; label: string }[];
}) {
  const active = relations.filter((r) => !r.end_date);
  const studentLabel = (id?: number) =>
    id == null
      ? "未知学生"
      : students.find((s) => s.id === id)?.label ?? `学生 ${id}`;
  const mentorLabel = (id: number) =>
    mentors.find((m) => m.id === id)?.name ?? `导师 ${id}`;
  const groupLabel = (id: number) =>
    groups.find((g) => g.id === id)?.name ?? `课题组 ${id}`;
  const collegeOf = (r: Relation) =>
    groups.find((g) => g.id === r.group_id)?.college ||
    mentors.find((m) => m.id === r.mentor_id)?.college ||
    "学院缺失";
  type MentorMap = Map<number, Set<number>>;
  type GroupMap = Map<number, MentorMap>;
  const tree = new Map<string, GroupMap>();
  for (const r of active) {
    const college = collegeOf(r);
    const byGroup = tree.get(college) ?? new Map<number, MentorMap>();
    tree.set(college, byGroup);
    const byMentor = byGroup.get(r.group_id) ?? new Map<number, Set<number>>();
    byGroup.set(r.group_id, byMentor);
    const studentIds = byMentor.get(r.mentor_id) ?? new Set<number>();
    byMentor.set(r.mentor_id, studentIds);
    if (r.student_id != null) studentIds.add(r.student_id);
  }
  const leafWidth = 94,
    rowGap = 80,
    left = 16,
    yCollege = 26,
    yGroup = yCollege + rowGap,
    yMentor = yGroup + rowGap,
    yStudent = yMentor + rowGap;
  const nodes: { x: number; y: number; label: string; kind: string }[] = [];
  const links: { x1: number; y1: number; x2: number; y2: number }[] = [];
  let cursor = left;
  for (const [college, byGroup] of tree) {
    const groupCenters: number[] = [];
    for (const [groupId, byMentor] of byGroup) {
      const mentorCenters: number[] = [];
      for (const [mentorId, studentIds] of byMentor) {
        const ids = [...studentIds];
        const shown = ids.slice(0, 8);
        const centers: number[] = [];
        if (!ids.length) {
          const x = cursor + leafWidth / 2;
          nodes.push({ x, y: yStudent, label: "暂无学生", kind: "student" });
          centers.push(x);
          cursor += leafWidth;
        }
        for (const id of shown) {
          const x = cursor + leafWidth / 2;
          nodes.push({
            x,
            y: yStudent,
            label: studentLabel(id),
            kind: "student",
          });
          centers.push(x);
          cursor += leafWidth;
        }
        if (ids.length > shown.length) {
          const x = cursor + leafWidth / 2;
          nodes.push({
            x,
            y: yStudent,
            label: `…共${ids.length}人`,
            kind: "student",
          });
          centers.push(x);
          cursor += leafWidth;
        }
        const mx = (centers[0] + centers[centers.length - 1]) / 2;
        nodes.push({
          x: mx,
          y: yMentor,
          label: mentorLabel(mentorId),
          kind: "mentor",
        });
        mentorCenters.push(mx);
        for (const sx of centers)
          links.push({ x1: mx, y1: yMentor + 13, x2: sx, y2: yStudent - 13 });
      }
      const gx =
        (mentorCenters[0] + mentorCenters[mentorCenters.length - 1]) / 2;
      nodes.push({
        x: gx,
        y: yGroup,
        label: groupLabel(groupId),
        kind: "group",
      });
      groupCenters.push(gx);
      for (const mx of mentorCenters)
        links.push({ x1: gx, y1: yGroup + 13, x2: mx, y2: yMentor - 13 });
    }
    const cx = (groupCenters[0] + groupCenters[groupCenters.length - 1]) / 2;
    nodes.push({ x: cx, y: yCollege, label: college, kind: "college" });
    for (const gx of groupCenters)
      links.push({ x1: cx, y1: yCollege + 13, x2: gx, y2: yGroup - 13 });
  }
  const width = Math.max(cursor + left, 320),
    height = yStudent + 46;
  const colors: Record<string, string> = {
    college: "#20584d",
    group: "#2563eb",
    mentor: "#7c3aed",
    student: "#475569",
  };
  const short = (s: string) => (s.length > 9 ? `${s.slice(0, 8)}…` : s);
  return (
    <div className="graph-wrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role="img"
        aria-label="课题组归属图谱"
        className="group-graph"
      >
        {links.map((l, i) => (
          <line
            key={i}
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke="#cdddce"
          />
        ))}
        {nodes.map((n, i) => (
          <g key={i}>
            <rect
              x={n.x - 43}
              y={n.y - 13}
              width={86}
              height={26}
              rx={6}
              fill={n.kind === "student" ? "#f2f7f5" : "#ffffff"}
              stroke={colors[n.kind]}
            />
            <text
              x={n.x}
              y={n.y + 4}
              textAnchor="middle"
              fontSize={n.kind === "student" ? 10 : 11}
              fill={colors[n.kind]}
            >
              {short(n.label)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
export function MentorGroupPanel({ csrf }: { csrf: string }) {
  const [mentors, setMentors] = useState<Directory[]>([]),
    [groups, setGroups] = useState<Directory[]>([]),
    [relations, setRelations] = useState<Relation[]>([]);
  const [students, setStudents] = useState<{ id: number; label: string }[]>([]);
  const [kind, setKind] = useState("mentors"),
    [edit, setEdit] = useState<Directory | null>(null),
    [relationEdit, setRelationEdit] = useState<Relation | null>(null),
    [history, setHistory] = useState<
      { version: number; data: Relation; reason: string; created_at: string }[]
    >([]);
  const [factsSubject, setFactsSubject] = useState("");
  const [facts, setFacts] = useState<Facts | null>(null),
    [drill, setDrill] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{
    id: number;
    row_count: number;
    source_department: string;
  } | null>(null);
  async function api<T>(
    url: string,
    method = "GET",
    body?: unknown,
  ): Promise<T> {
    const r = await fetch(`/api/mentor-groups/${url}`, {
      method,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok)
      throw new Error(
        typeof d.detail === "string" ? d.detail : "请检查输入日期与必要字段",
      );
    return d;
  }
  async function load() {
    const [m, g, r, s] = await Promise.all([
      api<Directory[]>("directory/mentors"),
      api<Directory[]>("directory/groups"),
      api<{ items: Relation[] }>("relations"),
      api<{ id: number; label: string }[]>("students"),
    ]);
    setMentors(m);
    setGroups(g);
    setRelations(r.items);
    setStudents(s);
  }
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(String(e));
      setFacts(null);
      setHistory([]);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void act(load);
  }, []);
  async function saveDirectory(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await act(async () => {
      await api(
        `directory/${kind}${edit ? `/${edit.id}` : ""}`,
        edit ? "PUT" : "POST",
        {
          number: f.get("number"),
          name: f.get("name"),
          college: f.get("college"),
          major: f.get("major"),
          ...(edit
            ? { expected_version: edit.version, reason: f.get("reason") }
            : {}),
        },
      );
      setEdit(null);
      await load();
      setNotice("目录已保存");
    });
  }
  async function saveRelation(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await act(async () => {
      await api(
        `relations${relationEdit ? `/${relationEdit.id}` : ""}`,
        relationEdit ? "PUT" : "POST",
        {
          student_id: Number(f.get("student_id")),
          mentor_id: Number(f.get("mentor_id")),
          group_id: Number(f.get("group_id")),
          start_date: f.get("start_date"),
          end_date: f.get("end_date") || null,
          source_department: f.get("source_department"),
          reason: f.get("reason"),
          ...(relationEdit ? { expected_version: relationEdit.version } : {}),
        },
      );
      setRelationEdit(null);
      setHistory([]);
      setFacts(null);
      await load();
      setNotice("关系已保存并保留版本历史");
    });
  }
  async function importExcel(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const target = f.get("kind");
    f.delete("kind");
    await act(async () => {
      const r = await fetch(`/api/mentor-groups/import/${target}`, {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: f,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail);
      await load();
      setPreview(d);
      setNotice(
        `预览 ${d.row_count} 行；来源：${d.source_department}；尚未写入业务目录与关系`,
      );
    });
  }
  return (
    <section aria-label="导师与课题组">
      <h2>导师与课题组</h2>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <button
        className="secondary"
        disabled={busy}
        onClick={() =>
          void act(async () => {
            setFacts(null);
            setHistory([]);
            await load();
          })
        }
      >
        刷新当前授权范围
      </button>
      <h3>查看指导情况</h3>
      <details className="task-details">
        <summary>登记导师对标资料</summary>
        <form onSubmit={(event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const data = new FormData(form);
          void act(async () => {
            await api(`directory/mentors/${data.get("mentor")}/profile`, "POST", {
              direction: data.get("direction"), title: data.get("title"), effective_on: data.get("effective_on"),
            });
            setFacts(null);
            setNotice("导师对标资料已保存，请重新查询关系事实。");
          });
        }}>
          <label>导师<select name="mentor" required>
            <option value="">请选择导师</option>
            {mentors.map((mentor) => <option key={mentor.id} value={mentor.id}>{mentor.name ?? `导师 ${mentor.id}`}</option>)}
          </select></label>
          <label>研究方向<input name="direction" required maxLength={100} /></label>
          <label>职称<input name="title" required maxLength={100} /></label>
          <label>生效日期<input name="effective_on" type="date" required /></label>
          <button disabled={busy}>保存对标资料</button>
        </form>
      </details>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          void act(async () => {
            const subject = String(f.get("subject"));
            const q = new URLSearchParams({ as_of: String(f.get("as_of")) });
            const [kind, id] = String(f.get("subject")).split(":");
            if (id) q.set(kind, id);
            setFacts(await api<Facts>(`facts?${q}`));
            setFactsSubject(!id ? "全部授权关系" : (kind === "mentor_id" ? mentors : groups).find(item => String(item.id) === id)?.name || subject);
            setDrill("");
          });
        }}
      >
        <label>导师或课题组
          <select aria-label="导师或课题组" name="subject">
            <option value="">全部授权关系</option>
            <optgroup label="导师">
              {mentors.map((m) => <option key={m.id} value={`mentor_id:${m.id}`}>{m.name ?? `导师 ${m.id}`}</option>)}
            </optgroup>
            <optgroup label="课题组">
              {groups.map((g) => <option key={g.id} value={`group_id:${g.id}`}>{g.name ?? `课题组 ${g.id}`}</option>)}
            </optgroup>
          </select>
        </label>
        <label>
          关系统计日期
          <input name="as_of" type="date" defaultValue={new Date().toLocaleDateString("sv-SE")} required />
        </label>
        <button disabled={busy}>查询关系事实</button>
      </form>
      {facts && (
        <div aria-label="关系事实结果">
          <h3>{factsSubject}的指导情况</h3>
          <p className="mentor-fact-summary">
            截至 {facts.as_of} · 去重学生数：{facts.student_count} ·
            有效指导关系：{facts.relation_ids.length}
          </p>
          <h4>导师与课题组效能</h4>
          {facts.effectiveness?.annual_counts ? (
            <>
              <p>评分覆盖 {facts.effectiveness.scored}/{facts.effectiveness.students} 人，涉及 {facts.effectiveness.cohorts} 届。按方案 85 分口径统计模拟评价，混用规则版本时暂停分数比较。</p>
              <details className="reading-note"><summary>近三年成果与统计范围</summary><p>前三个完整年度的授权可见成果数 · {Object.entries(facts.effectiveness.annual_counts).map(([year, count]) => `${year} 年 ${count} 项`).join(" · ")}。仅计可确认发生于指导关系期间的成果。</p></details>
              <table>
                <thead><tr><th>指标</th><th>当前值</th><th>同学院同类单位均值</th><th>可比单位排名</th></tr></thead>
                <tbody>
                  {(["rate", "acceleration", "stability"] as const).map((key) => {
                    const value = facts.effectiveness?.[key];
                    const peer = facts.effectiveness?.benchmark[key];
                    const unit = key === "rate" ? "%" : "";
                    return <tr key={key}>
                      <td>{{rate: "模拟拔尖产出率", acceleration: "成果增量变化", stability: "培养稳定性（各届平均分方差）"}[key]}</td>
                      <td>{value == null ? "条件不足" : value.toFixed(2) + unit}</td>
                      <td>{peer?.mean == null ? "暂无可比单位" : `${peer.mean.toFixed(2)}${unit}（${peer.count} 个）`}</td>
                      <td>{peer?.rank == null || value == null || peer.mean == null ? "—" : `第 ${peer.rank} / ${peer.count + 1} · ${value === peer.mean ? "等于" : value > peer.mean ? "高于" : "低于"}均值`}</td>
                    </tr>;
                  })}
                </tbody>
              </table>
              <p>仅在有可比数据时排名。同值并列，跨届均分方差越小排名越靠前。</p>
            </>
          ) : <p>请选择一名导师或一个课题组，并确认所选日期有授权可见的有效指导关系。</p>}
          <p>影响力转化缺少毕业后跟踪数据。</p>
          {facts.effectiveness?.matched_benchmark && (() => {
            const match = facts.effectiveness.matched_benchmark;
            if (!match.profile || !match.current) return <p>同方向同职称对标 · {match.reason}。</p>;
            const format = (value: number | null | undefined, percent: boolean) =>
              value == null ? "数据不足" : `${value.toFixed(2)}${percent ? "%" : ""}`;
            return <details className="task-details">
              <summary>同方向同职称对标</summary>
              <p>{match.profile.direction} · {match.profile.title} · 同学院可比导师 {match.peer_count} 人。</p>
              <p>本导师预计毕业已到期 {match.current.due} 人，其中 {match.current.verified} 人有可核对毕业日期。</p>
              <table>
                <thead><tr><th>指标</th><th>当前导师</th><th>同组导师均值</th><th>有数据的同组导师</th></tr></thead>
                <tbody>{(["outputs", "graduation", "delay"] as const).map((metric) => (
                  <tr key={metric}>
                    <th scope="row">{{ outputs: "人均登记成果", graduation: "已登记毕业比例", delay: "有实际毕业日期者的延期比例" }[metric]}</th>
                    <td>{format(match.current?.[metric], metric !== "outputs")}</td>
                    <td>{format(match.peers?.[metric]?.mean, metric !== "outputs")}</td>
                    <td>{match.peers?.[metric]?.count ?? 0}</td>
                  </tr>
                ))}</tbody>
              </table>
            </details>;
          })()}
          <table>
            <thead>
              <tr>
                <th>成果类别</th>
                <th>参与学生人数</th>
                <th>去重成果数</th>
                <th>人均登记成果</th>
                <th>证据</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(facts.categories).map(([k, v]) => (
                <tr key={k}>
                  <td>{labels[k]}</td>
                  <td>{v.student_count}</td>
                  <td>{v.distinct_outputs}</td>
                  <td>{v.participations_per_student?.toFixed(2) ?? "暂无可比口径"}</td>
                  <td>
                    <button
                      className="mentor-detail-action"
                      aria-label={`${labels[k]}查看明细`}
                      onClick={() => setDrill(k)}
                    >
                      查看明细
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mentor-missing">
            <p>人均登记成果按参与人次除以有效指导学生数计算。共同成果按每位参与学生各计一次，成果权限覆盖不足时不计算。</p>
            {facts.graduation.due ? (
              <>
                <p>已到预计毕业日期 {facts.graduation.due} 人 · 截至查询日已毕业 {facts.graduation.completed} 人。</p>
                <p>按期毕业 {facts.delay.on_time} 人 · 已知延期 {facts.delay.late} 人 · 实际毕业日期待核查 {facts.delay.unknown} 人。按登记日期统计。</p>
                {Object.entries(facts.graduation.destinations ?? {}).map(([destination, count]) => (
                  <p key={destination}>毕业去向 · {destination} {count} 人</p>
                ))}
              </>
            ) : <p>毕业与延期 · {facts.graduation.reason}。</p>}
          </div>
          <p>{facts.basis}</p>
          {drill && (
            <div>
              <h4>{labels[drill]}事实证据</h4>
              <table>
                <thead>
                  <tr>
                    <th>业务编号</th>
                    <th>成果</th>
                    <th>授权参与人数</th>
                    <th>版本</th>
                  </tr>
                </thead>
                <tbody>
                  {facts.categories[drill].items.map((i) => (
                    <tr key={i.id}>
                      <td>{i.business_key}</td>
                      <td>{i.title}</td>
                      <td>{i.participant_count}</td>
                      <td>{i.version}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      <details className="task-details"><summary>业务目录</summary>

      <label>
        目录类型
        <select
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setEdit(null);
          }}
        >
          <option value="mentors">导师目录</option>
          <option value="groups">课题组目录</option>
        </select>
      </label>
      <table>
        <thead>
          <tr>
            <th>编号</th>
            <th>名称</th>
            <th>学院 / 专业</th>
            <th>版本</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {(kind === "mentors" ? mentors : groups).map((row) => (
            <tr key={row.id}>
              <td>{row.mentor_number ?? row.group_number ?? "身份权限限制"}</td>
              <td>{row.name ?? "身份权限限制"}</td>
              <td>
                {row.college} / {row.major}
              </td>
              <td>{row.version}</td>
              <td>
                <button onClick={() => setEdit(row)}>更正目录 {row.id}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form key={`${kind}-${edit?.id ?? "new"}`} onSubmit={saveDirectory}>
        <h4>{edit ? "更正目录" : "新增目录"}</h4>
        <label>
          目录业务编号
          <input
            name="number"
            required
            defaultValue={edit?.mentor_number ?? edit?.group_number ?? ""}
          />
        </label>
        <label>
          目录名称
          <input name="name" required defaultValue={edit?.name} />
        </label>
        <CollegeSelect label="目录学院" name="college" required defaultValue={edit?.college} />
        <label>
          目录专业
          <input name="major" required defaultValue={edit?.major} />
        </label>
        {edit && (
          <label>
            目录更正依据
            <input name="reason" required />
          </label>
        )}
        <button disabled={busy}>保存目录</button>
        {edit && (
          <button type="button" onClick={() => setEdit(null)}>
            取消更正
          </button>
        )}
      </form>
      </details>
      <details className="task-details"><summary>学生关系与历史</summary>

      <table>
        <thead>
          <tr>
            <th>关系</th>
            <th>学生档案</th>
            <th>导师 / 课题组</th>
            <th>有效日期</th>
            <th>来源</th>
            <th>版本与操作</th>
          </tr>
        </thead>
        <tbody>
          {relations.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>
                {students.find((s) => s.id === r.student_id)?.label ??
                  "身份权限限制"}
              </td>
              <td>
                {mentors.find((m) => m.id === r.mentor_id)?.name ??
                  `导师 ${r.mentor_id}`}{" "}
                /{" "}
                {groups.find((g) => g.id === r.group_id)?.name ??
                  `课题组 ${r.group_id}`}
              </td>
              <td>
                {r.start_date} 至 {r.end_date ?? "持续有效"}
              </td>
              <td>{r.source_department}</td>
              <td>
                v{r.version}{" "}
                <button onClick={() => setRelationEdit(r)}>
                  更正关系 {r.id}
                </button>
                <button
                  onClick={() =>
                    void act(async () =>
                      setHistory(
                        (
                          await api<{ items: typeof history }>(
                            `relations/${r.id}/history`,
                          )
                        ).items,
                      ),
                    )
                  }
                >
                  关系历史 {r.id}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form
        key={
          relationEdit
            ? `relation-${relationEdit.id}-${relationEdit.version}`
            : "new-relation"
        }
        onSubmit={saveRelation}
      >
        <h4>{relationEdit ? "更正学生关系" : "新增学生关系"}</h4>
        <label>
          关系学生
          <select
            name="student_id"
            required
            defaultValue={relationEdit?.student_id}
          >
            <option value="">请选择授权学生</option>
            {students.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          业务导师
          <select
            name="mentor_id"
            required
            defaultValue={relationEdit?.mentor_id ?? ""}
          >
            <option value="">请选择</option>
            {mentors.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name ?? `导师 ${m.id}`}
              </option>
            ))}
          </select>
        </label>
        <label>
          业务课题组
          <select
            name="group_id"
            required
            defaultValue={relationEdit?.group_id ?? ""}
          >
            <option value="">请选择</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name ?? `课题组 ${g.id}`}
              </option>
            ))}
          </select>
        </label>
        <label>
          关系开始日期
          <input
            name="start_date"
            type="date"
            required
            defaultValue={relationEdit?.start_date}
          />
        </label>
        <label>
          关系结束日期
          <input
            name="end_date"
            type="date"
            defaultValue={relationEdit?.end_date ?? ""}
          />
        </label>
        <label>
          关系来源部门
          <input
            name="source_department"
            required
            defaultValue={relationEdit?.source_department}
          />
        </label>
        <label>
          关系变更依据
          <input name="reason" required />
        </label>
        <button disabled={busy}>保存学生关系</button>
        {relationEdit && (
          <button type="button" onClick={() => setRelationEdit(null)}>
            取消关系更正
          </button>
        )}
      </form>
      {history.length > 0 && (
        <div>
          <h4>关系版本历史</h4>
          <table>
            <thead>
              <tr>
                <th>版本</th>
                <th>日期范围</th>
                <th>变更依据</th>
                <th>记录时间</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.version}>
                  <td>{h.version}</td>
                  <td>
                    {h.data.start_date} 至 {h.data.end_date ?? "持续有效"}
                  </td>
                  <td>{h.reason}</td>
                  <td>{h.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </details>
      <details className="task-details"><summary>标准 Excel 导入</summary>

      <p>
        先预览再确认写入；任一行无效则整批不写入。重复编号或日期冲突需人工核对，通过更正表单保留历史。
      </p>
      <div className="actions">
        {["mentors", "groups", "relations"].map((k, i) => (
          <a key={k} href={`/api/mentor-groups/templates/${k}`}>
            {["导师目录模板", "课题组模板", "学生关系模板"][i]}
          </a>
        ))}
      </div>
      <form onSubmit={importExcel}>
        <label>
          导入类型
          <select name="kind">
            <option value="mentors">导师目录</option>
            <option value="groups">课题组目录</option>
            <option value="relations">学生关系</option>
          </select>
        </label>
        <label>
          目录关系来源部门
          <input name="source_department" required />
        </label>
        <label>
          目录关系 Excel
          <input type="file" name="file" accept=".xlsx" required />
        </label>
        <button disabled={busy}>预览目录关系导入</button>
      </form>
      {preview && (
        <div aria-label="目录关系导入预览">
          <p>
            可写入 {preview.row_count} 行；来源：{preview.source_department}
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const result = await api<{ items: unknown[] }>(
                  `previews/${preview.id}/confirm`,
                  "POST",
                );
                setPreview(null);
                setFacts(null);
                await load();
                setNotice(`已确认导入 ${result.items.length} 行`);
              })
            }
          >
            确认目录关系导入
          </button>
          <button onClick={() => setPreview(null)}>取消导入</button>
        </div>
      )}
      </details>
      <details className="task-details">
        <summary>课题组归属图谱（学院 → 课题组 → 导师 → 学生）</summary>
        <p className="muted">
          仅绘制当前有效关系（无结束日期）且在当前授权范围内的归属；身份未授权时导师与课题组以编号显示，学生显示研究编号。每名导师最多直接展示
          8 名学生，超出以"…共N人"汇总。
        </p>
        {relations.filter((r) => !r.end_date).length === 0 ? (
          <p>暂无当前有效关系，图谱为空。可先在上方维护导师课题组关系。</p>
        ) : (
          <GroupGraph
            mentors={mentors}
            groups={groups}
            relations={relations}
            students={students}
          />
        )}
        <p className="muted">
          未入图目录：导师{" "}
          {
            mentors.filter(
              (m) => !relations.some((r) => !r.end_date && r.mentor_id === m.id),
            ).length
          }{" "}
          位、课题组{" "}
          {
            groups.filter(
              (g) => !relations.some((r) => !r.end_date && r.group_id === g.id),
            ).length
          }{" "}
          个（无当前有效关系，不在图中）。
        </p>
      </details>
    </section>
  );
}
