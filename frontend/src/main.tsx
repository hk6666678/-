import { EvaluationPanel } from "./EvaluationPanel";
import { ReportsPanel } from "./ReportsPanel";
import { AssessmentPanel } from "./AssessmentPanel";
import { MentorGroupPanel } from "./MentorGroupPanel";
import { OutputsTabs } from "./OutputsTabs";
import { ThesisQuality } from "./ThesisQuality";
import { BusinessRulesPanel } from "./BusinessRulesPanel";
import { AnalysisPanel } from "./AnalysisPanel";
import { WorkbenchAlerts } from "./ProcessAlerts";
import { RecordPanel } from "./RecordPanel";
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { AccessPanel } from "./AccessPanel";
import { AgentPanel } from "./AgentPanel";
import { AuditPanel } from "./AuditPanel";
import { MilestonePanel } from "./MilestonePanel";
import { PaperPanel } from "./PaperPanel";
import { CoursePanel } from "./CoursePanel";
import { ResolutionPanel } from "./ResolutionPanel";
import { StudentPanel } from "./StudentPanel";
import { ModelPanel } from "./ModelPanel";
import { CollegeSelect } from "./CollegeSelect";

type Role =
  | "mentor"
  | "platform_admin"
  | "college_data_admin"
  | "college_analyst"
  | "school_data_admin"
  | "school_analyst";
