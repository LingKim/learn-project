export const reviewLabels: Record<string, string> = {
  source_unavailable: "来源已失效，本次不作掌握验证。",
  in_progress: "练习未完成，本次验证尚未结束。",
  insufficient_sample: "相关题不足 3 道，本次样本不足。",
  incomplete_evidence: "仍有未提交或未评分的相关题，本次证据不完整。",
  low_confidence: "包含低置信度评分，本次尚不能验证通过。",
  needs_learning: "仍有错误或部分正确的相关题，建议继续学习。",
};
