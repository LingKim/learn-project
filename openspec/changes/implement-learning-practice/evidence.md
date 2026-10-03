# Evidence：学习刷题练习第一版

日期：2026-10-03。用户已明确回复“确认方案 开始开发”。代码、文档与自动化验证已完成，本机运行和浏览器主要业务闭环已验证；完整视觉及用户人工验收未完成。未将未完成项归档为验收通过。

## 实现范围与设计

- 非限时、资料/通用模式，单选、多选、判断、简答、文本编程五型；默认 5 题、中等难度，允许 1–20 题。多选集合完全匹配；主观 confidence < 0.7 标记低置信度。
- 配置建议/候选确认 → 持久化异步生成 → 预览编辑/删除/重新生成 → 私有答案保存/逐题点评/再次作答 → 历史/报告/追加式重评。
- 保留旧 Pen 10–13，校准新稿 68–76。节点和截图见 design.md、`docs/ui-design/evidence/practice/`。已读取各页 Pen 渲染图；71/72 为 236px 题号栏并移除旧计时框。实际三模式文案已与 resolveInstances 读取的“刷题练习”对齐。
- Pen MCP Get 缓存 bounds 的 clipped 报告与渲染图不一致，此项不宣称零诊断。没有新增正式计时、Weakness、精讲、音频、笔记、计划、简历/JD、聊天附件、全局任务中心或新 AI 同意弹窗。

## 静态、契约及自动化

- FastAPI OpenAPI 为唯一 DTO 来源，最新 SDK 含 `profile_override_fields`，用于保留画像字段省略兜底与 null/[] 明确清空语义。前端通过 feature API / queryOptions / mutationOptions / 共享 ApiError 接入。
- 最终后端：Ruff format/check 全量通过；mypy 80 个源文件通过；普通 pytest **261 passed / 53 skipped / 1 warning**。warning 为既有本地 Qdrant payload index 无效提示。skip 包括需独立环境的集成测试，不能算通过。
- 独立隔离 PostgreSQL＋ASGI HTTP＋实际 PracticeWorker **22/22 passed**；执行 upgrade → downgrade `20261003_02` → upgrade。覆盖持久202、私有权限、幂等/presence、并发答案版本、配置PATCH后timestamp、推荐画像组合、取消/租约/迟到fencing、失败保留旧版、来源删除/移动/活动版本切换、普通重命名保持有效、无原文失效预览、主观202/低置信度、completed重评与反馈。
- 生成/上下文/评分/worker 定向测试 **65/65 passed**，包含总体正确与错误维度矛盾拒绝、代码运行声明、候选画像presence与固定来源快照检索。没有引入未批准的混合维度聚合公式或分数阈值。
- 最终前端 `pnpm check`：Oxfmt、API boundaries、type-aware Oxlint、TypeScript、Vitest **29文件/129 tests**、OpenAPI SDK一致性全部通过。覆盖五型控件、保存确认后提交、冲突保留输入/显式恢复、completed只读、刷新/断线寻址、画像presence和来源撤权cache清理。
- OpenSpec strict validate、Compose config 静态检查、git diff --check 通过。没有 Next.js build / Docker image build。

## 本机数据库与运行

- 执行前核对 `.env` 目标为 `localhost/xuemian_ai`，current=`20261003_02`，practice 表 0、用户 3。
- 备份 `.runtime/backups/xuemian_ai-before-practice-20261003T044233Z.dump`，155485 bytes、0600，pg_restore --list 包含 table data / alembic_version 且可读。
- 升级并读回 `20261003_03`、practice 表 9；升级时既有用户仍 3。随后创建专用合成验收账号，因此升级前计数不是当前用户总数。
- 最后源码修复后重载本项目受管 API（PID 7436）和 practice-worker（PID 7438），清单 `.runtime/processes.json`；未启停外部 PostgreSQL/Redis，未动其他worker。
- 真实 `/api/v1/health/ready` 返回 ready，PostgreSQL/Redis/RustFS up；浏览器在最新运行包上完成主观重评。
- 唯一隔离库 `xuemian_practice_a919bf080f7c_e2e` 已删除，保密env已删除并核验不存在；golden专用Qdrant collection已清理。业务库专用账号与合成练习保留供追溯，没有批量删除用户资料。

## 真实模型小型合成评测

仅合成资料及 SQL/事务问题；没有外发用户原件、凭据或私有资料。汇总可复查 `quality-metrics.json`，完整合成报告保留在 `/private/tmp/practice-four-format-quality*.json`。

