# 下一批开发：质量诊断台与提示词管理

状态：用户已批准推荐的首期边界，2026-10-03 开始在独立集成分支实施。调研基线为本地 `main@57629ef`；本轮三个 worktree 只修复学习闭环。以下是对既有 PRD/OpenSpec 的实施拆分，不扩大业务边界。

## 当前已完成与真实缺口

认证/画像、文件生命周期、文档解析/OCR/受保护检索、流式问答/附件、五型练习、难点/文字精讲/针对性再练已有实现。练习与精讲的人工验收、异常浏览器矩阵以及自然长资料的整体质量尚待完成。PRD 1.4 的“尚未实现 Weakness”过时句已更正，不据此重复开发。

下一方向沿用已确认的“练习→学习资产/文字讲解→质量诊断/提示词管理→简历/模拟面试”，不按 PRD 中的模块优先级表误判本机交付状态。

| 依据 | 本地核验事实 | 对下一批的影响 |
| --- | --- | --- |
| document_processing/models.py RetrievalTrace | 有 owner、KB、query 摘要、策略字符串、阶段候选、最终 chunk、30天到期、retained_by_case；无 Query 正文及完整业务 source绑定 | 必须由领域读取器三重校验 owner/source/trace，不能凭 trace ID 授权正文 |
| learning/models.py LearningTurn | 有 question/answer/citations/trace_id、prompt_manifest；通用模式 trace_id 可为空 | 建议首批质量工单只绑定本人资料模式真实已完成 turn 且 trace_complete=true |
| practice / learning_assets models与worker | 有独立持久任务/不可变结果、manifest/trace_ids；无统一 AgentRun | 先落真实运行绑定适配，不能仅“扩展”不存在的 AgentRun |
| document_processing/retrieval.py | 当前关键词为 PostgreSQL FTS/ts_rank_cd；策略版本是固定字符串 | 不可将 FTS 标成 BM25；首批回放固定已记录策略，不宣称完整不可变策略注册表已有实现 |
| tests/test_retrieval_quality.py 与 evaluation.py | 指标函数和测试内同次Trace候选排序对照；Hybrid-only/No-Rerank现策略相同 | 缺可复用受控 replay服务；候选离线排序不证明因果，不伪造新模型负载耗时 |
| practice/generation.py | 当前 generate/regenerate使用真实Prompt片段、类型/题量驱动输出Schema、LangChain provider；manifest scene=practice_generate等 | 可以选已有 generate 场景作为首个受管场景，必须纳入动态Schema指纹 |
| learning/generation.py | 真实快速回答 agent=content_analyzer / scene=learning_quick_answer，流式协议 | 首批不强改流式问答Prompt接入，避免把流式结果误当统一JSON输出 |
| main.py / frontend/src/app | 当前没有 quality/prompt路由或对应管理员页面 | 两条新后端router、两个独立feature；main、导航、生成SDK由集成者统一编辑 |
| docs/ui-design/pen-prompts.md | 记录反馈56–58、诊断59–61、Prompt管理设计，但本轮未重新读取Pen | 页面实施前必须从Pen读取并校准实际版本；不能仅凭旧截图宣称设计验收 |

## 先冻结的公共契约（由主 agent 单独完成）

这是第一道串行关口。两条后端并行线从同一冻结提交建立 worktree，不各自定义一套契约。

1. **结果身份**：`source_type/source_id/owner_user_id/immutable_result_version/trace_ids/prompt_run_id`。首批质量类型建议为 `learning_turn`；由 learning 领域只读 adapter 检查 turn→conversation→user、状态、资料模式和完整 trace，并验证每个 trace.owner 与知识范围匹配。管理员调用不得绕过用户授权。删除/失效来源只返回不可用，不从备份或普通日志取回正文。没有完整Trace的通用问答不出现本期入口。
2. **Trace读取与回放**：定义 `TraceMetadata`、授权候选ID、解析/处理版本、策略版本和稳定 `TRACE_UNAVAILABLE/TRACE_INCOMPLETE/SOURCE_UNAVAILABLE`；字段白名单不含query/回答/原文。`ReplayRequest` 固定 case/grant/version 和 mode。首次只支持可证明的既有策略，FTS名称与实际算法一致；相同候选重排明确标注“离线对照”，不冒称因果或独立负载测量。来源不足与策略不能复原时明确不可回放。
3. **实际场景注册**：建议首个 `question_generator/practice_generate`，复用当前生成执行器与五型题Schema。schema随题位变化时，稳定场景契约hash与本次实例schema hash均记录；保留既有manifest key用于历史读取。工具allowlist在代码固定，不能由Prompt扩大。其余plan/grade/知识精讲/流式问答暂仍使用现有实现，不预建空模板。
4. **运行快照**：新增最小 AgentRun 与业务run关联，字段依据原prompt设计；任务入队短事务固定Prompt根版本/依赖hash、model参数、输入引用和context来源。worker只消费快照，重试不重新解析活动版本。prompt发布、停用、回滚不改变旧pending/processing任务。新受管任务无有效活动版本时返回稳定不可用错误；不静默fallback硬编码。上线前须先以当前已批准Prompt建立草稿并完成显式评测/发布，不能伪造通过证据。
5. **迁移顺序**：核验迁移head `20261003_04` 后，由主agent分配单一串行链：公共运行/必要Trace关系→quality表→prompt表。两个agent提交迁移草稿，由主agent整理revision/down_revision，禁止各自产生冲突head。无业务库迁移直到按项目规则完成目标核对与可恢复备份。
6. **响应与SDK**：Pydantic为事实源，现有ApiResponse/PageResponse/ApiError/HTTP状态规则不变。接口冻结后先通过真实curl权限矩阵，再一次性导出OpenAPI/生成SDK并提供同一冻结提交给前端，不手写DTO。
7. **敏感访问与运维**：quality grant加密快照与prompt管理员正文no-store使用不同权限检查，统一无正文审计字段。quality 30天授权、关闭立即拒读、7天物理清理宽限、90/180天元数据规则沿用已有规格。加密密钥通过Settings注入并明确轮换key_id；合成评测不调用生产数据，不在保存草稿时自动调用模型。

