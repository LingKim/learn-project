# Tasks：统一后端结构化日志

- [x] 通过分轮需求拷问确认选型、公共 API、事件、隐私和验证边界
- [x] 调研 structlog、Loguru 与标准库 logging 的官方资料和项目适配性
- [x] 编写 Proposal、Design 与增量 Specification
- [x] 将 structlog 与标准库、Uvicorn 日志统一接入 ProcessorFormatter
- [x] 增加可配置日志级别、公共字段和稳定 logger 名
- [x] 封装 logger 获取、上下文绑定和清理能力，不复制日志级别 API
- [x] 校验外部 `X-Request-ID` 并保证请求上下文隔离和清理
- [x] 统一请求完成日志并关闭 Uvicorn access log
- [x] 让未知异常只记录一次安全 ERROR 日志
- [x] 为依赖探测失败增加脱敏 warning 日志
- [x] 增加递归敏感字段和自由文本凭据兜底脱敏
- [x] 增加应用启动与正常关闭日志
- [x] 更新环境变量示例、后端规则与工程文档
- [x] 补齐日志 schema、级别、上下文、脱敏、异常和标准库互操作测试
- [x] 执行 Ruff、mypy 和完整后端 pytest
- [x] 自审改动并记录实际证据与未验证项
