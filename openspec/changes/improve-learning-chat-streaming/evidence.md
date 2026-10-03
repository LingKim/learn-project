# 2026-10-03 学习会话修正验证

## 实现与自审

先更新 PRD/OpenSpec 并冻结 FastAPI SSE 契约，三个 subagent 按后端、聊天交互、Markdown/媒体并行，主 agent 生成 SDK、集成和验证；另做只读跨职责审查。AGENTS.md 已加入符合条件的并行开发规则。

发送同步产生右侧用户气泡及左侧 loading；Qwen qwen3.8-flash 的真实 astream 逐段解码 JSON answer 字段，最终严格校验才保存。失败清空临时正文，同 key 重试不重复消息，切换/卸载隔离迟到事件；阅读历史不抢滚动。反馈原本已接 LearningTurn.feedback，保留并改图标及 title/aria-label，选中可取消；这只是反馈记录，未实现模型训练/质量工单闭环。生成笔记尚未实现的入口移除。聊天语言控件与首次学习确认弹窗移除，不伪造 consent；默认回答语言复用个人资料 preferred_language，资料解析确认独立保留。

自审修复了重放准备后撤权仍返回旧引用、响应在首帧前断开留下 processing 租约两个边界；新增隔离测试验证。每次 delta 发布前短事务核验用户、会话、范围、资料活动版本与 lease；模型等待不持事务。已发送暂态无法物理撤回，失败时客户端清理且后端不保存它。

## 真实流式证据

测试仅使用唯一临时数据库、合成账号与合成 PostgreSQL 资料；真实千问未收到用户业务资料。

- 首次代理测试发现 content-encoding:gzip：202 段 delta 与 started/completed 均在 10.480s 集中到达；直连后端开始事件 0.011s、6 段 delta 在 1.531–1.894s 到达，证明代理缓冲。
- SSE 专属响应增加 Cache-Control: no-store, no-transform 后，Next 代理不再 gzip；started 0.025s，169 段 delta 在 3.512–11.602s 陆续到达，completed 11.840s。没有假逐字动画。
- 真实浏览器从立即用户/等待气泡到最终答案，MutationObserver 记录 346 次 DOM 变化、328 种正文长度，确认实际渐进渲染；发送后 dialog 数为 0。
- 合成账号设置 en-US 后省略请求 language，started/completed 均为 en；历史正文及 helpful 写入后读回一致，随后恢复中文。
- 资料模式有效问题：5 段 delta、1 个可用引用、trace_complete=true；不相关 Shor 算法问题：11 段 delta、refused=true、0 引用。仅是合成样例核验，不代表全场景生成质量评测。

## Markdown、媒体与设计

使用 react-markdown、remark-gfm、rehype-raw 与 rehype-sanitize：GFM 标题/列表/引用/任务/表格/代码，白名单图片、audio/video/source；拒危险 URL、脚本及任意 HTML。代码与表格局部横向滚动。图片 ![alt](url) 支持 Dialog 放大；带媒体后缀链接或白名单 audio/video 标签支持播放，不自动播放，preload=none。支持内容中的媒体资源渲染，没有新增附件上传或多模态生成业务。

临时纯合成媒体页在真实浏览器验证：390px 无横向溢出、图片 loaded=true，放大/关闭成功；视频和音频 controls=true、preload=none、autoplay=false，调用播放后 readyState=4、playing=true。图片使用 no-referrer，不附本应用 Authorization；原生外站媒体 Cookie 按浏览器自身策略处理。临时路由和资源已删除。

实际读取 Pen 的 ehMic/pvuuj 图层及截图；1440×960 桌面会话 DOM：顶栏 76、侧栏 312、顶部控制区 125（y76）、消息区 671（y201）、输入区 88（y872），textarea 48；滚动离底后回到底部按钮可见。用户右灰、AI 左淡黄，36px 头像/12px 间距、650/760px 内容宽及舒适 14px/28px 行高。图标按钮正文为空，title/aria-label 包含继续追问、有帮助、无帮助、复制回答。390/768/1440 三宽均无页面/消息区横向溢出。桌面最终实际截图见 [chat-desktop.png](screenshots/chat-desktop.png)。本轮更新替代旧稿的文字操作、语言控件和首问确认；不是对全部页面、字体命中或逐像素色差的验收。豆包仅只读参考初始界面，未读取历史正文或发送消息，不声称测过其后端。

## 自动化检查

- frontend pnpm check 全部通过：格式、API边界、Oxlint、TypeScript、Vitest **79 passed / 19 files**、OpenAPI client一致性。
- backend Ruff、mypy **66 source files** 通过；最终 pytest **137 passed / 25 skipped**。跳过项要求隔离数据库或真实模型环境，不计作通过；本地Qdrant的payload index警告属本地引擎限制。
- run_learning_checks.py 唯一隔离DB/collection **23 passed / 1 skipped**，包含新增9项流式/语言/撤权/取消/租约/重放测试；跳过真实模型专项由以上真实HTTP样例补充，仍不宣称该专项已运行。迁移升级/回退/升级仅在临时DB运行，本轮无业务库DDL。
- 最终相关后端 generation/SSE 单测 **21 passed**，包含 no-transform 专属头断言。
- OpenAPI重新导出、SDK重新生成，OpenSpec strict 与 git diff --check通过。
- 未运行 Next.js/Docker build，未 commit/push；用户人工验收待完成。

## 服务与清理

本地受管后端8000优雅重载为 PID 53226，live/ready 200，未登录 SSE 401；3000前端保持dev/HMR，其他worker与外部PostgreSQL/Redis/Qdrant/RustFS未启停。两个隔离serve环境均输出 DROP DATABASE 与 isolated resources cleaned，隔离集成DB亦已DROP，临时媒体资源移除，tsconfig测试include恢复，浏览器task9 finish完成。

## 后续用户验收补正

用户真实watch回答无换行，说明上述合法样例不覆盖全部模型输出。宽屏重复宽度限制也已修正；经用户授权清理指定坏历史，补生成约束/格式校验。见 [Markdown与边距补正](../fix-chat-markdown-and-gutters/evidence.md)。
