# Proposal：全栈工程脚手架

## 背景

项目已有 PRD v0.4 和 UI 设计验收记录，但尚无前后端源码、工程规范、接口契约或本地容器编排。后续三个业务里程碑需要一个可复用、可验证且不会提前固化业务错误抽象的工程基线。

## 目标

- 在当前目录建立 `frontend/` 和 `backend/` 两个工程目录，并由根目录统一治理。
- 建立 Next.js、FastAPI、OpenAPI 生成客户端、健康检查、结构化日志和本地 Docker Compose 基线。
- 复用本机已运行的 PostgreSQL 与 Redis；由 Compose 仅管理 frontend、backend 和 RustFS。
- 建立轻量 AI Coding 约束、OpenSpec、自动化质量命令和测试骨架。

## 非目标

- 不实现注册登录、知识库、RAG、模拟面试、笔记或管理员后台等业务功能。
- 不创建演示用 LangGraph 业务图；只验证 LangChain 与 LangGraph 依赖可导入。
- 本轮不启用 pgvector，不创建业务表，不运行 Next.js build 或 Docker image build。
- 不创建 GitHub Actions，不 commit，不 push，不创建远程仓库。

## 影响

- 新增根级工程治理、前后端源码、Docker Compose、开发命令和本地环境模板。
- 在既有 PostgreSQL 容器中提供显式、幂等的专属数据库初始化入口；该动作不得由普通启动命令隐式触发。
- RustFS 是本轮新增的唯一项目内基础设施服务。

