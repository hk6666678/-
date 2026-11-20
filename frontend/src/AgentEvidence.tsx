import { EvidenceDetails, evidenceLabel } from "./EvidenceDetails";

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const sourceNames: Record<string, string> = {
  "research-outputs": "论文", patents: "专利", awards: "获奖", conferences: "会议",
};

export function AgentEvidence({ data }: { data: unknown }) {
  if (!record(data) || !("peer_outputs" in data)) return <EvidenceDetails data={data} />;
  const { peer_outputs: peer, course_trend: course, ...other } = data;
  return <div className="signal-evidence">
    <section><h4>同届成果对比</h4>
      {record(peer) && typeof peer.count === "number" && typeof peer.peer_median === "number" ? <>
        <div className="signal-metrics">
          <div><span>本人登记成果</span><strong>{peer.count}<small> 项</small></strong></div>
          <div><span>同届同专业中位数</span><strong>{peer.peer_median}<small> 项</small></strong></div>
        </div>
        <p>与中位数相比{peer.count === peer.peer_median ? "持平" : `${peer.count < peer.peer_median ? "少" : "多"} ${Math.abs(peer.count - peer.peer_median)} 项`}
          {typeof peer.peer_count === "number" && ` · 比较范围 ${peer.peer_count} 人`}</p>
        {Array.isArray(peer.sources) && peer.sources.length > 0 && <details><summary>成果来源（{peer.sources.length}）</summary>
          <ul>{peer.sources.map((source, index) => {
            const match = typeof source === "string" && /^\/api\/(research-outputs|patents|awards|conferences)\/(\d+)\/history$/.exec(source);
            return <li key={index}>{match ? <a href={source} target="_blank" rel="noreferrer">{sourceNames[match[1]]}记录 #{match[2]}</a> : <EvidenceDetails data={source} />}</li>;
          })}</ul></details>}
      </> : <EvidenceDetails data={peer} />}
    </section>
    {record(course) && Array.isArray(course.observations) ? <section>
      <h4>课程成绩趋势</h4><p><b>{String(course.signal ?? "")}</b>
        {typeof course.baseline_count === "number" && ` · 基于 ${course.baseline_count} 个历史学期`}
        {Array.isArray(course.limits) && ` · 控制区间 ${course.limits.join(" 至 ")} 分`}</p>
      <div className="signal-terms">{course.observations.map((row, index) => record(row) && typeof row.mean === "number"
        ? <div className="signal-term" key={index}><span>{String(row.term)}</span>
          <i aria-hidden="true"><i style={{width: `${Math.max(0, Math.min(100, row.mean))}%`}} /></i>
          <strong>{row.mean} 分</strong><small>{String(row.records)} 条</small></div>
        : <EvidenceDetails key={index} data={row} />)}</div>
    </section> : course != null && <EvidenceDetails data={course} />}
    {Object.entries(other).map(([key,value]) => <details key={key} open={key === "notice"}>
      <summary>{evidenceLabel(key)}{value == null ? " · 暂无记录" : ""}</summary><EvidenceDetails data={value} />
    </details>)}
  </div>;
}
