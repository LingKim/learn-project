# Proposal: 实现内容库前端与文件管理联调

## 背景

文件管理后端已经提供知识库、上传会话、文件列表、重命名、移动、下载和删除影响确认接口，但前端仍停留在工程状态页，用户无法通过产品界面使用这些能力。Pencil 的 35–37 页面给出了内容库视觉与交互基线。

## 目标

- 按 Pencil 35–37 的象牙白、阳光黄、浅沙色、细描边信息架构实现内容库页面。
- 通过 feature API、TanStack Query options、统一协议层和 generated SDK 对接现有后端。
- 支持知识库创建、重命名、删除，文件查询、上传、重命名、移动、下载和删除。
- 为真实联调补充 Vitest 与隔离 Playwright E2E，覆盖核心增删改查闭环。

## 非目标

- 不实现后端尚未提供的解析、重新解析、恢复、永久清理或内容引用详情。
- 不新增或手写一套与 OpenAPI 重复的 TypeScript DTO。
- 不修改 Pencil 设计稿，不实现管理员文件策略页面。
- 不执行 Next.js build 或 Docker image build。

## 风险与约束

- 文件后端当前仍是工作区未提交改动，本 change 在其 OpenAPI 契约上继续开发，不改写其历史归属。
- 预签名上传 URL 指向对象存储，不属于业务 API；仅上传传输层允许直接 `PUT`，所有业务请求仍必须经过 generated SDK。
- Pencil 中的“可用/解析中/失败/恢复”状态超出当前后端范围，页面只展示真实的 `processing_status` / `validation_status`，上传完成显示“已上传·待解析”。
