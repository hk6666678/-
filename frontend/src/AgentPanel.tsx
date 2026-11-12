import { useEffect, useState } from "react";

type ModelStatus = {
  enabled: boolean;
  approved: boolean;
  version: number;
  available: boolean;
  message: string;
};

type AgentResult = {
  answer: string;
  plan: unknown;
  tool_result: unknown;
  evidence_links: { label: string; url: string }[];
  model_version: number;
  generated_at: number;
};

export function AgentPanel({ csrf }: { csrf: string }) {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AgentResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/model/status", { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw new Error("模型状态读取失败");
        return (await response.json()) as ModelStatus;
      })
      .then(setStatus)
      .catch((err: unknown) => setError(String(err)));
  }, []);

  async function ask() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch("/api/agent/query", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
        },
        body: JSON.stringify({ question }),
      });
      const value = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          value && typeof value.detail === "string"
            ? value.detail
            : "Agent 查询失败",
        );
      }
      setResult(value as AgentResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Agent 查询与解释</h2>
      <p>
        只读查询学生档案、人数统计、培养统计、论文特征、同类比较、候选依据和人工复核历史。数字由系统工具计算；
        写操作、任意SQL和任意文件访问不可用；论文回答区分作者主张、专家评价与系统推荐，不输出优秀概率。
      </p>
      <p role="status">{status ? status.message : "模型状态读取中…"}</p>
      {status && !status.available && (
        <p className="muted">
          未配置获准模型时不会发送业务数据，也不会用固定回答冒充模型结果。
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void ask();
        }}
      >
        <label>
          问题
          <textarea
            value={question}
            rows={3}
            maxLength={2000}
            required
            onChange={(event) => setQuestion(event.target.value)}
          />
        </label>
        <button disabled={busy || question.trim().length < 2}>
          {busy ? "查询中…" : "发送只读问题"}
        </button>
      </form>
      {result && (
        <article>
          <h3>Agent 回答</h3>
          <p>{result.answer}</p>
          <p>
            模型配置版本 {result.model_version} · 生成时间{" "}
            {new Date(result.generated_at * 1000).toLocaleString()}
          </p>
          {result.evidence_links.map((link) => (
            <a key={link.url} href={link.url}>
              {link.label}
            </a>
          ))}
          <details>
            <summary>工具结果与口径</summary>
            <pre>{JSON.stringify(result.tool_result, null, 2)}</pre>
          </details>
        </article>
      )}
    </section>
  );
}