| 版本 | 文件处理 | 五型整组有效结构 | 资料不足拒绝 | 主观点评 |
| --- | --- | --- | --- | --- |
| 初版 | 6/6 | 0/6 | 未形成分母 | 未验证 |
| 第二版 | 6/6 | 1/6 | 3/3 | 0/1 |
| 最新固定题位 v3 / 评分 v4 | 6/6 | 6/6组、30/30题 | 3/3 | 1/1 |

- TXT、MD、DOCX、原生/扫描/混合 PDF 共 6 文件，经真实 DocumentWorker、PG/Qdrant、OCR、embedding、rerank、Qwen。文件相关来源 Recall@5 **6/6**，当前来源定位 **6/6**，生成题目引用可定位 **30/30**。
- object storage 使用合成bytes fixture，本runner不证明RustFS上传完整闭环；Recall指相关文件命中，不代表穷尽各文件全部内容/所有页。
- 初版存在嵌套topics、字符串citation编号和联合Schema选错题型，严格门禁阻止发布；按服务器固定题位提供JSON Schema，未用自动类型纠正降低规则。初/二版失败分母保留，不能与最终版成功分母混算。
- 主观评分引用模型选择的 answer_spans 编号，由后端确定性重建quote/start/end；拒绝伪造证据、越界分数和代码已执行声明。模型confidence=1是自报值，不是校准概率。
- 最后门禁变更后重放最新已保存30题仍通过；已保存真实主观结果重放通过。真实浏览器又完成文本编程、简答和简答重评。
- 人工抽样20题核心答案有资料支持，但少数讲解补充资料外DML背景、派生伪代码；**引用可定位不等于全文语义支持**。小样本不证明生产成功率≥99%，未声称生产质量已全面验收。

## 真实HTTP与浏览器

使用 ego-browser 技能，唯一验收空间14、专用合成账号；没有接管或关闭用户其他页面。截图失败时仍复用原页面，没有另建空间。

- HTTP/worker实际闭环：plan202 → generate202 → 不可变revision → attempt → 保存 → 客观评分 → 刷新读取 → report → completed；`.runtime/practice-http-evidence.json`仅UUID/计数，无token或正文。初版HTTP生成失败没有抹去。
- 浏览器：学习入口 → 五型各1题配置 → 真实建议 → 明确原配置确认 → 五型生成预览；编辑文本编程评分规则，题集v1→v2；开始练习。
- 文本答案保存后刷新读回一致；五型均实际提交并得到点评。多选首次只选A判错0/10、原因漏选；再次作答选A+B产生答案v2、正确10/10，旧提交可追溯。
- 文本编程与简答真实模型点评均有准确回答证据位置；简答输入重评原因后追加点评v2，旧v1保留。
- 完成报告实际 **已提交5/5、已评分5/5、未提交0、50/50**（使用第二次多选答案），知识点注明样本不足；重新打开私有历史显示“第1次练习·已完成·5题”及查看报告入口。单题重新生成已创建题集v3，删除第5题又创建4题的题集v4；原已完成attempt保持v2的5题，历史报告刷新仍为5/5、50/50。
- 浏览器发现PATCH MissingGreenlet已修复并补真实HTTP回归。切题曾因等待h1（实际h2）超时，后续DOM与PATCH200证实切换成功，未误列为业务故障；切题保存错误现明确显示。
- 四宽度答题页DOM：375/768/1024/1440均无document/body横向溢出，1024/1440题号栏实测236px。结果 `docs/ui-design/evidence/practice/browser-responsive.json`。
- 已取得并查看桌面题目预览截图 `browser-processing-1440.png`（实际内容为生成后预览v1）。后续ego/CDP/连接浏览器截图均出现captureScreenshot超时，原生窗口读取异常耗时；**不宣称四宽度截图或逐页完整视觉通过**。font-family声明已核对，实际字体命中未核验。
- 资料来源失效、取消及全部异常分支已有自动化覆盖，未全部逐项进行真实浏览器操作。页面完整人工视觉、资料模式人工体验和最终用户人工验收仍待完成。

## 自审与交付边界

独立只读自审报告6项，已修复并回归：总体评分矛盾、画像省略/null、撤权原文cache、代码运行声明、普通重命名误失效、知识库新文件干扰固定快照。来源和版本保护没有因修复而放宽。

未commit / push / 创建PR。没有覆盖无关 `.gitignore` 本地改动。自动化、真实模型小样本、本机运行、浏览器主要业务、Pen稿及用户人工验收分别记录；不以HTTP200、worker存活或检查数量代替完整验收。
