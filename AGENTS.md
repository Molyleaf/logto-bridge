# AGENTS.md — 本仓库 AI/Agent 全栈开发最高准则与规范

> 本文档是指导 AI/Agent 在本仓库进行开发、修改、重构的最高规范。所有通用 Python 开发约定均已转移至专属指南，各模块内部实现约束均已转移至对应文件的代码契约注释中。AI/Agent 在写/改本仓库的任何代码前，必须严格对齐本准则。

---

## 1. 核心技术栈与目录架构

本仓库是一个**纯粹、轻量级、高可靠性**的 HTTP 桥接服务网关（Logto Bridge）：
- **核心框架**：Python + FastAPI 异步框架 + Pydantic v2 + Uvicorn。
- **短信集成**：阿里云号码认证服务 SDK (`alibabacloud_dypnsapi20170525`)，调用 `SendSmsVerifyCode` 接口。
- **邮件集成**：基于 `aiosmtplib` 异步向配置好的多个 SMTP 账户进行负载均衡发送。
- **模板引擎**：Jinja2 模板，用于动态渲染极其精美、响应式的双语 HTML 验证邮件。
- **配置管理**：使用统一配置 Settings。官方配置模板为 `config/config.example.toml`，生产环境手动重命名为 `config/config.toml` 并挂载（不包含在 Docker 镜像内）。

### 目录指引与典型职责
- `app/core/`：包含配置加载 (`config.py`) 以及全局统一日志结构 (`logging.py`)。
- `app/integrations/`：包含三方 API 集成逻辑。
  - `sms.py`：封装阿里云短信发送逻辑。
  - `email.py`：实现 SMTP 轮询（Round-Robin）发送与故障自动转移（Failover）逻辑。
- `app/templates/`：存放多语言 HTML 邮件模板。
  - `app/templates/zh-CN/`：简体中文邮件模板。
  - `app/templates/en/`：英文邮件模板。
- `app/api/`：API 路由与安全网关层。
  - `deps.py`：全局安全依赖（X-Bridge-Token / Bearer 校验）。
  - `sms.py`：接收 Logto 短信请求并转发至阿里云服务。
  - `email.py`：接收 Logto 邮件请求、加载并渲染模板，再通过负载均衡 SMTP 投递。
- `app/server.py`：FastAPI 实例创建与全局事件监听、健康检查接口 (`/healthz`)。

---

## 2. 桥接器核心业务不变量（红线）

- **身份安全验证（Security Boundary）**：
  - 所有的 API 发送接口（如 `/api/sms` 和 `/api/email`）**必须**强校验配置中的 Bearer Token。
  - 请求头必须包含 `Authorization: Bearer <token>` 或 `X-Bridge-Token: <token>`，匹配失败必须拒绝服务并返回 `401 Unauthorized`。
  - **绝对禁止**公开暴露没有任何授权防护的短信或邮件投递接口。
- **自动容灾故障转移（Failover Invariant）**：
  - 邮件服务必须配置多个 SMTP 账户，并使用 **Round-Robin** 算法进行依次分发。
  - 若在发送过程中某一个 SMTP 节点抛出异常（网络连接超时、认证失败、频控限制等），必须**静默捕获该异常**，记录 Error 日志，并**立即尝试下一个可用的 SMTP 节点**，直到发送成功，或轮询完整池节点为止。
  - 只有在池中**所有**的 SMTP 账户均投递失败时，方可返回错误响应，以最大化保证 Logto 的用户注册与登录体验。
- **短信验证码传输规则**：
  - Logto 会自动在 `payload.code` 字段中生成数字验证码，桥接器应直接采用此验证码值。
  - 调用 `SendSmsVerifyCode` 时，需将该验证码转换后置于 `TemplateParam` 标准 JSON 中发送（如 `{"code":"123456"}`）。
- **隐私保护与日志脱敏（Observability & Sanitization）**：
  - 敏感信息（如 API Token、密码、数据库连接串、Logto 验证码 `code`、收件手机号的中间四位）**绝对禁止**记录至正常运行日志中，避免日志被攻击者窃取后发生越权。

---

## 3. 开发准则与最佳实践

### 3.1 Python 规范
所有 Python 代码的函数签名、异步边界、校验边界、错误处理与日志、以及 ACE 代码契约（`@ai-intent`, `@ai-invariant`, `@ai-boundary`, `@ai-directive`, `@ai-observe`, `@ai-context`）的标注格式，必须严格遵循专属指南：
👉 [Python 最佳实践与代码契约指南](file:///C:/Users/HenryHuang/.gemini/config/plugins/ace/skills/reference/python-guide.md)

### 3.2 邮件 UI 规范
- **响应式布局**：邮件的 HTML 模板必须适配 PC 端与主流移动端（iOS / Android Mail App），宽限制在 `600px` 内，使用内联样式。
- **设计美感**：必须告别简陋的默认邮件排版，使用渐变色 Header（深海蓝 `#0A192F` 到 `#172A45`），圆角卡片面板，大字体加粗验证码，并在页脚附上防欺诈安全提示及动态时间。

---

## 4. 关键开发命令

- Python 代码格式化：`ruff format .`
- Python 静态检查：`ruff check .`
- 单元/集成测试：`pytest`
