import { useEffect, useState } from "react";
type Paper = {id:number;version:number;student_id?:number;title?:string;level:string;discipline:string;year:string;status:string;failure_code?:string;features:Record<string,number>|null;semantic_features:string};
type StudentOption = { id: number; name?: string; research_id: string; data: Record<string, string> };
export function PaperPanel({csrf}:{csrf:string}) {
 const [items,setItems]=useState<Paper[]>([]),[error,setError]=useState(""),[evidence,setEvidence]=useState(""),[studentId,setStudentId]=useState("");
 const [students, setStudents] = useState<StudentOption[]>([]);
 const [rosterError, setRosterError] = useState(false);
 const [covered, setCovered] = useState<string[]>([]);
 const [confirmed, setConfirmed] = useState(false);
 const [busy, setBusy] = useState(false);
 const selected = students.find((student) => String(student.id) === studentId);
 const studentLabel = (student: StudentOption) => [student.name, student.research_id, student.data["专业"]].filter(Boolean).join(" · ");
 async function call(url:string,options:RequestInit={}) {const r=await fetch(url,options);if(!r.ok) {const e=await r.json();throw new Error(typeof e.detail==='string'?e.detail:'请检查输入');}return r.json();}
 async function refresh(){try{setItems((await call('/api/papers')).items);}catch(e){setError(String(e));}}
 useEffect(()=>{void refresh();const t=setInterval(()=>void refresh(),2500);return ()=>clearInterval(t);},[]);
 useEffect(() => {
   const controller = new AbortController();
   async function loadStudents() {
     const options: StudentOption[] = [];
     let total = 0;
     do {
       const response = await fetch(`/api/students?limit=200&offset=${options.length}`, { signal: controller.signal });
       if (!response.ok) throw Error();
       const page = await response.json() as { items: StudentOption[]; total: number };
       total = page.total;
       if (!page.items.length) break;
       options.push(...page.items);
     } while (options.length < total);
     if (!controller.signal.aborted) setStudents(options);
   }
   void loadStudents().catch(() => { if (!controller.signal.aborted) setRosterError(true); });
   return () => controller.abort();
 }, []);
 async function upload(event: React.FormEvent<HTMLFormElement>) {
   event.preventDefault();
   if (!selected || !confirmed) return;
   const form = new FormData(event.currentTarget);
   const current = items.reduce((version, item) => item.student_id === selected.id ? Math.max(version, item.version) : version, 0);
   form.set("expected_version", String(current));
   form.set("covered_student_ids", JSON.stringify([selected.id, ...covered.map(Number)]));
   setBusy(true);
   try {
     await call("/api/papers", { method: "POST", headers: { "X-CSRF-Token": csrf }, body: form });
     setError("");
     setConfirmed(false);
     await refresh();
   } catch (e) {
     setError(String(e));
     await refresh();
   } finally {
     setBusy(false);
   }
 }
 return <section><h2>论文上传与本地解析</h2>{error&&<p role="alert">{error}</p>}{rosterError&&<p role="alert">无法读取学生档案，请检查查看权限。</p>}<form onSubmit={upload}>
   <label>研究生<select aria-label="研究生" name="student_id" value={studentId} required onChange={(e) => {
     setStudentId(e.target.value);
     setCovered([]);
     setConfirmed(false);
   }}>
     <option value="">请选择研究生</option>
     {students.map((student) => <option key={student.id} value={student.id}>{studentLabel(student)}</option>)}
   </select></label>
   <label>标题<input name="title" required maxLength={500}/></label>
   <label>论文PDF<input name="file" type="file" accept=".pdf" required onChange={() => setConfirmed(false)}/></label>
   {selected && <details className="task-details" key={selected.id}>
     <summary>论文信息及其他涉及的学生{covered.length ? `（已选 ${covered.length} 人）` : ""}</summary>
     <label>培养层次<input name="level" defaultValue={selected.data["培养层次"]} maxLength={500}/></label>
     <label>学科／专业<input name="discipline" defaultValue={selected.data["专业"]} maxLength={500}/></label>
     <label>年度<input name="year" maxLength={500}/></label>
     <label>其他涉及的学生（可多选）<select aria-label="其他涉及的学生" multiple value={covered}
       onChange={(e) => {
         setCovered(Array.from(e.target.selectedOptions, (option) => option.value));
         setConfirmed(false);
       }}>
       {students.filter((student) => student.id !== selected.id).map((student) => <option key={student.id} value={student.id}>{studentLabel(student)}</option>)}
     </select></label>
   </details>}
   <label className="check-option"><input type="checkbox" checked={confirmed} required onChange={(e) => setConfirmed(e.target.checked)} />已核对 PDF 涉及的全部学生</label>
   <button disabled={busy || !selected}>上传新版本并排队</button></form>
 <h3>上传记录</h3>
 <button className="secondary" onClick={()=>void refresh()}>刷新进度</button>
 {items.map(p=><article key={p.id}><h3>{p.title||'论文（身份已隐藏）'} · 版本{p.version}</h3><p>{p.level||'层次缺失'} / {p.discipline||'学科缺失'} / {p.year||'年度缺失'}</p><p>{({queued:'排队',processing:'处理中',succeeded:'成功',failed:'失败'} as Record<string,string>)[p.status]} {p.failure_code&&({no_text:'无可提取文字（可能为扫描件）',encrypted:'加密PDF',damaged_or_unavailable:'文件损坏或不可用'} as Record<string,string>)[p.failure_code]}</p><p>{p.semantic_features}</p>{p.features&&<pre>{JSON.stringify(p.features,null,2)}</pre>}<button onClick={()=>void call(`/api/papers/${p.id}/evidence`).then(r=>setEvidence(JSON.stringify(r,null,2))).catch(e=>setError(String(e)))}>查看页序证据</button>{p.status==='succeeded'&&<><button onClick={()=>void call(`/api/papers/${p.id}/semantic`,{method:'POST',headers:{'X-CSRF-Token':csrf}}).then(r=>setEvidence(JSON.stringify(r,null,2))).catch(e=>setError(String(e)))}>提取／重试智能特征</button><button onClick={()=>void call(`/api/papers/${p.id}/semantic`).then(r=>setEvidence(JSON.stringify(r,null,2))).catch(e=>setError(String(e)))}>智能特征与历史依据</button></>}<a href={`/api/papers/${p.id}/download`}>下载原件</a>{p.status==='failed'&&<button onClick={()=>void call(`/api/papers/${p.id}/retry`,{method:'POST',headers:{'X-CSRF-Token':csrf}}).then(refresh).catch(e=>setError(String(e)))}>重试</button>}</article>)}<pre style={{whiteSpace:'pre-wrap'}}>{evidence}</pre></section>;
}
