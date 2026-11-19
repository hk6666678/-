import { useEffect, useRef, useState } from "react";

type ModelStatus = { available: boolean; message: string };
type Turn = {
  question: string;
  result?: {
    answer: string;
    evidence_links: { label: string; url: string }[];
    tool_result: unknown;
  };
  error?: string;
};

export function AgentPanel({ csrf }: { csrf: string }) {
  const [status, setStatus] = useState<ModelStatus>();
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState("");
  const latest = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/model/status", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw Error();
        return await response.json() as ModelStatus;
      })
      .then(setStatus)
      .catch(() => {
        if (!controller.signal.aborted) setStatus({ available: false, message: "暂时无法读取 Agent 状态，请刷新重试。" });
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (turns.length || pending) latest.current?.scrollIntoView({ block: "end" });
  }, [turns, pending]);

  async function ask() {
    const prompt = question.trim();
    if (!status?.available || pending || prompt.length < 2) return;
    setPending(prompt);
    setQuestion("");
    try {
      const response = await fetch("/api/agent/query", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ question: prompt }),
      });
      const value = await response.json().catch(() => null);
      if (!response.ok) throw Error(typeof value?.detail === "string" ? value.detail : "暂时无法完成查询。");
      setTurns((previous) => [...previous, { question: prompt, result: value }]);
    } catch (err) {
      setTurns((previous) => [...previous, { question: prompt, error: err instanceof Error ? err.message : String(err) }]);
    } finally {
      setPending("");
    }
  }

  return (
    <section className="agent-home" aria-label="Agent 对话">
      {!turns.length && !pending ? (
        <header className="agent-home-intro">
          <img src="/tongji-emblem.png" width="82" height="82" alt="同济大学校标" />
          <h2>今天想了解什么培养问题？</h2>
          <p>查询学生档案、培养过程、科研成果与研究分析。</p>
        </header>
      ) : (
        <div className="agent-thread" aria-live="polite">
          {turns.map((turn, index) => (
            <article key={index} className="agent-turn">
              <p className="agent-question">{turn.question}</p>
              {turn.error && <p role="alert">{turn.error}</p>}
              {turn.result && (
                <div className="agent-answer">
                  <h3>Agent 回答</h3>
                  <p>{turn.result.answer}</p>
                  <div className="agent-evidence">
                    {turn.result.evidence_links.map((link) => <a key={link.url} href={link.url}>{link.label}</a>)}
                  </div>
                  <details>
                    <summary>查看计算依据</summary>
                    <pre>{JSON.stringify(turn.result.tool_result, null, 2)}</pre>
                  </details>
                </div>
              )}
            </article>
          ))}
          {pending && <article className="agent-turn">
            <p className="agent-question">{pending}</p>
            <p role="status">正在查询…</p>
          </article>}
        </div>
      )}
      <form className="agent-composer" onSubmit={(event) => {
        event.preventDefault();
        void ask();
      }}>
        <textarea aria-label="问题" placeholder="输入你想查询的问题" rows={3} maxLength={2000}
          value={question} onChange={(event) => setQuestion(event.target.value)} />
        <div className="agent-composer-actions">
          <span>只读查询 · 每条问题独立计算</span>
          <button disabled={!status?.available || !!pending || question.trim().length < 2}>发送问题</button>
        </div>
      </form>
      {!status?.available && <div className="agent-connection" role="status">
        <span>{status?.message ?? "正在检查 Agent 连接…"}</span>
      </div>}
      <div ref={latest} />
    </section>
  );
}
