import { useState } from "react";
import { CollegeSelect } from "./CollegeSelect";

type Result = {
  cohort_count: number;
  points: { research_id: string; score: number; output_count: number; topic_record_id: number; output_ids: number[] }[];
  excluded: Record<string, number>;
  uncertain_participations: number;
  pearson_r: number | null;
};

export function TopicCorrelation() {
  const [college, setCollege] = useState("");
  const [result, setResult] = useState<Result>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const maxCount = Math.max(1, ...(result?.points.map((p) => p.output_count) ?? []));
  return (
    <details>
      <summary>选题分数与科研成果相关性</summary>
      <form onSubmit={async (event) => {
        event.preventDefault();
        const query = new URLSearchParams({ college });
        for (const [key, value] of new FormData(event.currentTarget))
          query.set(key, String(value).trim());
        setBusy(true);
        setResult(undefined);
        setError("");
        try {
          const response = await fetch(`/api/analyses/topic-correlation?${query}`);
          const body = await response.json();
          if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "请检查分析条件");
          setResult(body);
        } catch (error) {
          setError(String(error));
        } finally {
          setBusy(false);
        }
      }}>
        <CollegeSelect label="相关性分析学院" value={college} onChange={setCollege} />
        <label>相关性分析专业<input name="major" required /></label>
        <label>入学年份<input name="entry_year" type="number" min="1900" max="2100" required /></label>
        <label>相关性分析成果类别
          <select name="category">
            <option value="research_papers">科研论文</option><option value="patents">专利</option>
            <option value="awards">获奖项目</option><option value="conferences">会议</option>
          </select>
        </label>
        <button disabled={busy || !college}>计算相关性</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <p>有效样本 {result.points.length}/{result.cohort_count} 人。Pearson r {result.pearson_r?.toFixed(3) ?? "不可计算（样本少于 3 人或变量无差异）"}。</p>
          {Object.entries(result.excluded).map(([reason, count]) => <p key={reason}>{reason} · {count} 人</p>)}
          <p>按同学院、同专业、同届学生首次有实际日期的选题百分制成绩及所选类别的选题后成果数比较。无法确定先后的成果参与 {result.uncertain_participations} 次，未计入成果数。结论仅描述关联，随访时长和成果收录完整性可能影响结果。</p>
          {result.points.length > 0 && (
            <svg viewBox="0 0 440 175" width="440" style={{ maxWidth: "100%" }} role="img" aria-label="选题分数与选题后成果数散点图">
              <path d="M45 15 V135 H420" fill="none" stroke="currentColor" />
              <text x="0" y="18">成果数</text><text x="5" y="38">{maxCount}</text>
              <text x="25" y="135">0</text><text x="45" y="154">0</text><text x="393" y="154">100</text><text x="182" y="170">选题分数</text>
              {result.points.map((point) => (
                <circle key={point.research_id} cx={45 + 365 * point.score / 100} cy={135 - 105 * point.output_count / maxCount} r="4" fill="#2563eb">
                  <title>{point.research_id} · {point.score} 分 · {point.output_count} 项</title>
                </circle>
              ))}
            </svg>
          )}
          <details>
            <summary>样本与来源记录</summary>
            <ul>{result.points.map((point) => <li key={point.research_id}>
              {point.research_id} · {point.score} 分 · 选题记录 #{point.topic_record_id} · 选题后成果 {point.output_count} 项
              {point.output_ids.map((id) => ` #${id}`)}
            </li>)}</ul>
          </details>
        </>
      )}
    </details>
  );
}
