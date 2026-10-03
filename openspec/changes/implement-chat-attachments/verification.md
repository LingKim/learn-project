# 聊天附件验证记录（2026-10-03）

## 已验证

- PRD、proposal、design、tasks与capability delta已更新；OpenSpec strict validate通过。
- Pen 65/66/67分别覆盖已上传与加号菜单、拖拽、解析/错误状态。三稿结构检查无裁切问题；输入区附件在上、加号在左下、发送在右下，沿用暖色设计。
- 前端pnpm check通过：Oxfmt、API边界、Oxlint、TypeScript、96项Vitest、生成SDK一致性。
- 后端Ruff/mypy通过；全量pytest 186 passed / 31 skipped，local Qdrant有一条索引提示。最终Prompt v8补充后重新运行生成测试42 passed。
- 附件16项测试覆盖实际TXT/MD/Markdown/DOCX/PDF解析、受控扫描PDF OCR、真实图片格式/尺寸/动画/比例/元数据、文件大小、过期/绑定冲突和11MiB累计收包限额（含不可信/缺失Content-Length）。
- 业务库目标localhost/xuemian_ai，原版本20261003_01；迁移前完成pg_dump归档与pg_restore目录检查，备份位于/private/tmp/xuemian-attachments-backup-20261003-110758/xuemian_ai.dump。升级并读回20261003_02，附件表存在；未启停外部PostgreSQL/Redis/RustFS。
- 项目API重启运行新版本。浏览器合成账号attachment_20261003验证图文多选上传、发送前移除、DOM文件拖拽事件上传、解析完成及消息附件回显。
- 图片私有Blob读取成功（实际600px）；刷新后从会话列表重新打开，附件历史保留。
- 千问视觉模型首次真实调用发现json_schema兼容400，改用json_object并保留本地严格输出校验。页面失败重试成功，识别红色正方形、图中CODE7319、TXT项目代号SYNTHETIC-42、预算123万元；后续无新附件追问正确保留上下文并算出133万元。
- PDF/DOCX/.markdown实际多选上传并解析成功；空问题仅附件发送成功，后端补默认问题。
- 375/768/1024/1440宽度DOM核验无水平溢出，文本输入保持可用。

## 验证边界

- 31项跳过包含未设置显式隔离数据库/其他可选集成环境的测试；未把带全表清理fixture的集成测试直接运行到业务库。
- 真实外部模型只使用合成资料，未传用户截图/私人原件。扫描PDF OCR仅受控provider测试，本次未额外做真实OCR模型验收。
- 拖拽验收使用浏览器DataTransfer/DragEvent；未模拟Finder跨应用拖放。上传失败重试、6件上下文上限等由自动化测试覆盖。
- 未执行Next.js/Docker build。未执行本轮Git commit/push。人工产品验收待用户完成。

## 最终补充

- 文档模型json_schema兼容问题修复：所有有附件上下文的请求使用json_object，保留相同模型与本地严格校验。页面原失败轮次重试成功，准确读取DOCX-88、MD-77及PDF中PostgreSQL事务隔离防脏读主题，标题与正文正常分段。
- 长时页面上传发现原共享认证层使用过期access token，已依据AuthPayload.expires_in提前30秒single-flight刷新；并发刷新回归测试通过。前端最终96项通过。
- 响应式四宽度截图与桌面最终页面截图均已保存；Pen及输入框布局/附件chips/加号菜单已逐项核验。

- 最大10MiB合成PDF通过前端代理实际上传、解析和发送前移除，multipart开销未导致截断；最终保留同一ego验收空间页面供人工查看。
