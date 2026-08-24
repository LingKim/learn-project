# 学面通AI工程基线

本文记录脚手架阶段的稳定工程边界。详细变更规格位于 `openspec/changes/bootstrap-fullstack/`。

## 核心原则

1. 后端是业务规则与接口契约的唯一事实源，前端 client 从 OpenAPI 生成。
2. 后端采用模块化单体，只有真实业务出现时才创建对应模块。
3. LangGraph 用于显式业务状态机，不允许智能体自由互调；脚手架阶段不创建演示业务图。
4. 本机 PostgreSQL 与 Redis 是外部依赖，项目 Compose 不管理其生命周期。
5. 管理员、日志和健康检查均不得暴露用户业务正文或秘密。

## 当前边界

- 本期只有系统健康纵切，不代表 PRD 业务里程碑已经开始实现。
- PostgreSQL 暂不启用 pgvector；进入内容库与 RAG 开发前必须补充对应 OpenSpec。
- GitHub Actions、生产发布、云端域名与 TLS 不在本期范围内。

