# 设计与契约

全局框架：桌面默认64px左侧图标栏，40px交互目标，顶部品牌、业务导航，中间留白，底部任务/通知/设置/账号。tooltip支持hover和focus，禁用项说明尚未开放，当前项背景与aria-current。不以展开侧栏遮挡历史列表。顶部模式56px，两者使用同一导航项。学习工作区使用框架提供的可用高度，不再写死76px；历史312px保留。学习内部模式能力保持不变。

设置使用现有Dialog及新官方Tooltip，设置入口独立于个人资料。两种布局单选，保存按钮；成功后更新共享profile Query缓存、即刻改变框架且保留会话与草稿，失败保留原布局，冲突刷新资料后提示重试。账号偏好通过现有GET/PATCH /api/v1/users/me/profile：增加navigation_position必填响应枚举left|top，默认left；PATCH可省略、显式null/其他值拒绝，沿用version乐观锁。新增user_profiles列String(8) NOT NULL DEFAULT left及CHECK，历史记录回填left。不重复定义前端DTO，不用localStorage存事实源。

迁移仅本项目业务库：核对.env目标与Alembic current/head，受限权限可恢复pg_dump备份后upgrade head，读回版本/列。不管理外部数据库或Redis。OpenAPI由后端导出再生成SDK。无build、无Git提交。

## 实施与设计依据

Pen新增节点uV9HB（左侧默认）、S7y7V（顶部备选）、MIB0l（用户设置），保留原稿；截图导出至docs/ui-design/evidence/navigation-redesign。设计在代码实现前完成，用户设置随后按真实Dialog补齐居中呈现。ui-ux-pro-max已运行design-system与Next.js搜索，采用稳定hover、SVG图标、键盘focus等建议；儿童字体/靛蓝及落地页布局建议不适用于现有产品，沿用既有暖色设计系统。

Tooltip通过项目固定shadcn CLI添加，首次沙箱DNS失败后联网成功；修正registry生成的cn导入为项目已有@/lib/utils并移除无用cn依赖。禁用导航以aria-disabled=true保留键盘可发现性，点击无业务动作，tooltip说明尚未开放。全屏删除Dialog覆盖窗口，消除旧76px偏移，保留既有删除范围和确认令牌机制。
