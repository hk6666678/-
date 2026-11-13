import { useEffect, useState } from "react";
type Participant = {student_number?: string; name?: string; order: number; role: string; association: string};
type Output = {id:number; version:number; business_key:string; title:string; participants:Participant[]};
type History = {version:number;source_department:string;payload:{title:string;void_reason?:string}};
type Batch = {id:string; items:{business_key:string;status:string;payload:{title:string}}[]};
export function ResearchOutputs({csrf}:{csrf:string}) {
  const [items,setItems]=useState<Output[]>([]), [batch,setBatch]=useState<Batch|null>(null), [error,setError]=useState(""), [busy,setBusy]=useState(false), [loaded,setLoaded]=useState(false), [accept,setAccept]=useState(false);
  const [selected,setSelected]=useState<Output|null>(null), [history,setHistory]=useState<History[]>([]), [reason,setReason]=useState("");
  const [voided,setVoided]=useState(false);
  async function call(url:string, options:RequestInit={}) {
    const response=await fetch(url,{credentials:"same-origin",...options});
    const result=await response.json();
    if(!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "输入格式无效");
    return result;
  }
  async function reload(){try{setItems((await call(`/api/research-outputs?voided=${voided}`)).items);setLoaded(true);}catch(e){setError(String(e));}}
  useEffect(()=>{void reload();},[voided]);
  async function preview(event:React.FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError("");setBatch(null);setAccept(false);try{setBatch(await call("/api/research-outputs/preview",{method:"POST",headers:{"X-CSRF-Token":csrf},body:new FormData(event.currentTarget)}));}catch(e){setError(String(e));}finally{setBusy(false);}}
  async function confirm(){if(!batch)return;setBusy(true);setError("");try{await call(`/api/research-outputs/previews/${batch.id}/confirm`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({accept_changes:accept})});setBatch(null);await reload();}catch(e){setError(String(e));}finally{setBusy(false);}}
  async function showHistory(item:Output){setError("");setSelected(null);setHistory([]);setReason("");try{const result=await call(`/api/research-outputs/${item.id}/history`);setSelected(item);setHistory(result.items);}catch(e){setError(String(e));}}
  async function voidOutput(event:React.FormEvent){event.preventDefault();if(!selected)return;setBusy(true);setError("");try{await call(`/api/research-outputs/${selected.id}/void`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({expected_version:selected.version,reason})});await showHistory({...selected,version:selected.version+1});await reload();}catch(e){setError(String(e));}finally{setBusy(false);}}
  return <section className="card"><h2>已发表科研论文</h2><p>科研成果独立于学位论文。相同业务编号每位参与者填写一行；保留作者次序与角色。学号缺档时待关联，身份冲突需纠正。</p><a href="/api/research-outputs/template">下载科研论文模板 v1</a>
    <form onSubmit={preview}><label>来源部门<input name="source_department" required /></label><label>标准 Excel 文件<input type="file" name="file" accept=".xlsx" required /></label><button disabled={busy}>预览导入</button></form>
    {error&&<p role="alert">{error}</p>}{busy&&<p role="status">处理中…</p>}
    {batch&&<section><h3>导入预览</h3><ul>{batch.items.map(item=><li key={item.business_key}>{item.payload.title} · {item.business_key} · {{new:"新增",change:"内容变更",duplicate:"重复跳过"}[item.status]}</li>)}</ul><label><input type="checkbox" checked={accept} onChange={e=>setAccept(e.target.checked)}/>明确确认内容变更，保留历史版本</label><button disabled={busy} onClick={()=>void confirm()}>确认导入</button></section>}
    <h3>当前授权范围</h3><label style={{display:"flex",alignItems:"center",gap:"0.5rem"}}><input style={{width:"auto"}} type="checkbox" checked={voided} onChange={e=>{setSelected(null);setVoided(e.target.checked);}}/>查看已作废成果</label><p>个人参与次数：{voided?0:items.reduce((sum,item)=>sum+item.participants.length,0)}；范围内成果去重数：{voided?0:items.length}。同一论文可计多次个人参与，成果只计一次。</p>
    {!loaded?<p>正在加载…</p>:items.length===0?<p>当前授权范围内暂无科研论文。</p>:<table><thead><tr><th>业务编号</th><th>标题</th><th>版本</th><th>可见参与者</th><th>操作</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{item.business_key}</td><td>{item.title}</td><td>{item.version}</td><td>{item.participants.map(p=><p key={p.order}>{p.order} · {p.name||"身份未授权"} {p.student_number||""} · {p.role} · {p.association==="pending"?"待关联":"已关联"}</p>)}</td><td><button onClick={()=>void showHistory(item)}>来源与历史</button></td></tr>)}</tbody></table>}
    {selected&&<section aria-label="成果来源与历史"><h3>{selected.title} · 来源与历史</h3><button onClick={()=>setSelected(null)}>关闭历史</button><table><thead><tr><th>版本</th><th>来源部门</th><th>标题</th><th>作废依据</th></tr></thead><tbody>{history.map(entry=><tr key={entry.version}><td>{entry.version}</td><td>{entry.source_department}</td><td>{entry.payload.title}</td><td>{entry.payload.void_reason||"—"}</td></tr>)}</tbody></table>{history.some(entry=>entry.payload.void_reason)?<p role="status">该成果已作废，原始内容和历史继续保留。</p>:<form onSubmit={voidOutput}><label>作废依据<input required value={reason} onChange={e=>setReason(e.target.value)}/></label><p>确认作废后，该成果退出当前统计，保留原始内容与操作历史。</p><button disabled={busy||!reason.trim()}>确认作废成果</button></form>}</section>}
  </section>;
}
