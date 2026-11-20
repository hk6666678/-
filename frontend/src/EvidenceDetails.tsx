const labels: Record<string, string> = {
  id: "记录编号", record_id: "记录编号", version_id: "论文版本编号", version: "版本",
  rule_id: "规则编号", rule_version: "规则版本", student_id: "学生档案编号", research_id: "研究编号",
  paper_version_id: "论文版本编号", comparison_id: "比较快照编号", snapshot_id: "评分或分析快照编号",
  page_count: "页数", character_count: "字符数", section_count: "章节数", reference_count: "参考文献条数",
  pages: "各页内容", page: "页码", text: "原文", quote: "引用原句", sections: "章节", references: "参考文献",
  items: "明细", result: "结果", features: "特征", source: "来源", source_department: "来源部门",
  sheet: "工作表", row_number: "行号", source_row_id: "来源行编号", batch_id: "导入批次编号",
  before: "更正前", after: "更正后", payload: "登记内容", data: "登记数据", original_row: "原始导入内容",
  reason: "原因", notice: "说明", status: "状态", type: "类型", category: "类别", name: "名称",
  history: "版本历史", archive: "学生档案", courses: "课程", milestones: "培养节点",
  topic: "选题", midterm: "中期考核", assessments: "盲审与答辩", scores: "评分",
  assessment_count: "考核记录数", student_count: "学生数", total: "总计", count: "数量",
  missing: "缺项", missing_count: "缺失人数", missing_rate: "缺失率", passed: "通过数",
  unknown: "状态未知数", failed: "未通过数", pass_ratio: "通过比例", pass_rate: "通过率",
  evidence: "依据", filters: "查询条件", scope: "查询范围", limitations: "适用范围与限制",
  course_code: "课程编号", term: "学期", attempt: "修读次数", academic_year: "学年",
  college: "学院", major: "专业", grade: "年级", entry_year: "入学年份", level: "培养层次",
  discipline: "学科／专业", year: "年度", title: "题名", value: "数值", feature: "指标",
  files: "文件", created_at: "记录时间", as_of: "统计时间", generated_at: "生成时间",
  stale: "依据有变化", active: "有效", enabled: "已启用", basis: "依据说明", operation: "操作",
  decision: "结论", comment: "意见", confirmed_by: "确认人", actor_id: "操作账号编号",
  by_level: "按培养层次", by_major: "按专业", by_grade: "按年级", dependencies: "依赖记录",
  mobility: "学籍异动", course_trend: "课程趋势", output_trend: "成果增量", blind_review: "盲审",
  milestone_trends: "选题与中期趋势", peer_outputs: "同届成果对比", signal: "判断结果",
  model_version: "模型版本", semantic_features: "智能特征", author_innovation_claim: "作者自述创新点",
  research_question: "研究问题", method: "研究方法", outcome_description: "研究成果描述",
};

const values: Record<string, string> = {
  linked: "已关联", pending: "待处理", draft: "草稿", queued: "等待解析",
  ready: "可导入", invalid: "校验未通过", conflict: "待核对冲突", duplicate: "重复记录",
  imported: "已导入", confirmed: "已确认", success: "成功", denied: "无权限",
  processing: "处理中", succeeded: "成功", failed: "失败", missing: "缺少记录",
  unauthorized: "当前无权查看", correct: "更正", void: "作废", simulation: "模拟",
  courses: "课程", topic: "选题", midterm: "中期考核", patents: "专利", awards: "获奖",
  conferences: "会议", research_papers: "科研论文", blind_reviews: "盲审", defenses: "答辩",
};

export function evidenceLabel(key: string) {
  return Object.hasOwn(labels, key) ? labels[key] : key.replaceAll("_", " ");
}

export function evidenceValue(value: string) {
  return Object.hasOwn(values, value) ? values[value] : value;
}

export function EvidenceDetails({ data, label }: { data: unknown; label?: string }) {
  if (data == null || data === "") return <span className="evidence-empty">暂无记录</span>;
  if (Array.isArray(data)) {
    if (!data.length) return <span className="evidence-empty">暂无记录</span>;
    return <ol className="evidence-list" aria-label={label}>{data.map((entry, index) => (
      <li key={index}><EvidenceDetails data={entry} /></li>
    ))}</ol>;
  }
  if (typeof data === "object") {
    const fields = Object.entries(data);
    if (!fields.length) return <span className="evidence-empty">暂无记录</span>;
    return <dl className="evidence-fields" aria-label={label}>{fields.map(([key, value]) => (
      <div key={key}><dt>{evidenceLabel(key)}</dt><dd>
        {typeof value === "number" && value >= 946684800 && /^(created_at|as_of|generated_at)$/.test(key)
          ? new Date(value * 1000).toLocaleString()
          : typeof value === "string" && value && /^(text|quote|comment|title)$/.test(key)
            ? <span className="evidence-value">{value}</span>
            : <EvidenceDetails data={value} />}
      </dd></div>
    ))}</dl>;
  }
  if (typeof data === "boolean") return <span>{data ? "是" : "否"}</span>;
  return <span className="evidence-value">{typeof data === "string" ? evidenceValue(data) : String(data)}</span>;
}
