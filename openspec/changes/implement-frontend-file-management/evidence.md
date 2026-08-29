# Evidence: 内容库前端与文件管理联调

## 设计与组件准备

- 已通过 Pencil MCP 读取 `pencil-new.pen` 的 35–37 页面、图层结构和截图。
- `pnpm dlx shadcn@latest add dialog select table` 在沙箱网络失败；授权联网后 CLI 下载完成但长时间无输出、未写入项目，人工中止。
- 按 `frontend/AGENTS.md` 允许的故障回退，使用项目现有 `radix-ui` 与 shadcn 官方组件结构落盘 `Dialog`、`Select`、`Table`，未新增第三方 UI 协议层。

## 验证结果

- Pencil：读取并截图核对 35–37 页面；实现保留象牙白、阳光黄、浅沙色、细描边、小圆角和扁平信息层级。
- 浏览器视觉：`output/playwright/file-management-overview.png` 与 `file-management-detail.png` 在 1280×720 下无裁切、塌陷或横向溢出。
- 前端全量 `pnpm check`：format、boundaries/Oxlint、TypeScript、Vitest、OpenAPI check 全部通过；11 个测试文件、39 个测试通过。
- 后端全量：Ruff format/check、mypy 通过；pytest 63 个测试通过。
- 隔离 E2E：`./scripts/run-file-e2e.sh` 最终 1/1 通过，覆盖注册、知识库创建/重命名/删除、真实 TXT 上传与 worker 校验、文件重命名、下载授权、跨知识库移动和删除。
- E2E 使用 `_e2e` 数据库、唯一 RustFS buckets、独立 Redis key 前缀和独立 worker；最终运行无 `NoSuchBucket` 或清理警告，退出时清理文件表、认证数据和临时 buckets。
- 本地联调 CORS 回归：开发环境同时允许 `http://localhost:3000` 与 `http://127.0.0.1:3000`，并已重新执行 `uv run xuemian-ai-init-storage` 幂等更新 4 个 RustFS buckets。
- 真实浏览器复验：从 `http://127.0.0.1:3000` 上传 48 B TXT，RustFS PUT、上传完成确认与 worker 校验均成功，文件进入“已上传·待解析”；随后已删除临时验收文件。
- 配置回归测试：`test_settings_parse_multiple_allowed_origins` 覆盖逗号分隔和空格清理；相关 pytest 14 个测试、Ruff 与 mypy 均通过。
- API 文档代理回归：Swagger 与 ReDoc 使用相对 `./openapi.json`，同时兼容后端直连和 `/api/backend/*` 代理；代理 schema 返回 HTTP 200，新增 2 个回归测试并通过 Ruff、mypy。

## 未验证与边界

- 按项目规则未运行 Next.js build 或 Docker image build。
- 本轮 E2E 使用小型 TXT 验证 single 上传；multipart 由 Vitest 覆盖分片签名、PUT、ETag 与完成提交，未再用浏览器上传大于 20 MB 文件。
- Pencil 中的解析、重新解析、恢复、永久清理和内容引用详情没有后端接口，本轮未实现。
- 客户端不计算摘要，正常 UI 不触发 `reuse`；重复文件 `LINK` / `MOVE` / `CANCEL` 需要后续产品交互规格。
