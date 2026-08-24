# Backend AI Coding 规则

- 运行环境固定为 Python 3.12，依赖只能通过 `uv add` / `uv remove` 维护。
- FastAPI 路由只负责 HTTP 适配，不在路由函数中堆放业务规则。
- 新业务按模块组织；禁止建立全局巨型 `services.py` 或提前创建空模块。
- 配置统一通过 Pydantic Settings 注入；禁止读取散落的环境变量或写死秘密。
- API 错误遵循 RFC 9457，日志必须带 `request_id`，不得记录请求正文、凭据或用户业务内容。
- 后续开发业务接口必须复用 `core.responses`、`core.status_codes` 和 `core.errors` 中的统一响应、状态码枚举与项目异常体系；响应体 `code` 必须与真实 HTTP 状态码一致，禁止自行定义另一套响应格式或用 HTTP 200 包装失败。
- OpenAPI 是前后端契约唯一事实源；修改路由后同步导出 schema、生成前端 client 并更新测试。
- 使用 Ruff、mypy、pytest；默认不执行 Docker build。
