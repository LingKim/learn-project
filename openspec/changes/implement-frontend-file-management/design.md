# Design: 内容库前端与文件上传

## 页面与路由

- `/content`：知识库总览，提供分页列表、创建、重命名和删除入口。
- `/content/[knowledgeBaseId]`：知识库详情，提供文件搜索、状态筛选、分页、上传及文件操作。
- 根首页保留现有工程状态内容，并增加真实内容库入口；认证保护继续复用 `ProtectedRoute`。

## 数据访问边界

调用链统一为：

`页面/组件 → queries.ts/mutations.ts → api.ts → protocol.ts → generated SDK → FastAPI`

- `api.ts` 只返回已经统一解包的业务数据或 mutation 结果。
- 查询 key 由 `fileManagementKeys` 工厂维护。
- mutation 成功后按资源边界失效知识库或文件查询。
- Access Token 由认证模块的 `authenticatedAccessToken()` 提供，业务组件不直接读取令牌。

## 上传状态机

1. 创建上传会话并携带 `Idempotency-Key`。
2. `single`：向预签名 URL 执行一次 `PUT`，再提交完成。
3. `multipart`：按 `part_size` 切片；使用按需签名的分片 URL 上传，收集响应 `ETag` 后提交完成。
4. 当前 UI 不计算或发送客户端摘要，因此正常页面流程不会触发 `reuse`；若后端意外返回该模式，前端明确停止并提示重复文件需要处理，不自动替用户选择 `LINK`、`MOVE` 或 `CANCEL`。
5. 上传业务失败时尝试取消尚未完成的会话，保留原始 `ApiError` 供页面展示。

客户端摘要不是正式身份；本次不计算或依赖客户端 MD5/SHA-256。重复文件交互留待后续产品规格明确后实现。

## 交互与可访问性

- 复用 shadcn/ui 基础组件和 lucide-react 图标；表格在窄屏转为可横向滚动布局。
- 创建、重命名、移动使用明确标签的表单；删除必须先读取影响与短期 token，再由用户确认范围。
- 所有异步操作提供禁用、忙碌、错误和空状态；不渲染无后端能力的假操作。
- 下载通过用户点击后请求短期 URL，并在同一用户手势链中打开。

## 验证

- Vitest：feature API 解包与鉴权头、query key、上传 single/multipart、核心页面状态与操作。
- Playwright：隔离数据库与存储前缀下完成注册/登录、知识库 CRUD、真实小型 TXT 上传、文件重命名/移动/下载 URL 请求/删除。
- 质量门禁：format、lint/boundaries、typecheck、Vitest、OpenAPI check；按项目规则不运行 build。
