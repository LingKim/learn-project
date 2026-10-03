# 2026-10-03 实施分期（首期已批准）

调研时已有真实业务执行器、硬编码Prompt片段/哈希manifest和PracticeRun/KnowledgeRun，没有统一AgentRegistry/AgentRun或PromptDefinition/PromptVersion；下述首期已获用户“可以”批准，在独立分支实施。当前进度与验证见本目录 evidence.md 和集成交付记录。

建议首批纳管**question_generator/practice_generate**真实生成场景，完整交付注册边界、模板/变量、不可变依赖版本、管理员草稿/Diff/合成预览/固定评测/发布/回滚/停用/审计，并以真实PracticeRun验证任务启动时快照和历史不漂移。保留现有manifest键，动态题位Schema实例参与评测指纹；其他真实场景留待后续接入，不创建七套空角色模板。

现有输出与业务模型保留；新AgentRun只存版本/hash/context来源与业务引用，不复制正文。注册受管场景无活动发布版本不能静默fallback；启用前需当前批准内容草稿经过真实合成评测后发布。已启动任务必须固定使用入队快照，停用/发布不影响旧任务。

公共契约、迁移链、文件归属与具体验收详见 [下一批并行实施方案](../../../docs/development/parallel-next-batch-20261003.md)。当前模型、FTS命名、事务设计与文件路径是技术工作。后端及非视觉前端 API/query 已获批准；缺失 Pen 页面仍等待设计参考授权，不据本期批准猜测视觉状态。
