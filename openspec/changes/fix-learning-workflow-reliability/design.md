# Design：并行修复边界

Base：`57629ef`，正确源仓库 `/Users/lilin/Desktop/AI系列/learn-project`。

| 分支 | 文件归属 |
| --- | --- |
| codex/learn-assets-hardening | backend learning_assets 与专属 tests |
| codex/learn-practice-hardening | backend practice 与专属 tests |
| codex/learn-ui-recovery | frontend features/practice、features/learning-assets 与对应 tests |
| codex/learn-integration-20261003 | 合并、自审、共享文档和全库验证 |

工作树在本任务 `worktrees/{assets,practice,ui,integration}`。现有 OpenAPI、数据库 schema 和业务接口保持兼容；不重建 DTO。所有文件由所属 agent 修改，共享文件只有集成者处理。交叉自审补充的账号缓存隔离由主 agent 编辑 providers/query-provider、app/layout 和对应回归；AuthProvider 置于 QueryProvider 外层，按 status/user.id 更换 client 并清理退出会话的旧缓存。

不可重试修复保留既有错误白名单禁令，并与执行器 retryable 取交集。复习去重比较最新结果；追加版本摘要关联前一版本，避免来源恢复与历史摘要唯一约束冲突，不使用随机摘要、不改迁移。前端保存继续沿用串行队列和后端版本乐观锁，路由恢复沿用 owner/object 隔离边界，缓存清理只影响对应失效原文。

后端使用三份独立一次性 PostgreSQL 合成库，先升级→降级→升级验证。主库不参与测试。配置仅在子进程内存传递，不序列化进程环境、URL或秘密；本地 harness 文件只保存测试库名。前端集成树复制独立依赖，避免构建/缓存写到主工作区。测试与构建均在集成树执行。临时库最后精确清理，worktree/本地分支保留供复核。
