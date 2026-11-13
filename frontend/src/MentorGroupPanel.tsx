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
      items: {
        id: number;
        version: number;
        business_key: string;
        title: string;
        participant_count: number;
      }[];
    }
  >;
  graduation: { reason: string };
  delay: { reason: string };
  basis: string;
};
const labels: Record<string, string> = {
  research_papers: "科研论文",
  patents: "专利",
  awards: "获奖项目",
  conferences: "会议",
};
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
      <p>
        维护业务目录、学生关系与日期历史，按当前授权查看事实。业务导师与登录账号分别管理。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <button
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
      <h3>业务目录</h3>
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
        <label>
          目录学院
          <input name="college" required defaultValue={edit?.college} />
        </label>
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
      <h3>学生关系与历史</h3>
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
      <h3>标准 Excel 导入</h3>
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
      <h3>事实统计与下钻</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          void act(async () => {
            const q = new URLSearchParams({ as_of: String(f.get("as_of")) });
            if (f.get("mentor_id"))
              q.set("mentor_id", String(f.get("mentor_id")));
            if (f.get("group_id")) q.set("group_id", String(f.get("group_id")));
            setFacts(await api<Facts>(`facts?${q}`));
            setDrill("");
          });
        }}
      >
        <label>
          关系统计日期
          <input name="as_of" type="date" required />
        </label>
        <label>
          统计导师
          <select name="mentor_id">
            <option value="">全部授权导师</option>
            {mentors.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name ?? `导师 ${m.id}`}
              </option>
            ))}
          </select>
        </label>
        <label>
          统计课题组
          <select name="group_id">
            <option value="">全部授权课题组</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name ?? `课题组 ${g.id}`}
              </option>
            ))}
          </select>
        </label>
        <button disabled={busy}>查询关系事实</button>
      </form>
      {facts && (
        <div aria-label="关系事实结果">
          <p className="mentor-fact-summary">
            截至 {facts.as_of} · 去重学生数：{facts.student_count} ·
            有效指导关系：{facts.relation_ids.length}
          </p>
          <table>
            <thead>
              <tr>
                <th>成果类别</th>
                <th>参与学生人数</th>
                <th>去重成果数</th>
                <th>证据</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(facts.categories).map(([k, v]) => (
                <tr key={k}>
                  <td>{labels[k]}</td>
                  <td>{v.student_count}</td>
                  <td>{v.distinct_outputs}</td>
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
            <p>毕业：条件缺失，{facts.graduation.reason}。</p>
            <p>延期：条件缺失，{facts.delay.reason}。</p>
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
    </section>
  );
}
