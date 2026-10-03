# Evidence：既有学习闭环可靠性修复

2026-10-03。先核验本地仓库、报告拆分，再按用户授权开启三个独立 worktree agent。修复依据已批准的练习与学习资产行为，不将下一批新功能当作已获批准。用户允许必要本地提交，禁止push/PR/部署和覆盖主工作区。

## 交付与复现

| 责任线 | 已复现缺陷与修复 | 证据 |
| --- | --- | --- |
| practice | fail_run忽略执行器retryable=false；现取执行器意图与既有业务禁令的交集 | 修复前真实service回归False变True；5项矩阵、2项实库retry回归 |
| assets | 历史任意digest去重使来源恢复后不追加可用结论；现只与最新记录去重，摘要形成确定前驱链 | 修复前预期3版实际2版；新链/旧摘要、4次往返、连续重放及真实PostgreSQL唯一约束验证 |
| ui | 提交等待期间漏保存新草稿、flush提前结束、练习/精讲旧run恢复、来源404/409原文缓存残留 | agent先运行失败回归再修复，覆盖服务确认版本、路由/owner恢复、失效cache |
| ui二次自审 | 卸载后的迟到响应仍可跳转/继续提交，正常自身URL更新被误失活、卸载且继续编辑后flush循环 | 独立reviewer逐项复核并反馈，新增deferred回归后修复；不新增业务操作或页面规则 |
| integration | 全局QueryClient跨账号复用私有缓存；现AuthProvider在外层，按status/user.id更换业务client与页面生命周期 | 初次账号切换/迟到查询两项回归均失败；修复后账号切换、退出、迟到查询、StrictMode4项通过，独立provider依赖复核通过 |

未新增迁移、API或DTO。未改正常页面视觉设计；来源失效错误沿用现有样式，但错误展示位置从关闭的弹窗移至来源区，未重新做Pen视觉验收。

## 最终验证结果

| 检查 | 实际结果 | 边界 |
| --- | --- | --- |
| 后端全库pytest，开启本次assets/practice隔离库 | 385 passed / 41 skipped / 1 warning，25.06秒 | 未启用部分文档/问答实基础设施和真实模型opt-in；Qdrant local payload index警告，不冒充server索引效果 |
| agent练习定向 | 78纯测试+24隔离库/HTTP通过 | 与全库有重叠，不能相加为唯一场景数量 |
| agent学习资产定向 | 95 passed / 4 skipped，8.81秒 | 4项真实模型opt-in未开启；合成资料与mock provider |
| 后端静态 | Ruff format158文件 / lint通过；mypy90source files通过 | 检查集成后代码 |
| 前端最终pnpm check与Next构建 | 38文件 / 171 tests通过，6.02秒；Oxfmt163文件、Oxlint/API边界、TypeScript、SDK全过；Next16.3.2生产构建成功（11静态生成页） | 包含UI追加修复与集成者的4项账号隔离回归；构建不代表运行/部署 |
| FastAPI OpenAPI再导出 | 与仓库schema字节一致；前端生成SDK check通过 | 不创建另一套DTO |
| 后端构建 | uv build成功生成sdist与wheel | 产物位于任务.runtime/build/backend；不代表Docker镜像或部署 |
| Compose | 使用临时本树.env.example副本供env_file解析，config --quiet通过，随后副本删除 | 未启停任何容器或运行服务 |
| OpenSpec | 本期fix及quality/prompt三个变更strict validate通过 | 两份旧未来规格只纠正delta头/标点格式，解析通过不代表未来功能完成 |
| Git diff | diff --check通过 | 四个本轮worktree最终干净；主工作区仍仅原.gitignore修改 |

前端首次Next构建在sandbox中因Turbopack创建子进程绑定IPC端口返回EPERM；随后以用户构建授权在独立集成树重跑成功，IPC端口不属于应用服务部署。后端首次无隔离build依赖的尝试因无hatchling失败，改用任务私有uv缓存的隔离build环境成功。测试harness初次缺合成auth/API配置，补齐后全库通过；没有为这些环境配置问题修改业务代码。

## 隔离与保护

从main@57629ef建立4棵树：worktrees/assets、practice、ui、integration。主工作区始终为main@57629ef，原有.gitignore修改原样保留。没有重启现有backend/frontend/worker，没有迁移业务库，没有push/PR/部署。

三份独立一次性PostgreSQL库：xuemian_parallel_20261003_{assets,practice,integration}_test。每份真实upgrade head→downgrade20261003_03→upgrade20261003_04通过；全库/agent验证完成后已精确DROP并删除库名标记。测试只使用合成用户和数据，模型密钥为不具调用权限的占位值，真实模型opt-in关闭。安全审批拒绝初稿整进程环境序列化后，harness改为仅保存非敏感库名，凭据只在子进程内存中传递；未创建秘密环境JSON。

## 自审与剩余边界

主agent自审、交叉agent只读自审均已执行。发现的本轮具体遗漏已交回所属agent修正，最终无已知阻塞。源码/组件测试不是浏览器或用户人工验收。

来源往返实库测试使用合成processing version active/retired切换并触发再次投影，证明**来源恢复后再次投影会产生当前正确结论**；未新增来源生命周期主动触发投影，不能据此声称来源改变时历史复习立即自动刷新。

未做本轮真实模型/自然长资料质量评测、真实账号切换浏览器验收、完整异常矩阵、Pen像素/字体验收、Docker镜像构建或生产部署。已上线的旧本机进程仍运行旧main代码，只有独立集成分支包含本轮修复。

## 下一批方案

具体待批准方案见 [并行实施计划](../../../docs/development/parallel-next-batch-20261003.md) 与quality/prompt各自implementation-plan补充。真实FTS不能标成BM25，测试内离线排名对照不能冒充受控回放服务；不存在的统一AgentRun不能当作已经扩展。首批业务source与Prompt场景需明确批准，其他技术契约由AI冻结后才并行开发。原PRD过时Weakness实施状态已校正。


## 本地提交与工作树

共同路径前缀：`/Users/lilin/Documents/Codex/2026-10-03/task/worktrees/`。

| 分支 | 工作树 | 提交 |
| --- | --- | --- |
| codex/learn-practice-hardening | practice | 84af4d9700a199bb830f6a4c646e154aa19614a2 |
| codex/learn-assets-hardening | assets | e463c4b966562b44dccf86922dea14b9d566b47b |
| codex/learn-ui-recovery | ui | 7d432af7ff687ed95b8664d1054ce540101cb461、35dde8fb0bcb7bf8a8ef9b261527744fb02f5977 |
| codex/learn-integration-20261003 | integration | 全部功能分支保留merge历史；额外账号隔离1c17a43；最后追加交付文档提交 |

独立交叉review无已知阻塞，不替代浏览器、模型或人工验收。源码分支与worktree保留给用户审阅；没有自动合入main。
