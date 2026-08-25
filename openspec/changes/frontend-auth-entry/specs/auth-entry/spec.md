# auth-entry Specification

## 登录入口

### Requirement：用户名登录表单

系统 SHALL 在 `/login` 展示用户名与密码输入、记住账号选项、登录按钮和注册链接，且 SHALL NOT 展示手机号/邮箱登录或找回密码入口。

#### Scenario：缺少必填字段

- **WHEN** 用户在用户名或密码为空时提交
- **THEN** 页面在对应字段附近展示可访问错误，并保持已输入内容

## 注册入口

### Requirement：开放用户名注册表单

系统 SHALL 在 `/register` 展示昵称、唯一用户名、密码和确认密码；SHALL NOT 要求手机号、邮箱、验证码或协议页面。

#### Scenario：密码不符合规则

- **WHEN** 密码少于 8 位或只包含一类字符
- **THEN** 页面阻止提交并明确指出密码要求

#### Scenario：两次密码不一致

- **WHEN** 确认密码与密码不同
- **THEN** 页面在确认密码字段展示错误

## 已取消入口

### Requirement：不提供首次强制改密

系统 SHALL NOT 提供首次登录强制改密路由、临时密码表单或管理员重置密码入口。

#### Scenario：访问旧路由

- **WHEN** 用户访问 `/first-login/change-password`
- **THEN** 系统不得展示旧的强制改密页面

## 响应式与无障碍

### Requirement：键盘与移动端可用

登录和注册页面 SHALL 支持键盘操作、清晰焦点、字段错误关联、密码显隐可访问名称，并在窄屏保持全部关键功能。
