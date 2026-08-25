# Design：认证入口前端页面

## 路由与组件边界

- `/login`：用户名、密码、记住账号；可跳转注册。
- `/register`：昵称、用户名、密码、确认密码；可返回登录。
- `/first-login/change-password`：最新 PRD 已取消该能力，必须删除路由、页面、表单与测试，不保留不可达入口。
- `src/features/auth` 持有认证页面壳、表单和纯校验规则；输入框、复选框、字段错误和密码输入等基础控件统一放在 `src/components/ui`，App Router 页面只负责元数据和装配。
- `Input`、`Checkbox`、`Label` 以 shadcn 官方 `new-york-v4` registry 为事实源；项目仅通过 `InputField`、`CheckboxField`、`PasswordField` 组合它们，不复刻官方基础组件。

## 视觉与响应式

- 桌面端沿用 Pen 的左右分栏：左侧浅沙色品牌叙事，右侧象牙白表单区。
- 移动端收拢为单列，保留品牌标识和关键说明，不隐藏任何表单能力。
- 使用现有主题 token、小圆角、细描边和单一暖黄强调色，不引入渐变、玻璃拟态或卡片套卡片。

## 表单与失败行为

- 用户名和昵称只校验必填，不擅自增加 PRD 未确认的字符集规则。
- 密码至少 8 位，并至少包含字母、数字、符号三类中的两类；确认密码必须一致。
- 错误与状态使用 `aria-live`，输入框关联字段错误，密码显隐按钮有可访问名称。
- 当前没有认证 OpenAPI 时，校验通过后明确提示“认证接口尚未接入”，不跳转到不存在的业务页面；后端契约就绪后由 `implement-authentication` 统一替换为真实提交和会话恢复。

## 契约与隐私

- 本轮不发送账号或密码，不写入 localStorage、日志或 URL。
- 后续必须先实现 FastAPI 认证契约、导出 OpenAPI 并重新生成 client，再接入真实提交。
