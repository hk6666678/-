import { CitationPanel } from "./CitationPanel";
import { OutputCohorts } from "./OutputCohorts";
import { useEffect, useRef, useState } from "react";
type Participant = {student_number?: string; name?: string; order: number; role: string; association: string};
type Output = {id:number; version:number; business_key:string; title:string; details:Record<string,string>; participants:Participant[]};
type History = {version:number;source_department:string;payload:{title:string;void_reason?:string}};
type Batch = {id:string; items:{business_key:string;status:string;payload:{title:string}}[]};
export function ResearchOutputs({csrf,category="research_outputs"}:{csrf:string;category?:string}) {
  const endpoint=category==="research_outputs"?"research-outputs":category;
  const label:Record<string,string>={research_outputs:"已发表科研论文",patents:"专利",awards:"获奖项目",conferences:"会议"};
  const title=label[category];
  const [items,setItems]=useState<Output[]>([]), [batch,setBatch]=useState<Batch|null>(null), [error,setError]=useState(""), [busy,setBusy]=useState(false), [loaded,setLoaded]=useState(false), [accept,setAccept]=useState(false);
  const [selected,setSelected]=useState<Output|null>(null), [history,setHistory]=useState<History[]>([]), [reason,setReason]=useState("");
  const [voided,setVoided]=useState(false);
  const listRequest = useRef(0);
  const historyRequest = useRef(0);
  const [cohortVersion,setCohortVersion]=useState(0);
  const [stats,setStats]=useState<{years:{year:string;distinct_outputs:number;personal_participations:number}[];basis:string;missing_citations:number}|null>(null);
  const [counts,setCounts]=useState<{personal_participations:number;distinct_outputs:number;can_view?:boolean}>();
  async function call(url:string, options:RequestInit={}) {
    const response=await fetch(url,{credentials:"same-origin",...options});
    const result=await response.json();
    if(!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "输入格式无效");
    return result;
  }
  function closeHistory() {
    historyRequest.current++;
    setSelected(null);
    setHistory([]);
  }
  async function reload() {
    const request = ++listRequest.current;
    historyRequest.current++;
    setItems([]);
    setCounts(undefined);
    setStats(null);
    setLoaded(false);
    try {
      const result = await call(`/api/${endpoint}?voided=${voided}`);
      if (request !== listRequest.current) return;
      setItems(result.items);
      setCounts(result);
      setCohortVersion(version => version + 1);
      setLoaded(true);
      if (!voided && result.can_view !== false) {
        const statistics = await call(`/api/${endpoint}/statistics`);
        if (request === listRequest.current) setStats(statistics);
      }
    } catch (e) {
      if (request === listRequest.current) setError(String(e));
    }
  }
  useEffect(()=>{void reload();},[voided]);
  async function preview(event:React.FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError("");setBatch(null);setAccept(false);try{setBatch(await call(`/api/${endpoint}/preview`,{method:"POST",headers:{"X-CSRF-Token":csrf},body:new FormData(event.currentTarget)}));}catch(e){setError(String(e));}finally{setBusy(false);}}
  async function confirm(){if(!batch)return;setBusy(true);setError("");try{await call(`/api/${endpoint}/previews/${batch.id}/confirm`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({accept_changes:accept})});setBatch(null);await reload();}catch(e){setError(String(e));}finally{setBusy(false);}}
  async function showHistory(item: Output) {
    const request = ++historyRequest.current;
    setError("");
    setSelected(null);
    setHistory([]);
    setReason("");
    try {
      const result = await call(`/api/${endpoint}/${item.id}/history`);
      if (request !== historyRequest.current) return;
      setSelected(item);
      setHistory(result.items);
    } catch (e) {
      if (request !== historyRequest.current) return;
      setError(String(e));
      await reload();
    }
  }
  async function voidOutput(event:React.FormEvent){event.preventDefault();if(!selected)return;setBusy(true);setError("");try{await call(`/api/${endpoint}/${selected.id}/void`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({expected_version:selected.version,reason})});await showHistory({...selected,version:selected.version+1});await reload();}catch(e){setError(String(e));}finally{setBusy(false);}}
  return <section className="card"><h2>{title}</h2><details className="task-details"><summary>导入{title}</summary><p>每位参与者填写一行，共同成果使用相同业务编号。</p><a href={`/api/${endpoint}/template`}>下载{title}模板 v1</a>
    <form onSubmit={preview}><label>来源部门<input name="source_department" required /></label><label>标准 Excel 文件<input type="file" name="file" accept=".xlsx" required /></label><button disabled={busy}>预览导入</button></form>
        {batch&&<section><h3>导入预览</h3><ul>{batch.items.map(item=><li key={item.business_key}>{item.payload.title} · {item.business_key} · {{new:"新增",change:"内容变更",duplicate:"重复跳过"}[item.status]}</li>)}</ul><label><input type="checkbox" checked={accept} onChange={e=>setAccept(e.target.checked)}/>明确确认内容变更，保留历史版本</label><button disabled={busy} onClick={()=>void confirm()}>确认导入</button></section>}
