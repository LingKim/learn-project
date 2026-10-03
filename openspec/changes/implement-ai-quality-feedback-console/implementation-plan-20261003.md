# 2026-10-03 实施分期（待批准）

本地已实现真实资料问答、RetrievalTrace、练习与学习资产，但尚无质量工单领域。原evidence的历史事实保留，当前判断以本次核验为准。

建议首批完整交付**本人资料模式的已完成LearningTurn且trace_complete=true**工单闭环、授权与管理员诊断/受控回放。通用模式无Trace，本期不新增伪Trace；其他结果源随后按同样adapter拓展。保持原规格的单次字段授权、30天/关闭时失效、撤销立即拒读、7天清理及管理员禁止全局正文浏览规则。

开发前冻结owner/source/trace、结果不可变身份、授权读取adapter、回放真实能力与迁移链。当前关键词实际为PostgreSQL FTS，不是BM25；回放名称与能力准确标记，测试内候选离线对照不能当生产回放服务或因果证明。

后端/前端独立worktree文件归属、验收矩阵和与Prompt模块的公共契约详见 [下一批并行实施方案](../../../docs/development/parallel-next-batch-20261003.md)。此文档不代表已获本期具体实施批准。