## 可落地的最小交付与文件归属

两条功能仍各自包含后端与页面，最终分别验收，不能用空表/假按钮当成完成。

| worktree/负责人 | 最小交付 | 独占文件 | 前置与验收 |
| --- | --- | --- | --- |
| next-quality-backend / Q | 资料问答turn工单：创建/幂等、本人列表详情补充、基础/追加授权、撤销/到期、未领取撤回；管理员队列/领取/状态/公开回复与内部备注隔离、脱敏概览/Trace/受控回放；加密快照清理 | backend/src/xuemian_ai/ai_quality/**、api/ai_quality.py、专属tests、quality OpenSpec | 公共结果/Trace/审计契约；实库跨用户/跨工单/角色/撤销竞态/保留清理全绿。只做定义好的业务source，不加附件/下载/全文搜索 |
| next-prompt-backend / P | 首个真实generate场景：注册校验、定义/不可变版本依赖、草稿编辑/Diff/合成预览、固定合成评测与指纹、发布/回滚新版本/停用/审计；run启动快照与实际generate接入 | backend/src/xuemian_ai/prompt_management/**、api/prompts.py、专属tests、prompt OpenSpec；practice接入由主agent承担 | 注册/运行契约；实库并发发布、旧任务/历史版本不漂移、陈旧评测拒发、普通用户正文拒读、no-store。真实模型评测由管理员显式发起，需真实报告 |
| next-quality-ui / Q-UI | Pen56–61的反馈入口/非默认勾选单次授权、我的工单/详情、管理员概览/队列/链路与回放，禁止正文导出 | frontend/src/features/ai-quality/**，质量路由page文件 | API/SDK与Pen读取校准完成后并行；浏览器两个用户+管理员权限矩阵、grant撤销缓存清理、公开/内部隔离 |
| next-prompt-ui / P-UI | Pen Prompt列表/版本详情、编辑/Diff/预览/评测/发布/回滚/停用及审计 | frontend/src/features/prompt-management/**，Prompt管理路由page文件 | API/SDK与Pen校准；普通用户不可读正文、no-store、不持久化Prompt；状态冲突保留草稿，真实任务快照显示不含正文 |
| next-integration / 主agent | 公共adapter/注册run、迁移链、Settings、main/router注册、现有learning入口与practice worker接入、导航、SDK、Compose/worker运行配置、总体docs/evidence | shared、learning/**与practice接入、migrations、core/config、main、generated/openapi、app导航及共享组件 | 审计各接口边界，四树合入独立集成分支；全库Ruff/mypy/pytest/Oxfmt/Oxlint/TS/Vitest/contract/compose与用户授权构建；真curl+隔离浏览器闭环 |

并行顺序：公共契约提交→Q/P后端同时开始；生成SDK冻结提交后→两路前端同时开始（可与后端余下内部实现并行）。公共main/Settings/SDK/迁移/导航由主agent处理。质量模块仅读取run/version引用，不依赖Prompt后台全部完成；未知旧Prompt版本显示既有manifest来源，不伪造数据库版本。

## 既有规格是否足够直接实施

两份原规格已给出主要产品规则、角色、授权期限、状态机、不可变版本/回滚语义和API路径，不需要重新询问这些已确认规则。证据与部分依赖文字仍停留在2026-08-30；已实现业务Agent/Trace存在，不能继续照旧写“无真实场景”。但尚缺上述本机契约适配、分期边界、迁移链、实际Pen复核与具体实施批准；当前不能不经这些关口直接开写两套完整功能。

需要用户批准的产品选择只有本期边界：是否先交付“本人资料问答且完整Trace”的质量工单，以及“练习generate”的提示词管理，之后再扩展其他AI结果/场景。推荐两者同批并行。若要求首批也支持通用问答、评分/精讲工单或全部Prompt场景，必须先补其trace/source/输出协议设计再批准，不自行猜测。

算法命名纠正为FTS、复用当前模型、hash结构、迁移revision、目录路径、事务/租约实现均为可由AI处理的技术选择；无须让用户决策基础实现细节。模型调用成本与真实上线仍须按既有明确执行方式控制；本轮在用户批准后实施这批功能，主工作区和上一批交付保持原样。
