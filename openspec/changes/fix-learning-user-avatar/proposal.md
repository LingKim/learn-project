# 修复学习室用户头像不显示

## 问题与证据

用户已设置个人头像，但会话消息中的用户头像未变化。LearningPage的data-message-role=user区域直接渲染UserRound默认图标，未接入个人资料头像。临时诊断组件测试为QueryClient预置avatar_set=true及头像Blob，打开真实LearningPage历史会话后，用户消息区域img断言失败（expected null not to be null）。临时测试已删除，业务代码未修改。

## 待用户批准的修复范围

- 现有用户消息头像位置显示当前账号设置的头像，复用userProfileQueryOptions/userAvatarQueryOptions及鉴权Blob接口。
- 上传或更换头像后，通过现有缓存失效机制同步；历史消息与新消息都显示当前头像。
- 没有头像、读取失败或删除头像时显示现有默认图标。
- 保持现有圆形尺寸、位置和布局，不增加会话侧栏头像或其他入口，不修改AI头像，不修改后端接口。

## 流程澄清

用户明确澄清Bug修复不需要OpenSpec或方案审批，本Bug直接修复；此文档作为已编写的诊断记录保留。删除“同意并继续”的独立方案未在本次头像修复中实施。
