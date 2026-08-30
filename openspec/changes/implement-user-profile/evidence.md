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

- 尚未实现数据库迁移、文件 purpose、图片处理器、个人资料 API、前端页面或真实 Prompt 消费。
- 尚未执行 curl、后端/前端测试、浏览器验收、Next.js build 或 Docker build。
- 当前环境没有 OpenSpec CLI 可执行证据；本轮只能执行规格结构、Requirement/Scenario 数量、冲突词、尾随空白和 `git diff --check` 检查，不能冒充 strict validate。
