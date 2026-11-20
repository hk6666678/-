import { EvidenceDetails, evidenceLabel } from "./EvidenceDetails";
import { useEffect, useState } from "react";
type Paper = {id:number;version:number;student_id?:number;title?:string;level:string;discipline:string;year:string;status:string;failure_code?:string;features:Record<string,number>|null};
type StudentOption = { id: number; name?: string; research_id: string; data: Record<string, string> };
export function PaperPanel({csrf}:{csrf:string}) {
 const [items,setItems]=useState<Paper[]>([]),[error,setError]=useState(""),[evidence,setEvidence]=useState<{ paperId: number; label: string; data: unknown }>(),[studentId,setStudentId]=useState("");
 const [students, setStudents] = useState<StudentOption[]>([]);
 const [rosterError, setRosterError] = useState(false);
 const [covered, setCovered] = useState<string[]>([]);
 const [confirmed, setConfirmed] = useState(false);
 const [busy, setBusy] = useState(false);
 const selected = students.find((student) => String(student.id) === studentId);
 const studentLabel = (student: StudentOption) => [student.name, student.research_id, student.data["专业"]].filter(Boolean).join(" · ");
 async function call(url:string,options:RequestInit={}) {const r=await fetch(url,options);if(!r.ok) {const e=await r.json();throw new Error(typeof e.detail==='string'?e.detail:'请检查输入');}return r.json();}
 async function refresh(){try{setItems((await call('/api/papers')).items);}catch(e){setError(String(e));}}
 useEffect(() => {
   void refresh();
   const timer = window.setInterval(() => void refresh(), 2500);
   return () => window.clearInterval(timer);
 }, []);
 async function showEvidence(paperId: number, label: string, path: string, extract = false) {
   setError("");
   setEvidence(undefined);
   try {
     const data = await call(path, extract ? { method: "POST", headers: { "X-CSRF-Token": csrf } } : {});
     setEvidence({ paperId, label, data });
   } catch (error) {
     setError(error instanceof Error ? error.message : String(error));
   }
 }
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
 {items.length === 0 && <p className="muted">暂无可查看的论文上传记录。</p>}
 <div className="paper-records">
   {items.map((paper) => <article className="card paper-record" key={paper.id}>
     <header className="paper-record-header">
       <h3>{paper.title || "论文（身份已隐藏）"}</h3>
       <span className="paper-status" data-status={paper.status}>{{ queued: "等待解析", processing: "正在解析", succeeded: "解析成功", failed: "解析失败" }[paper.status] ?? "状态待核查"}</span>
     </header>
     <p className="muted">版本 {paper.version} / {paper.level || "培养层次未登记"} / {paper.discipline || "学科未登记"} / {paper.year ? `${paper.year} 年` : "年度未登记"}</p>
     {paper.failure_code && <p>{{ no_text: "PDF 没有可提取的文字，请检查是否为扫描件。", encrypted: "PDF 已加密，请上传可读取的文件。", damaged_or_unavailable: "文件损坏或不可用，请核对原件后重试。" }[paper.failure_code] ?? "无法完成解析，请核对原件后重试。"}</p>}
     {paper.features && <dl className="paper-metrics">
       {["page_count", "character_count", "section_count", "reference_count"].map((key) => <div key={key}>
         <dt>{evidenceLabel(key)}</dt><dd>{paper.features?.[key] ?? "待核查"}</dd>
       </div>)}
     </dl>}
     <div className="action-row paper-record-actions">
       <button type="button" className="secondary" onClick={() => void showEvidence(paper.id, "页序证据", `/api/papers/${paper.id}/evidence`)}>查看页序证据</button>
       {paper.status === "succeeded" && <>
         <button type="button" className="secondary" onClick={() => void showEvidence(paper.id, "智能特征", `/api/papers/${paper.id}/semantic`, true)}>提取智能特征</button>
         <button type="button" className="secondary" onClick={() => void showEvidence(paper.id, "智能特征与历史依据", `/api/papers/${paper.id}/semantic`)}>智能特征与历史依据</button>
       </>}
       <a href={`/api/papers/${paper.id}/download`}>下载原件</a>
       {paper.status === "failed" && <button onClick={() => void call(`/api/papers/${paper.id}/retry`, { method: "POST", headers: { "X-CSRF-Token": csrf } }).then(refresh).catch((error) => setError(String(error)))}>重试解析</button>}
     </div>
     {evidence?.paperId === paper.id && <details open className="task-details">
       <summary>{evidence.label}</summary>
       <EvidenceDetails data={evidence.data} />
     </details>}
   </article>)}
 </div></section>;
}
