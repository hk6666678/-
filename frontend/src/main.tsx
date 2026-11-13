import { ResearchOutputs } from "./ResearchOutputs";
import { AnalysisPanel } from "./AnalysisPanel";
import { RecordPanel } from "./RecordPanel";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { AccessPanel } from "./AccessPanel";
import { AgentPanel } from "./AgentPanel";
import { AuditPanel } from "./AuditPanel";
import { MilestonePanel } from "./MilestonePanel";
import { PaperPanel } from "./PaperPanel";
import { CandidatePanel } from "./CandidatePanel";
import { ComparisonPanel } from "./ComparisonPanel";
import { CoursePanel } from "./CoursePanel";
import { ResolutionPanel } from "./ResolutionPanel";
import { StudentPanel } from "./StudentPanel";
import { ModelPanel } from "./ModelPanel";

type Role = "mentor" | "platform_admin" | "college_data_admin" | "college_analyst" | "school_data_admin" | "school_analyst";
type User = {
  id: number;
  username: string;
  roles: Role[];
  active: boolean;
  version: number;
  business_permissions: string[];
};
type Session = { user: User; csrf_token: string };
const roleNames: Record<Role, string> = {
  platform_admin: "平台管理员",
  school_data_admin: "校级数据管理员",
  school_analyst: "校级分析人员",
  mentor: "导师",
  college_data_admin: "学院数据管理员",
  college_analyst: "学院分析人员",
};
const roles = Object.keys(roleNames) as Role[];
async function request<T>(
  url: string,
  method = "GET",
  body?: unknown,
  csrf?: string,
): Promise<T> {
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = "请求失败，请稍后重试";
    try {
      const error = await response.json();
      message =
        typeof error.detail === "string"
          ? error.detail
          : "请检查输入格式及密码长度";
    } catch {
      /* Non-JSON failures use the default message. */
    }
    if (response.status === 401)
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(message);
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}
function App() {
  const [session, setSession] = useState<Session | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [users, setUsers] = useState<User[]>([]),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [selected, setSelected] = useState<Role[]>(["college_analyst"]);
  const [page, setPage] = useState("overview");
  useEffect(() => {
    const expired = () => {
      setSession(null);
      setUsers([]);
      setPassword("");
      setUsername("");
      setPage("overview");
    };
    window.addEventListener("session-expired", expired);
    request<Session>("/api/me")
      .then(setSession)
      .catch(() => {})
      .finally(() => setLoading(false));
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => {
    if (session?.user.roles.includes("platform_admin")) void refresh();
  }, [session]);
  async function refresh() {
    try {
      setUsers(await request<User[]>("/api/users"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function perform(action: () => Promise<void>) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function login(event: React.FormEvent) {
    event.preventDefault();
    await perform(async () => {
      setSession(
        await request<Session>("/api/login", "POST", { username, password }),
      );
      setPassword("");
      setUsername("");
      setPage("overview");
    });
  }
  async function create(event: React.FormEvent) {
    event.preventDefault();
    await perform(async () => {
      await request(
        "/api/users",
        "POST",
        {
          username,
          password,
          roles: selected,
          request_id: crypto.randomUUID(),
        },
        session?.csrf_token,
      );
      setUsername("");
      setPassword("");
      setNotice("账号已创建");
      await refresh();
    });
  }
  async function update(user: User, nextRoles: Role[], active: boolean) {
    await perform(async () => {
      await request(
        `/api/users/${user.id}`,
        "PATCH",
        {
          roles: nextRoles,
          active,
          expected_version: user.version,
          request_id: crypto.randomUUID(),
        },
        session?.csrf_token,
      );
      setNotice("账号已更新，受影响账号需重新登录");
      await refresh();
    });
  }
  const alert = (
    <>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="notice">
          {notice}
        </div>
      )}
    </>
  );
  if (loading) return <main className="loading">正在加载平台…</main>;
  if (!session)
    return (
      <main className="login-shell">
        <section className="intro">
          <span className="eyebrow">AQP-PGS / 学院试用版</span>
          <h1>
            让培养过程
            <br />
            有迹可循。
          </h1>
          <p>
            数智赋能研究生培养质量研究
            <br />
            统一档案 · 数据追溯 · 可解释分析
          </p>
          <div className="intro-foot">从可信的数据开始，理解每一段成长。</div>
        </section>
        <section className="login-form">
          <span className="logo">
            A<span>Q</span>P
          </span>
          <h2>登录工作平台</h2>
          <p className="muted">使用管理员为您创建的个人账号</p>
          {alert}

          <form onSubmit={login}>
            <label>
              用户名
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                minLength={3}
                maxLength={64}
              />
            </label>
            <label>
              密码
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                maxLength={128}
              />
            </label>
            <button disabled={busy}>{busy ? "正在登录…" : "登录平台 →"}</button>
          </form>
          <p className="muted small">
            首次使用请由本机维护人员初始化管理员账号。
          </p>
        </section>
      </main>
    );
  const admin = session.user.roles.includes("platform_admin");
  return (
    <div className="workspace">
      <aside>
        <div className="brand">
          AQP-PGS<small>研究生培养质量研究</small>
        </div>
        <nav aria-label="主导航">
          {[
            { label: "工作台", items: [["overview", "工作台概览"]] },
            {
              label: "数据管理",
              items: [
                ["students", "基础导入与学生档案"],
                ["courses", "课程导入与待关联"],
                ["milestones", "选题与中期导入"],
                ["maintenance", "数据纠错与维护"],
              ],
            },
            {
              label: "研究分析",
              items: [
                ["analysis", "课程统计与通过规则"],
                ["papers", "论文上传与解析"],
                ["research_outputs", "已发表科研论文"],
                ["patents", "专利"], ["awards", "获奖项目"], ["conferences", "会议"],
                ["agent", "Agent 查询"],
              ],
            },
            {
              label: "系统管理",
              items: [
                ["access", "授权与脱敏验证"],
                ...(admin
                  ? [
                      ["accounts", "个人账号管理"],
                      ["model", "获准模型连接"],
                      ["audit", "审计查询"],
                    ]
                  : []),
              ],
            },
          ].map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map(([key, label]) => (
                <button
                  key={key}
                  className={page === key ? "active" : ""}
                  aria-current={page === key ? "page" : undefined}
                  onClick={() => setPage(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="aside-foot">
          学院试用版 · 0.1
          <br />
          数据驱动，依据可查
        </div>
      </aside>
      <main className="content">
        <header>
          <div>
            <span className="eyebrow">研究生培养质量研究 / 工作平台</span>
            <h1>
              {
                {
                  maintenance: "数据纠错与维护",
                  overview: "欢迎回到工作台",
                  accounts: "个人账号管理",
                  audit: "审计查询",
                  milestones: "选题与中期导入",
                  papers: "论文上传与解析",
                  research_outputs: "已发表科研论文",
                  patents:"专利", awards:"获奖项目", conferences:"会议",
                  agent: "Agent 查询",
                  analysis: "课程统计与通过规则",
                  courses: "课程导入与待关联",
                  students: "基础导入与学生档案",
                  model: "获准模型连接",
                  access: "授权与脱敏验证",
                }[page]
              }
            </h1>
          </div>
          <div className="user-menu">
            <span>{session.user.username}</span>
            <button
              className="secondary"
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  await request(
                    "/api/logout",
                    "POST",
                    undefined,
                    session.csrf_token,
                  );
                  setSession(null);
                  setUsers([]);
                  setPage("overview");
                  setUsername("");
                  setPassword("");
                })
              }
            >
              退出登录
            </button>
          </div>
        </header>
        {alert}
        {page === "maintenance" && (
          <ResolutionPanel csrf={session.csrf_token} />
        )}
        {page === "maintenance" && <RecordPanel csrf={session.csrf_token} />}
        {page === "audit" && admin ? (
          <AuditPanel fetcher={request} />
        ) : page === "milestones" ? (
          <MilestonePanel csrf={session.csrf_token} fetcher={request} />
        ) : ["research_outputs","patents","awards","conferences"].includes(page) ? (<ResearchOutputs key={page} category={page} csrf={session.csrf_token} />) : page === "papers" ? (
          <>
            <PaperPanel csrf={session.csrf_token} />
            <ComparisonPanel csrf={session.csrf_token} />
            <CandidatePanel csrf={session.csrf_token} />
          </>
        ) : page === "agent" ? (
          <AgentPanel csrf={session.csrf_token} />
        ) : page === "analysis" ? (
          <AnalysisPanel csrf={session.csrf_token} />
        ) : page === "courses" ? (
          <CoursePanel csrf={session.csrf_token} />
        ) : page === "students" ? (
          <StudentPanel csrf={session.csrf_token} fetcher={request} />
        ) : page === "model" && admin ? (
          <ModelPanel csrf={session.csrf_token} fetcher={request} />
        ) : page === "access" ? (
          <AccessPanel
            key={session.user.id}
            admin={admin}
            csrf={session.csrf_token}
            users={users}
            fetcher={request}
          />
        ) : page === "overview" || !admin ? (
          <>
            <section className="welcome">
              <span className="eyebrow">统一平台 · 清晰职责</span>
              <h2>您的工作，从这里开始。</h2>
              <p>当前账号：{session.user.username}</p>
              <div className="tags">
                {session.user.roles.map((role) => (
                  <span key={role}>{roleNames[role]}</span>
                ))}
              </div>
            </section>
            <div className="cards">
              <section className="card">
                <h3>个人账号</h3>
                <p>
                  每次操作以个人身份记录，可由平台管理员管理账号状态及角色。
                </p>
                {admin && (
                  <button
                    className="secondary"
                    onClick={() => setPage("accounts")}
                  >
                    管理账号 →
                  </button>
                )}
              </section>
              <section className="card">
                <h3>业务数据授权</h3>
                <p>
                  角色不自动开放学生数据。数据维护、查看、分析和导出需要分别授权。导师还须绑定学生，兼任其他角色也只能访问绑定学生与数据授权的交集；解绑立即生效。
                </p>
                <span className="badge">业务数据权限请在授权验证页面查看</span>
              </section>
            </div>
          </>
        ) : (
          <>
            <section className="card">
              <h2>创建个人账号</h2>
              <p className="muted">
                角色可兼任。密码为 12～128 个字符，创建后交由账号本人保管。
              </p>
              <form className="account-form" onSubmit={create}>
                <label>
                  新账号用户名
                  <input
                    value={username}
                    autoComplete="off"
                    pattern="[A-Za-z0-9_.-]{3,64}"
                    title="3～64位字母、数字、点、下划线或短横线"
                    onChange={(e) => setUsername(e.target.value)}
                    required
                  />
                </label>
                <label>
                  初始密码
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    minLength={12}
                    maxLength={128}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </label>
                <fieldset>
                  <legend>账号角色</legend>
                  {roles.map((role) => (
                    <label className="check" key={role}>
                      <input
                        type="checkbox"
                        checked={selected.includes(role)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, role]
                              : selected.filter((r) => r !== role),
                          )
                        }
                      />
                      {roleNames[role]}
                    </label>
                  ))}
                </fieldset>
                <button disabled={busy || selected.length === 0}>
                  创建账号
                </button>
              </form>
            </section>
            <section className="card">
              <h2>
                账号列表 <span className="muted">{users.length}</span>
              </h2>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>角色（修改后需重新登录）</th>
                      <th>状态</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => (
                      <tr key={user.id}>
                        <td>
                          <strong>{user.username}</strong>
                          {user.id === session.user.id && (
                            <small>当前账号</small>
                          )}
                        </td>
                        <td>
                          {roles.map((role) => (
                            <label className="check" key={role}>
                              <input
                                type="checkbox"
                                aria-label={`${user.username} ${roleNames[role]}`}
                                checked={user.roles.includes(role)}
                                disabled={busy}
                                onChange={(e) =>
                                  void update(
                                    user,
                                    e.target.checked
                                      ? [...user.roles, role]
                                      : user.roles.filter((r) => r !== role),
                                    user.active,
                                  )
                                }
                              />
                              {roleNames[role]}
                            </label>
                          ))}
                        </td>
                        <td>
                          <span
                            className={user.active ? "badge" : "badge disabled"}
                          >
                            {user.active ? "正常" : "已停用"}
                          </span>
                        </td>
                        <td>
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() =>
                              void update(user, user.roles, !user.active)
                            }
                          >
                            {user.active ? "停用" : "启用"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);

