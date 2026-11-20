import { useEffect, useState } from "react";

type Result = {
  as_of: string;
  has_group: boolean;
  items: { college: string; course_code: string; term: string; score: number; peer_count: number; peer_mean: number | null; record_ids: number[] }[];
};

function ComparisonTable({ studentId }: { studentId: number }) {
  const [result, setResult] = useState<Result>();
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`/api/cultivation/students/${studentId}/mentor-course-comparison`, { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw Error(typeof data.detail === "string" ? data.detail : "暂时无法读取课程对比。");
        setResult(data);
      })
      .catch((err: Error) => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [studentId]);
  if (error) return <p role="alert">{error}</p>;
  if (!result) return <p role="status">正在读取课程对比…</p>;
  if (!result.has_group) return <p>当前范围暂无可查看的有效导师课题组关系。</p>;
  if (!result.items.length) return <p>该学生暂无可比较的百分制课程成绩。</p>;
  return <>
    <p>按 {result.as_of} 有效指导关系比较。同学院开课范围、同课程和同学期，先汇总每人多次成绩；可比同组学生不足 3 人时不显示组均分。</p>
    <div className="table-wrap"><table>
      <thead><tr><th>课程</th><th>本人均分</th><th>同导师组均分</th><th>可比人数</th><th>本人记录</th></tr></thead>
      <tbody>{result.items.map((item) => (
        <tr key={JSON.stringify([item.college, item.course_code, item.term])}>
          <th scope="row">{item.course_code} · {item.term} · {item.college}</th>
          <td>{item.score.toFixed(1)}</td><td>{item.peer_mean?.toFixed(1) ?? "样本不足"}</td><td>{item.peer_count}</td>
          <td>{item.record_ids.map((id) => <div key={id}><a href={`/api/records/courses/${id}`} target="_blank" rel="noreferrer">记录 #{id}</a></div>)}</td>
        </tr>
      ))}</tbody>
    </table></div>
  </>;
}

export function MentorCourseComparison({ studentId }: { studentId: number }) {
  const [open, setOpen] = useState(false);
  return <details className="task-details" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>同导师组课程对比</summary>
    {open && <ComparisonTable studentId={studentId} />}
  </details>;
}
