import { AgentEvidence } from "./AgentEvidence";
import { CultivationOverview, type EvidenceTarget } from "./CultivationOverview";
import { useEffect, useRef, useState } from "react";

type ModelStatus = { available: boolean; message: string };
type AlertFacts = { filters?: {student_id:number}; evidence_actions?: (Omit<EvidenceTarget,"student"> & {label:string})[] };
type Turn = {
  request?: {question:string; student_number?:string};
  stale?: boolean;
  question: string;
  result?: {
    answer: string;
    needs_student_number?: boolean;
    evidence_links: { label: string; url: string }[];
    tool_result: unknown;
  };
  error?: string;
};

export function AgentPanel({ csrf }: { csrf: string }) {
  const [target, setTarget] = useState<EvidenceTarget>();
  const [status, setStatus] = useState<ModelStatus>();
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState("");
  const [clarification, setClarification] = useState("");
  const latest = useRef<HTMLDivElement>(null);
  const questionField = useRef<HTMLTextAreaElement>(null);

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
    const followUp = clarification && /^[\w-]{2,100}$/.test(prompt);
    const original = followUp ? clarification : prompt;
    if (!followUp) setClarification("");
    setPending(prompt);
    setQuestion("");
    const request = {question:original, ...(followUp && {student_number:prompt})};
    try {
      const response = await fetch("/api/agent/query", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(request),
      });
      const value = await response.json().catch(() => null);
      if (!response.ok) throw Error(typeof value?.detail === "string" ? value.detail : "暂时无法完成查询。");
      setClarification(value.needs_student_number ? original : "");
      setTurns((previous) => [...previous, { question: prompt, request, result: value }]);
    } catch (err) {
      setTurns((previous) => [...previous, { question: prompt, error: err instanceof Error ? err.message : String(err) }]);
    } finally {
      setPending("");
    }
  }

  if (target) return <section className="card">
    <button onClick={() => setTarget(undefined)}>返回首页对话</button>
    <h2>培养过程分析 · 个人趋势</h2>
    <CultivationOverview csrf={csrf} target={target} showSnapshot={() => {}} onTopicChanged={() => {
      setTurns(previous => previous.map(turn => {
        const facts = turn.result?.tool_result as AlertFacts | undefined;
        return facts?.filters?.student_id === target.student && facts.evidence_actions?.some(action =>
          action.kind === "topic" && action.record === target.record && action.actual === target.actual && action.date === target.date)
          ? {...turn, stale:true} : turn;
      }));
    }} onTopicDenied={async () => {
      // The same grant may cover several students already discussed in this conversation.
      const queries = new Map<number, NonNullable<Turn["request"]>>();
      const replacements = new Map<Turn, Turn>();
      for (const turn of turns) {
        const facts = turn.result?.tool_result as AlertFacts | undefined;
        const id = facts?.filters?.student_id;
        if (!id || !facts?.evidence_actions || !turn.request) continue;
        queries.set(id, turn.request);
        replacements.set(turn, {...turn, stale:false, result:{
          answer:"权限已变化，正在重新核对培养依据。", evidence_links:[], tool_result:null,
        }});
      }
      setTurns(previous => previous.map(turn => replacements.get(turn) ?? turn));
      await Promise.all(Array.from(queries, async ([id, request]) => {
        let result: Turn["result"];
        try {
          const response = await fetch("/api/agent/query", {
            method:"POST", headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},
            body:JSON.stringify(request),
          });
          if (!response.ok) throw Error();
          const fresh = await response.json();
          if (fresh.tool_result?.filters?.student_id !== id) throw Error();
          result = fresh;
        } catch {
          result = {answer:"权限已变化，暂时无法重新核对培养依据，请重新查询。", evidence_links:[], tool_result:null};
        }
        const pendingTurns = new Set(Array.from(replacements).filter(([old]) =>
          (old.result?.tool_result as AlertFacts).filters?.student_id === id).map(([,pending]) => pending));
        setTurns(previous => previous.map(turn => pendingTurns.has(turn) ? {...turn, result} : turn));
      }));
    }} />
  </section>;
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
                  <p>{turn.stale && <strong>原选题结论已过时，请查看最新日期依据。<br /></strong>}{turn.result.answer}</p>
                  <div className="agent-evidence">
                    {(() => {
                      const facts = turn.result.tool_result as AlertFacts | null;
                      const student = facts?.filters?.student_id;
                      return student && facts?.evidence_actions?.map(action =>
                        <button type="button" key={action.record ?? action.kind} onClick={() =>
                          setTarget({...action, student})}>{action.label}{action.date && `（${action.date}）`}</button>);
                    })()}
                    {turn.result.evidence_links.map((link) => <a key={link.url} href={link.url}>{link.label}</a>)}
                  </div>
                  <details>
                    <summary>查看计算依据</summary>
                    <AgentEvidence data={turn.result.tool_result} />
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
        <textarea ref={questionField} aria-label="问题" placeholder={clarification ? "输入学号，按回车继续查询" : "输入你想查询的问题"} rows={3} maxLength={2000}
          enterKeyHint="send" aria-describedby="agent-input-hint"
          value={question} onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
            event.preventDefault();
            if (!event.repeat) event.currentTarget.form?.requestSubmit();
          }} />
        <div className="agent-composer-actions">
          <span id="agent-input-hint">Enter 发送 · Shift+Enter 换行</span>
          <button disabled={!status?.available || !!pending || question.trim().length < 2}>发送问题</button>
        </div>
      </form>
      {!turns.length && !pending && status?.available && (
        <div className="agent-suggestions" aria-label="示例提问">
          {["目前系统多少学生？", "学号 23501006 的学生有哪些培养预警？", "查询规则编号 1 的 2027 年五年滚动基准分位"].map((example) => (
            <button className="secondary" key={example} type="button" onClick={() => {
              setQuestion(example);
              questionField.current?.focus();
            }}>{example}</button>
          ))}
        </div>
      )}
      {!status?.available && <div className="agent-connection" role="status">
        <span>{status?.message ?? "正在检查 Agent 连接…"}</span>
      </div>}
      <div ref={latest} />
    </section>
  );
}
