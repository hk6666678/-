import { useState, useRef } from "react";
type Grant = {
  category: string;
  operation: string;
  college: string;
  major: string;
};
type Props = {
  admin: boolean;
  csrf: string;
  users: { id: number; username: string }[];
  fetcher: (
    url: string,
    method?: string,
    body?: unknown,
    csrf?: string,
  ) => Promise<unknown>;
};
const categories: Record<string, string> = {
  basic: "基础信息",
  courses: "课程成绩",
  topic: "选题",
  midterm: "中期",
  papers: "论文",
};
const operations: Record<string, string> = {
  maintain: "维护",
  view: "查看",
  analyze: "分析",
  identity: "身份展示",
  export: "导出",
  download: "原始下载",
  void: "作废",
  pass_rules: "通过规则",
  labels: "样本标签",
  candidate_rules: "候选规则启用",
  review: "人工复核",
};
export function AccessPanel({ admin, csrf, users, fetcher }: Props) {
  const [bindings, setBindings] = useState("");
  const loadSequence = useRef(0);
  const [target, setTarget] = useState(""),
    [version, setVersion] = useState(0),
    [grants, setGrants] = useState<Grant[]>([]),
    [category, setCategory] = useState("basic"),
    [operation, setOperation] = useState("view"),
    [college, setCollege] = useState("示例学院"),
    [major, setMajor] = useState("计算机"),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [samples, setSamples] = useState<Record<string, unknown>[]>([]);
  async function load(id: string) {
    const sequence = ++loadSequence.current;
    setTarget(id);
    setVersion(0);
    setGrants([]);
    setError("");
    setNotice("");
    setBusy(Boolean(id));
    if (!id) return;
    try {
      const data = (await fetcher(`/api/users/${id}/grants`)) as {
        version: number;
        grants: Grant[];
      };
      if (sequence !== loadSequence.current) return;
      setVersion(data.version);
      setGrants(data.grants);
      const bound = (await fetcher(`/api/users/${id}/student_bindings`)) as {
        student_bindings: string[];
      };
      if (sequence !== loadSequence.current) return;
      setBindings(bound.student_bindings.join("\n"));
    } catch (e) {
      if (sequence === loadSequence.current) setError((e as Error).message);
    } finally {
      if (sequence === loadSequence.current) setBusy(false);
    }
  }
  async function save(next: Grant[]) {
    setBusy(true);
    setError("");
    setNotice("");
    setSamples([]);
    try {
      const data = (await fetcher(
        `/api/users/${target}/grants`,
        "PUT",
        {
          expected_version: version,
          request_id: crypto.randomUUID(),
          grants: next,
        },
        csrf,
      )) as { version: number; grants: Grant[] };
      setVersion(data.version);
      setGrants(data.grants);
      setNotice("授权已保存，后续请求立即按新权限处理");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    setSamples([]);
    setError("");
    try {
      setSamples(
        (await fetcher("/api/access-demo/students")) as Record<
          string,
          unknown
        >[],
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <section className="card">
        <h2>授权与脱敏验证</h2>
        <p>
          示例记录均为合成数据，不是正式学生档案。系统管理员也需要单独的业务授权。
        </p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
        {admin && (
          <>
            <label>
              配置账号
              <select
                value={target}
                disabled={busy}
                onChange={(e) => void load(e.target.value)}
              >
                <option value="">请选择账号</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.username}
                  </option>
                ))}
              </select>
            </label>
            {version > 0 && (
              <>
                <label>
                  学生研究编号绑定（每行一个）
                  <textarea
                    value={bindings}
                    disabled={busy}
                    onChange={(e) => setBindings(e.target.value)}
                  />
                </label>
                <p>
                  导师只能访问显式绑定学生与数据授权的交集，兼任角色也受此约束。清空后保存立即撤销全部绑定。
                </p>
                <button
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError("");
                    setNotice("");
                    try {
                      const result = (await fetcher(
                        `/api/users/${target}/student_bindings`,
                        "PUT",
                        {
                          expected_version: version,
                          request_id: crypto.randomUUID(),
                          student_bindings: bindings
                            .split("\n")
                            .map((v) => v.trim())
                            .filter(Boolean),
                        },
                        csrf,
                      )) as { version: number; student_bindings: string[] };
                      setVersion(result.version);
                      setBindings(result.student_bindings.join("\n"));
                      setNotice("学生绑定已保存");
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  保存学生绑定
                </button>
                <form
                  className="account-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void save([
                      ...grants,
                      {
                        category,
                        operation,
                        college: college.trim(),
                        major: major.trim(),
                      },
                    ]);
                  }}
                >
                  <label>
                    数据类别
                    <select
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                    >
                      {Object.entries(categories).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    操作权限
                    <select
                      value={operation}
                      onChange={(e) => setOperation(e.target.value)}
                    >
                      {Object.entries(operations).map(([k, v]) => (
                        <option key={k} value={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    所属学院
                    <input
                      required
                      value={college}
                      onChange={(e) => setCollege(e.target.value)}
                    />
                  </label>
                  <label>
                    专业范围
                    <input
                      value={major}
                      onChange={(e) => setMajor(e.target.value)}
                      placeholder="留空表示该学院全部专业"
                    />
                  </label>
                  <button disabled={busy}>添加授权</button>
                </form>
                <table>
                  <thead>
                    <tr>
                      <th>数据</th>
                      <th>操作</th>
                      <th>范围</th>
                      <th>管理</th>
                    </tr>
                  </thead>
                  <tbody>
                    {grants.map((g, i) => (
                      <tr key={i}>
                        <td>{categories[g.category]}</td>
                        <td>{operations[g.operation]}</td>
                        <td>
                          {g.college} / {g.major || "全部专业"}
                        </td>
                        <td>
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() =>
                              void save(grants.filter((_, n) => n !== i))
                            }
                          >
                            撤销
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </>
        )}
      </section>
      <section className="card">
        <h2>以当前账号验证访问</h2>
        <p>
          三个合成样例分别属于示例学院的计算机、数学，以及其他示例学院。只有
          basic 查看授权才返回对应范围；身份展示需另外授权。
        </p>
        <button disabled={busy} onClick={() => void preview()}>
          刷新合成记录
        </button>
        <table>
          <thead>
            <tr>
              <th>研究编号</th>
              <th>姓名</th>
              <th>学号</th>
              <th>学院 / 专业</th>
            </tr>
          </thead>
          <tbody>
            {samples.map((s) => (
              <tr key={String(s.research_id)}>
                <td>{String(s.research_id)}</td>
                <td>{s.name ? String(s.name) : "已脱敏"}</td>
                <td>
                  {s.student_number ? String(s.student_number) : "已脱敏"}
                </td>
                <td>
                  {String(s.college)} / {String(s.major)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
