# Evidence：个人资料与默认画像

## 已确认事实

- 2026-08-30 用户确认需要普通用户主动上传头像并填写目标岗位、工作年限、目标岗位等级、技能/关注点和学习目标，作为题目、面试和学习计划的默认兜底画像。
- 当前后端 `User` 只有用户名、昵称、密码哈希、角色、状态、最后登录时间等账户字段，没有 `UserProfile` 表、头像字段、个人资料 API 或对应迁移。
- 当前前端没有个人资料业务路由，已有 Pen Prompt 04 只生成了“个人资料与默认偏好”概念页面，未覆盖头像、详细画像、活动薄弱点和乐观锁冲突状态。
- 当前文件用途只覆盖知识资料、简历、JD、真实/模拟面试录音，没有 `avatar` purpose；头像可以复用已交付的 `UploadSession`、`StoredObject`、`FileAsset`、RustFS 和异步清理基础设施，但不能创建 `KnowledgeBaseFile`。
- 当前系统识别薄弱点的 PRD 模型为独立 `Weakness`，包含来源、证据、严重程度、掌握状态和最后验证时间；把它复制进静态画像会丢失证据与时效。

## 已确认产品口径

- `UserProfile` 与 `User` 一对一；昵称仍属于 `User`，用户名只读，画像字段全部可选且不设置强制首次引导。
- 工作年限只保存月数，目标岗位等级为 `intern | junior | intermediate | senior | expert`。
- 本次任务显式输入优先于本次选择的简历/JD/薄弱点，再优先于默认画像和场景默认值；请求显式 `null` 禁止本次兜底。
- 单次任务值与模型推断不自动回写画像；只有用户明确选择“保存为默认画像”才更新。
- 头像支持 JPEG、PNG、WebP，默认最大 5 MB；服务端清除 EXIF 并生成统一方形 WebP，处理成功后才原子切换，失败保留旧头像。
- 管理员不能查看用户画像、头像或薄弱点；头像私有存储，数据库保存 FileAsset ID 而非签名 URL。

## 本轮变更

- PRD 已更新至 v0.10，新增个人资料与默认画像、头像生命周期、Prompt 注入优先级、来源快照、安全和验收口径。
- 新建 `implement-user-profile` Proposal、Design、Tasks、Evidence 以及 `user-profile`、`profile-avatar` 两份增量 Specification。
- `implement-prompt-management` 同步增加画像依赖、字段级来源解析、省略/null 语义、运行快照和禁止自动回写要求。
- Pen 记录新增 Prompt 07，但本轮没有操作 Pen 画布，发送状态与视觉核验状态必须保持“待发送/未核验”。

## 当前验证边界

- 已新增 `UserProfile` 模型与 `20260830_01` Alembic 迁移；迁移离线 SQL 已检查，并已从 `ac3e06160525` 实际升级项目当前 PostgreSQL 到 `20260830_01`。
- 已实现 `GET/PATCH /api/v1/users/me/profile`、头像上传会话/完成、私有读取与删除端点；活动薄弱点在领域尚未实现时稳定返回空集合。
- 已为现有上传会话和文件策略增加独立 `avatar` purpose；头像经 Pillow 真实解码、静态帧/尺寸/像素/超时限制、EXIF 方向修正、居中裁剪与 512×512 WebP 派生后才切换资料引用，不创建 `KnowledgeBaseFile`。
- Ruff、mypy、pytest 已通过；pytest 当前为 88 passed。头像单元测试覆盖 JPEG/PNG/WebP、动画 WebP、尺寸上限、方形输出、EXIF 清除和资料引用阻止误删。
- `scripts/run-profile-backend-smoke.sh` 已在隔离 `_e2e` 数据库与唯一 RustFS bucket 真实通过：未认证 401、空资料、规范化更新、陈旧版本 409、真实 PNG 上传、异步 WebP 转换、私有读取、删除及删除后 404；测试进程和隔离数据已清理。
- OpenAPI 快照和只读 generated client 已同步，`pnpm openapi:check` 通过。
- 尚未完成管理员/禁用/软删除账号的真实 curl 矩阵、并发头像切换、对象写入/清理故障注入与最大重试验证；因此相关权限矩阵、清理重试和交付任务保持未勾选。
- 已新增 `/profile` 受保护路由与“个人资料”导航，前端严格通过 `features/user-profile/api.ts -> queries.ts -> 页面` 接入 generated SDK；头像二进制也由 feature API 以 Bearer Token 获取，页面和 Query 未直接调用 generated SDK 或业务 `fetch`。
- 页面已覆盖昵称首字默认头像、真实头像预览、上传/更换/删除/处理中、失败保留旧头像，及用户名只读、岗位、年/月经验、岗位等级、技能标签、关注点标签、学习目标、默认语言、活动薄弱点只读空状态；修改密码、删除账号与强制首次引导未混入页面。
- 前端本轮执行 `pnpm lint`（含 API boundaries）、`pnpm typecheck`、`pnpm test`、`pnpm openapi:check`、`pnpm format:check` 均通过；Vitest 为 14 个测试文件、47 passed，新增覆盖年月换算、空经验、字段校验、头像类型/大小和 Query key/cache。
- `scripts/run-profile-e2e.sh` 已使用隔离 `_e2e` PostgreSQL、独立 Redis key 和本轮唯一 RustFS buckets 真实通过；Playwright 为 1 passed，覆盖注册、资料保存、刷新恢复、真实 PNG 上传、worker 转 WebP、私有头像读取、版本递增和删除，退出时已清理隔离数据与 buckets。
- Playwright 页面截图已保存到本地 `output/playwright/user-profile.png` 并完成桌面视觉检查；截图目录按项目规则不入 Git。Pen Prompt 07 仍未发送，47 号 Frame 仍未核验，因此不能把当前实现称为 Pen 像素级还原。
- 本轮未运行 Next.js build 或 Docker image build，未执行 commit/push；真实 Prompt 消费与 Weakness 领域仍未实现。
