import { useState } from "react";
type Entry = {
  id: number;
  category: string;
  version: number;
  active: boolean;
  can_void: boolean;
  dependency_token: string;
  current: Record<string, string>;
  revisions: {
    version: number;
    before: Record<string, string>;
    after: Record<string, string>;
    reason: string;
    operation: string;
    actor_id: number;
    source: unknown;
  }[];
};
export function RecordPanel({ csrf }: { csrf: string }) {
  const [category, C] = useState("basic"),
    [items, I] = useState<Entry[]>([]),
    [selected, S] = useState<Entry | null>(null),
    [values, V] = useState<Record<string, string>>({}),
    [reason, R] = useState(""),
    [identity, H] = useState(false),
    [showVoided, setShowVoided] = useState(false),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [error, E] = useState(""),
    [proposal, P] = useState<{ proposal_id: string; changes: unknown } | null>(
      null,
    );
  async function call(url: string, body?: unknown) {
    const r = await fetch(url, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: body ? JSON.stringify(body) : undefined,
    });
    const d = await r.json();
    if (!r.ok)
      throw Error(typeof d.detail === "string" ? d.detail : "请检查输入");
    return d;
  }
  async function run(f: () => Promise<void>) {
    E("");
    setNotice("");
    setBusy(true);
    try {
      await f();
    } catch (e) {
      E(String(e));
    } finally {
      setBusy(false);
    }
  }
  function choose(x: Entry) {
    S(x);
    V({ ...x.current });
    P(null);
    R("");
    H(false);
  }
  async function refresh(includeVoided = showVoided) {
    I(
      (await call(`/api/records/${category}?include_void=${includeVoided}&limit=200`))
        .items,
    );
  }
  async function finish(op: string) {
    if (!selected) return;
    await call(
      `/api/records/${category}/${selected.id}/${op}`,
      op === "void"
        ? { expected_version: selected.version, reason, confirmed: true }
        : {
            expected_version: selected.version,
            proposal_id: proposal?.proposal_id,
          },
    );
    const next = await call(`/api/records/${category}/${selected.id}`);
    choose(next);
    await refresh();
    if (op === "void") setNotice("记录已作废，已从有效记录列表移除。");
  }
  return (
    <section className="card">
      <h2>正式记录更正与历史</h2>
      <p>
        核对新旧差异后确认更正；身份变更须填写人工核实依据。作废保留原始内容和历史。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <label>
        记录类别
        <select
          value={category}
          onChange={(e) => {
            C(e.target.value);
            I([]);
            S(null);
            P(null);
          }}
        >
          {Object.entries({
            basic: "基础档案",
            courses: "课程",
            topic: "选题",
            midterm: "中期",
          }).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <label>
        <input
          type="checkbox"
          checked={showVoided}
          disabled={busy}
          onChange={(e) => {
            const checked = e.target.checked;
            setShowVoided(checked);
            void run(() => refresh(checked));
          }}
        />
        显示已作废记录
      </label>
      <button disabled={busy} onClick={() => void run(refresh)}>加载正式记录</button>
      {items.map((x) => (
        <button key={x.id} className="secondary" onClick={() => choose(x)}>
          记录{x.id} · 版本{x.version} · {x.active ? "有效" : "已作废"}
        </button>
      ))}
      {selected && (
        <div>
          <h3>
            记录{selected.id} · 版本{selected.version}
          </h3>
          <p>数据修订标识：{selected.dependency_token}</p>
          {Object.entries(values).map(([k, v]) => k === "所属学院" ? (
            <CollegeSelect
              key={k}
              label={k}
              value={v}
              disabled={!selected.active}
              onChange={(college) => {
                V({ ...values, [k]: college });
                P(null);
              }}
            />
          ) : (
            <label key={k}>
              {k}
              <input
                value={v}
                disabled={!selected.active}
                onChange={(e) => {
                  V({ ...values, [k]: e.target.value });
                  P(null);
                }}
              />
            </label>
          ))}
          <label>
            更正或作废依据
            <textarea
              maxLength={2000}
              value={reason}
              onChange={(e) => {
                R(e.target.value);
                P(null);
              }}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={identity}
              onChange={(e) => {
                H(e.target.checked);
                P(null);
              }}
            />
            已人工核实身份变更，并在依据中记录证据
          </label>
          {selected.active && !selected.can_void && <p>此账号没有作废这条记录的权限。</p>}
          {selected.can_void && !reason.trim() && <p>先填写上方的更正或作废依据，再点作废。</p>}
          <button
            disabled={busy || !selected.can_void || !reason.trim()}
            onClick={() =>
              void run(async () =>
                P(
                  await call(
                    `/api/records/${category}/${selected.id}/preview`,
                    {
                      expected_version: selected.version,
                      data: values,
                      reason,
                      identity_confirmed: identity,
                    },
                  ),
                ),
              )
            }
          >
            预览新旧差异
          </button>
          {proposal && (
            <>
              <pre aria-label="新旧差异">
                {JSON.stringify(proposal.changes, null, 2)}
              </pre>
              <button onClick={() => void run(() => finish("confirm"))}>
                确认此更正
              </button>
            </>
          )}
          <button
            disabled={!selected.active || !reason.trim()}
            onClick={() => void run(() => finish("void"))}
          >
            确认按原因作废
          </button>
          <h3>修订历史</h3>
          {selected.revisions.map((v) => (
            <article key={v.version}>
              <p>
                版本{v.version} · {v.operation} · 操作者{v.actor_id} ·{" "}
                {v.reason}
              </p>
              <pre>
                {JSON.stringify(
                  { 原值: v.before, 新值: v.after, 来源: v.source },
                  null,
                  2,
                )}
              </pre>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
import { CollegeSelect } from "./CollegeSelect";
