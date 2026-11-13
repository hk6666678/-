import { useEffect, useState } from "react";
type Batch = {
  id: string;
  valid_count: number;
  errors: { row: number; message: string }[];
};
type Template = {
  version: string;
  state: string;
  simulation: boolean;
  items: Record<string, number>;
  confirmed_by?: string;
  basis?: string;
};
type Item = {
  id: number;
  category: string;
  paper_version_id: number;
  batch: string;
  anonymous_code: string;
  template_version: string;
  scores: Record<string, number>;
  comment?: string;
};
export function AssessmentPanel({ csrf }: { csrf: string }) {
  const [items, setItems] = useState<Item[]>([]),
    [batch, setBatch] = useState<Batch>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false),
    [notice, setNotice] = useState(""),
    [templates, setTemplates] = useState<Template[]>([]);
  async function call(url: string, init?: RequestInit) {
    const r = await fetch(url, init);
    const v = await r.json();
    if (!r.ok)
      throw Error(typeof v.detail === "string" ? v.detail : "字段校验失败");
    return v;
  }
  async function load() {
    const v = await call("/api/external-assessments");
    setItems(v.items);
    setLoaded(true);
    setTemplates((await call("/api/external-assessments/templates")).items);
  }
  useEffect(() => {
    void load().catch((e) => setError(String(e)));
  }, []);
  return (
    <section>
      <p>
        关联论文版本与考核批次。simulation-v1为模拟评分配置，不代表正式业务标准。未使用真实模型。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <h3>Excel集中导入</h3>
      <a href="/api/external-assessments/template">
        下载标准Excel模板 · simulation-v1
      </a>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          setBusy(true);
          setError("");
          setBatch(undefined);
          try {
            setBatch(
              await call("/api/external-assessments/import/preview", {
                method: "POST",
                headers: { "X-CSRF-Token": csrf },
                body: data,
              }),
            );
          } catch (err) {
            setError(String(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          标准Excel文件
          <input
            name="file"
            type="file"
            accept=".xlsx"
            required
            onChange={() => setBatch(undefined)}
          />
        </label>
        <button disabled={busy}>上传并预览</button>
      </form>
      {batch && (
        <section>
          <h3>预览批次</h3>
          <p>
            {batch.id} · 可导入 {batch.valid_count} 行 · 错误{" "}
            {batch.errors.length} 行
          </p>
          {batch.errors.length > 0 && (
            <>
              <p>请按行号修改Excel，再重新上传；错误批次不会提交。</p>
              <table>
                <thead>
                  <tr>
                    <th>Excel行号</th>
                    <th>错误原因</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.errors.map((e) => (
                    <tr key={e.row}>
                      <td>{e.row}</td>
                      <td>{e.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <a href={`/api/external-assessments/import/${batch.id}/errors`}>
                查看错误报告
              </a>
            </>
          )}
          <button
            disabled={
              busy || batch.errors.length > 0 || batch.valid_count === 0
            }
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                await call(
                  `/api/external-assessments/import/${batch.id}/confirm`,
                  { method: "POST", headers: { "X-CSRF-Token": csrf } },
                );
                setBatch(undefined);
                setNotice("批次已确认");
                await load();
              } catch (err) {
                setError(String(err));
              } finally {
                setBusy(false);
              }
            }}
          >
            确认导入本批次
          </button>
        </section>
      )}
      <details>
        <summary>评分模板版本管理</summary>
        <p>
          维护权限创建不可覆盖的新草稿；独立启用权限与业务确认后方可用于导入。旧记录继续引用原版本。
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setError("");
            try {
              await call("/api/external-assessments/templates", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "X-CSRF-Token": csrf,
                },
                body: JSON.stringify({
                  version: f.get("version"),
                  category: f.get("category"),
                  college: f.get("college"),
                  major: f.get("major"),
                  items: JSON.parse(String(f.get("items"))),
                  simulation: f.get("simulation") === "on",
                }),
              });
              setNotice("模板草稿已保存");
              await load();
            } catch (err) {
              setError(String(err));
            }
          }}
        >
          <label>
            版本号
            <input name="version" required />
          </label>
          <label>
            类别
            <select name="category">
              <option value="blind_reviews">盲审</option>
              <option value="defenses">答辩</option>
            </select>
          </label>
          <label>
            学院
            <input name="college" required />
          </label>
          <label>
            专业
            <input name="major" required />
          </label>
          <label>
            分项上限JSON
            <input name="items" defaultValue={'{"quality":100}'} required />
          </label>
          <label>
            <input name="simulation" type="checkbox" defaultChecked />
            模拟配置
          </label>
          <button>保存新版本草稿</button>
        </form>
        <table>
          <thead>
            <tr>
              <th>版本</th>
              <th>状态</th>
              <th>配置</th>
              <th>业务确认</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.version}>
                <td>{t.version}</td>
                <td>
                  {t.simulation ? "模拟" : "正式"} ·{" "}
                  {t.state === "active" ? "已启用" : "草稿"}
                </td>
                <td>{JSON.stringify(t.items)}</td>
                <td>
                  {t.state === "draft" ? (
                    <form
                      onSubmit={async (e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        try {
                          await call(
                            `/api/external-assessments/templates/${encodeURIComponent(t.version)}/activate`,
                            {
                              method: "POST",
                              headers: {
                                "Content-Type": "application/json",
                                "X-CSRF-Token": csrf,
                              },
                              body: JSON.stringify({
                                confirmed_by: f.get("confirmed_by"),
                                basis: f.get("basis"),
                              }),
                            },
                          );
                          setNotice("模板已启用");
                          await load();
                        } catch (err) {
                          setError(String(err));
                        }
                      }}
                    >
                      <label>
                        业务确认人
                        <input name="confirmed_by" required />
                      </label>
                      <label>
                        确认依据
                        <input name="basis" required />
                      </label>
                      <button>确认启用此版本</button>
                    </form>
                  ) : (
                    `${t.confirmed_by ?? "系统模拟配置"} · ${t.basis ?? "演示使用"}`
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      <h3>考核记录</h3>
      <button onClick={() => void load().catch((e) => setError(String(e)))}>
        刷新记录
      </button>
      {!loaded ? (
        <p>正在读取…</p>
      ) : items.length === 0 ? (
        <p>当前范围暂无可见记录。</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>类别</th>
              <th>论文版本</th>
              <th>批次</th>
              <th>匿名编号</th>
              <th>模板版本</th>
              <th>分项成绩</th>
              <th>意见</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id}>
                <td>{i.category === "blind_reviews" ? "盲审" : "答辩"}</td>
                <td>{i.paper_version_id}</td>
                <td>{i.batch}</td>
                <td>{i.anonymous_code}</td>
                <td>{i.template_version}</td>
                <td>{JSON.stringify(i.scores)}</td>
                <td>{i.comment ?? "需原文读取授权"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