type User = {
  id: number;
  username: string;
  roles: Role[];
  active: boolean;
  school_view?: boolean;
  version: number;
  business_permissions: string[];
  account_preset?: AccountPreset;
  account_scope?: "college" | "school";
  account_colleges?: string[];
  preset_college?: string;
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
type AccountPreset = "ordinary" | "full";
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
    [preset, setPreset] = useState<AccountPreset>("ordinary");
  const [accountCollege, setAccountCollege] = useState("");
  const [accountScope, setAccountScope] = useState<"college" | "school">("college");
  const [editingAccount, setEditingAccount] = useState<User | null>(null);
  const accountFormRef = useRef<HTMLElement>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [navLabel, setNavLabel] = useState("工作台概览");
  const [page, setPage] = useState("overview");
  const contentRef = useRef<HTMLElement>(null);
  useEffect(() => { contentRef.current?.scrollTo(0, 0); }, [page]);
  useEffect(() => {
    const expired = () => {
      setSession(null);
      setUsers([]);
      setPassword("");
      setUsername("");
      setPage("overview");
      setEditingAccount(null);
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
      const account = editingAccount;
      await request(
        account ? `/api/users/${account.id}` : "/api/users",
        account ? "PATCH" : "POST",
        {
          ...(account
            ? { active: account.active, expected_version: account.version }
            : { username, password }),
          roles: [preset === "full" ? "platform_admin" : "college_analyst"],
          preset,
          scope: accountScope,
          college: accountScope === "college" ? accountCollege.trim() : "",
          request_id: crypto.randomUUID(),
        },
        session?.csrf_token,
      );
      setUsername("");
      setPassword("");
      setEditingAccount(null);
      setPreset("ordinary");
      setAccountScope("college");
      setAccountCollege("");
      setNotice(account ? "账号权限已更新" : "账号已创建，权限已自动配置");
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
        <button className="mobile-nav-toggle" aria-expanded={navOpen} aria-controls="workspace-navigation" onClick={() => setNavOpen(!navOpen)}>{navLabel} · {navOpen ? "收起导航" : "展开导航"}</button>
        <nav id="workspace-navigation" className={navOpen ? "is-open" : ""} aria-label="主导航">
          {[
            { label: "工作台", items: [["overview", "工作台概览"]] },
            {
              label: "研究分析",
              items: [
                ["analysis", "培养过程分析"],
                ["thesis_quality", "学位论文质量"],
                ["evaluation", "拔尖人才模拟评价"],
                ["reports", "三级报告"],
                ["agent", "Agent 智能问答"],
              ],
            },
            {
              label: "数据管理",
              items: [
                ["students", "基础导入与学生档案"],
                ["courses", "课程导入与待关联"],
                ["milestones", "选题与中期导入"],
                ["assessments", "盲审与答辩"],
                ["outputs", "科研成果导入"],
                ["thesis_upload", "学位论文上传"],
                ["mentor_groups", "导师与课题组数据"],
                ["maintenance", "数据纠错与维护"],
              ],
            },
            {
              label: "业务规则",
              items: [["rules", "业务规则管理"]],
            },
            {
              label: "系统管理",
              items: [
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
                  onClick={() => { setPage(key); setNavLabel(label); setNavOpen(false); }}
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
      <main className="content" ref={contentRef}>
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
                  assessments: "盲审与答辩",
                  outputs: "科研成果导入",
                  thesis_upload: "学位论文上传",
                  mentor_groups: "导师与课题组数据",
                  agent: "Agent 智能问答",
                  thesis_quality: "学位论文质量",
                  rules: "业务规则管理",
                  evaluation: "拔尖人才模拟评价",
                  reports: "三级报告",
                  analysis: "培养过程分析",
                  courses: "课程导入与待关联",
                  students: "基础导入与学生档案",
                  model: "获准模型连接",
                }[page]
              }
            </h1>
          </div>
          <div className="user-menu">
            <span title={session.user.username}>{session.user.username}</span>
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
        ) : page === "assessments" ? (
          <AssessmentPanel csrf={session.csrf_token} />
        ) : page === "milestones" ? (
          <MilestonePanel csrf={session.csrf_token} fetcher={request} />
        ) : page === "mentor_groups" ? (<MentorGroupPanel csrf={session.csrf_token} />) : page === "outputs" ? (<OutputsTabs csrf={session.csrf_token} />) : page === "thesis_upload" ? (
          <PaperPanel csrf={session.csrf_token} />
        ) : page === "thesis_quality" ? (
          <ThesisQuality csrf={session.csrf_token} />
        ) : page === "rules" ? (
          <BusinessRulesPanel csrf={session.csrf_token} />
        ) : page === "agent" ? (
          <AgentPanel csrf={session.csrf_token} />
        ) : page === "evaluation" ? (
          <EvaluationPanel csrf={session.csrf_token} />
        ) : page === "reports" ? (
          <ReportsPanel csrf={session.csrf_token} />
        ) : page === "analysis" ? (
          <AnalysisPanel csrf={session.csrf_token} />
        ) : page === "courses" ? (
          <CoursePanel csrf={session.csrf_token} />
        ) : page === "students" ? (
          <StudentPanel csrf={session.csrf_token} fetcher={request} />
        ) : page === "model" && admin ? (
          <ModelPanel csrf={session.csrf_token} fetcher={request} />
        ) : page === "overview" || !admin ? (
          <>
            <section className="welcome">
              <p>当前账号：{session.user.username}</p>
              <div className="tags">
                {session.user.roles.map((role) => (
                  <span key={role}>{roleNames[role]}</span>
                ))}
                <span>{session.user.account_scope === "school" && session.user.account_preset === "full"
                  ? "全校全权限"
                  : session.user.school_view ? "全校查看和分析" : "按授权范围访问"}</span>
              </div>
            </section>
            <div className="workbench-actions" role="group" aria-label="常用操作">
              {[
                ["students", "基础导入与学生档案", "查学生档案"],
                ["analysis", "培养过程分析", "查学生培养过程"],
                ["reports", "三级报告", "看学生报告"],
              ].map(([key, label, action]) => (
                <button key={key} type="button" className="secondary" onClick={() => {
                  setPage(key);
                  setNavLabel(label);
                }}>{action}</button>
              ))}
            </div>
            <WorkbenchAlerts openAnalysis={() => {
              setPage("analysis");
              setNavLabel("培养过程分析");
            }} />
          </>
        ) : (
          <>
            <section className="card" ref={accountFormRef}>
              <h2>{editingAccount ? `更改权限 · ${editingAccount.username}` : "创建个人账号"}</h2>
              <form className="account-form" onSubmit={create}>
                {!editingAccount && <>
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
                </>}
                <label>
                  账号权限
                  <select value={preset} onChange={(e) => setPreset(e.target.value === "full" ? "full" : "ordinary")}>
                    <option value="ordinary">普通</option>
                    <option value="full">全权限</option>
                  </select>
                </label>
                <label>
                  操作范围
                  <select value={accountScope} onChange={(event) => setAccountScope(event.target.value === "school" ? "school" : "college")}>
                    <option value="college">指定学院</option>
                    <option value="school">全校</option>
                  </select>
                </label>
                {accountScope === "college" && <CollegeSelect
                  key={editingAccount?.id ?? "new"}
                  label="所属学院"
                  value={accountCollege}
                  onChange={setAccountCollege}
                  required
                />}
                <p className="muted">
                  新权限：{preset === "ordinary" ? "普通" : "全权限"} · {accountScope === "school" ? "全校" : accountCollege || "请选择学院"}。
                  {preset === "ordinary" ? "可查看和分析，学生姓名和学号会隐藏。" : "可管理账号，查看、导入、修改和导出数据，也可查看学生身份与下载原件。"}
                </p>
                {editingAccount && <p className="muted">
                  原权限：{editingAccount.account_preset === "full" ? "全权限" : editingAccount.account_preset === "ordinary" ? "普通" : "原有配置"}
                  {editingAccount.account_scope === "school"
                    ? " · 全校"
                    : ` · ${editingAccount.account_colleges?.join("、") || "未配置学院业务权限"}`}
                  {editingAccount.school_view && editingAccount.account_scope !== "school" && " · 全校查看"}
                  。保存将替换原有权限。
                </p>}
                <button disabled={busy || (accountScope === "college" && !accountCollege.trim())}>
                  {editingAccount ? "保存权限" : "创建账号"}
                </button>
                {editingAccount && <button className="secondary" type="button" onClick={() => setEditingAccount(null)}>取消</button>}
              </form>
            </section>
            <section className="card">
              <h2>
                账号列表 <span className="muted">{users.length}</span>
              </h2>
              <div className="table-wrap">
                <table className="accounts-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>账号权限</th>
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
                          {user.account_preset ? (
                            <>
                              <span>{user.account_preset === "full" ? "全权限" : "普通"}</span>
                              <small>{user.account_scope === "school" ? "全校" : user.preset_college}</small>
                            </>
                          ) : (
                            <>原有配置<small>{user.roles.map((role) => roleNames[role]).join("、")}</small></>
                          )}
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
                            onClick={() => {
                              setEditingAccount(user);
                              setPreset(user.roles.includes("platform_admin") ? "full" : "ordinary");
                              setAccountCollege(user.preset_college ?? "");
                              setAccountScope(user.account_scope === "school" ? "school" : "college");
                              accountFormRef.current?.scrollIntoView({ block: "start" });
                            }}
                          >
                            更改权限
                          </button>{" "}
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
            <details className="card">
              <summary>高级授权</summary>
              <AccessPanel
                key={session.user.id}
                admin={admin}
                csrf={session.csrf_token}
                users={users}
                fetcher={request}
              />
            </details>
          </>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);

