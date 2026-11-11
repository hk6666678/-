import { useState } from "react";
type Event = {
  id: number;
  actor_id: number | null;
  action: string;
  target: string;
  outcome: string;
  created_at: number;
  details: unknown;
};
type Result = {
  items: Event[];
  total: number;
  page: number;
  page_size: number;
  notice: string;
};
export function AuditPanel({
  fetcher,
}: {
  fetcher: <T>(url: string) => Promise<T>;
}) {
  const [actor, setActor] = useState(""),
    [action, setAction] = useState(""),
    [target, setTarget] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [data, setData] = useState<Result | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function load(page: number) {
    setBusy(true);
    setError("");
    setData(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: "25",
      });
      if (actor) params.set("actor_id", actor);
      if (action) params.set("action", action);
      if (target) params.set("target", target);
      if (start)
        params.set(
          "started_at",
          String(Math.floor(new Date(start).getTime() / 1000)),
        );
      if (end)
        params.set(
          "ended_at",
          String(Math.floor(new Date(end).getTime() / 1000)),
        );
      setData(await fetcher<Result>("/api/audit?" + params));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>审计查询与追溯</h2>
      <p>仅平台管理员可查看管理元信息；此权限不开放学生内容或原始文件。</p>
      <form
        className="account-form"
        onSubmit={(e) => {
          e.preventDefault();
          void load(1);
        }}
      >
        <label>
          操作者账号 ID
          <input
            type="number"
            min="1"
            value={actor}
            onChange={(e) => setActor(e.target.value)}
          />
        </label>
        <label>
          操作名称
          <input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="例如 user.update"
          />
        </label>
        <label>
          目标对象
          <input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="精确匹配原始对象标识"
          />
        </label>
        <label>
          开始时间
          <input
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          结束时间
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
        <button disabled={busy}>查询审计</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {data && (
        <>
          <p role="status">
            共 {data.total} 条，第 {data.page} 页。{data.notice}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>编号 / 时间</th>
                  <th>操作者</th>
                  <th>操作 / 目标</th>
                  <th>结果与详情</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((event) => (
                  <tr key={event.id}>
                    <td>
                      {event.id}
                      <small>
                        {new Date(event.created_at * 1000).toLocaleString()}
                      </small>
                    </td>
                    <td>{event.actor_id ?? "未登录"}</td>
                    <td>
                      {event.action}
                      <small>{event.target}</small>
                    </td>
                    <td>
                      {event.outcome}
                      <details>
                        <summary>版本及原因信息</summary>
                        <pre>{JSON.stringify(event.details, null, 2)}</pre>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            className="secondary"
            disabled={busy || data.page === 1}
            onClick={() => void load(data.page - 1)}
          >
            上一页
          </button>
          <button
            className="secondary"
            disabled={busy || data.page * data.page_size >= data.total}
            onClick={() => void load(data.page + 1)}
          >
            下一页
          </button>
        </>
      )}
    </section>
  );
}