</details>
    {error&&<p role="alert">{error}</p>}{busy&&<p role="status">处理中…</p>}
    <h3>当前授权范围</h3><button type="button" className="secondary" onClick={() => { closeHistory(); setError(""); void reload(); }}>刷新当前授权范围</button><label style={{display:"flex",alignItems:"center",gap:"0.5rem"}}><input style={{width:"auto"}} type="checkbox" checked={voided} onChange={e=>{closeHistory();listRequest.current++;setVoided(e.target.checked);}}/>查看已作废成果</label>{counts?.can_view === false && <p>当前账号没有此类成果的查看权限。</p>}{counts && counts.can_view !== false && <><p>仅统计当前账号获准查看的成果。</p><dl className="summary-pair"><div><dt>成果数（去重）</dt><dd>{counts.distinct_outputs} 项</dd></div><div><dt>个人参与次数</dt><dd>{counts.personal_participations} 人次</dd></div></dl></>}
    {counts?.can_view === false ? null : !loaded?<p>正在加载…</p>:items.length===0?<p>当前授权范围内暂无{title}。</p>:<table><thead><tr><th>业务编号</th><th>标题</th><th>版本</th><th>可见参与者</th><th>操作</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{item.business_key}</td><td>{item.title}{Object.entries(item.details||{}).map(([key,value])=><p key={key}>{key}：{value}</p>)}</td><td>{item.version}</td><td>{item.participants.map(p=><p key={p.order}>{p.order} · {p.name||"身份未授权"} {p.student_number||""} · {p.role} · {p.association==="pending"?"待关联":"已关联"}</p>)}</td><td><button onClick={()=>void showHistory(item)}>来源与历史</button></td></tr>)}</tbody></table>}
    {selected&&<section aria-label="成果来源与历史"><div className="output-history-title"><h3>{selected.title} · 来源与历史</h3><button className="secondary" onClick={closeHistory}>关闭历史</button></div>{category==="research_outputs"&&<CitationPanel key={selected.id} id={selected.id} csrf={csrf} onChange={()=>void reload()}/>}<h3 className="output-version-title">成果版本与作废</h3><table><thead><tr><th>版本</th><th>来源部门</th><th>标题</th><th>作废依据</th></tr></thead><tbody>{history.map(entry=><tr key={entry.version}><td>{entry.version}</td><td>{entry.source_department}</td><td>{entry.payload.title}</td><td>{entry.payload.void_reason||"—"}</td></tr>)}</tbody></table>{history.some(entry=>entry.payload.void_reason)?<p role="status">该成果已作废，原始内容和历史继续保留。</p>:<form className="output-danger" onSubmit={voidOutput}><label>作废依据<input required value={reason} onChange={e=>setReason(e.target.value)}/></label><p>确认作废后，该成果退出当前统计，保留原始内容与操作历史。</p><button disabled={busy||!reason.trim()}>确认作废成果</button></form>}</section>}
    {counts?.can_view !== false&&stats&&!voided&&<details className="task-details"><summary>年度成果统计</summary><p>{stats.basis}</p><table><thead><tr><th>年份</th><th>成果去重数</th><th>个人参与人次</th></tr></thead><tbody>{stats.years.map(y=><tr key={y.year}><td>{y.year}</td><td>{y.distinct_outputs}</td><td>{y.personal_participations}</td></tr>)}</tbody></table>{category==="research_outputs"&&<p>缺引用快照成果：{stats.missing_citations}。各成果引用历史见来源与历史。</p>}</details>}
    {counts?.can_view !== false&&loaded&&!voided&&<details className="task-details"><summary>同届排名与培养阶段</summary><OutputCohorts key={cohortVersion} endpoint={endpoint}/></details>}
  </section>;
}
