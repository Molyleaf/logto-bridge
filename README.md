# Logto Bridge Gateway 🚀

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100.0+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[简体中文 (Simplified Chinese)](README.zh_CN.md) | English

`Logto Bridge Gateway` is a **lightweight, highly concurrent, and highly available** HTTP bridge gateway specifically customized for [Logto](https://logto.io). 

It bridges standardized HTTP Webhook requests emitted by Logto to destination service APIs, enabling seamless integration with domestic SMS service providers (such as **Alibaba Cloud DYPNSAPI**) and ensuring high-reliability email delivery using a **load-balanced SMTP pool with automatic failover**.

---

## 🎯 Key Features

*   **⚡ Asynchronous High-Concurrency Core**: Built on **FastAPI and Uvicorn**. Leveraging `aiosmtplib` for asynchronous email delivery and using `asyncio.to_thread` for threadpool-isolated execution of synchronous Alibaba Cloud SDK calls to keep the asyncio event loop unblocked.
*   **💬 Alibaba Cloud DYPNSAPI SMS Integration**: Fully integrates Alibaba Cloud's **Number Authentication Service (DYPNSAPI)** using the `SendSmsVerifyCode` interface, directly passing Logto's generated verification codes, converting expiration timings, and masking phone numbers in logs.
*   **✉️ SMTP Load Balancing & Failover**: Configures a list of multiple SMTP accounts. Emails are sent using a thread-safe **Round-Robin** algorithm. If a mailer encounters a timeout, rate limit, or auth failure, it **silently fails over** to the next available account in the pool, only raising an error if all servers fail.
*   **🎨 Premium Responsive Bilingual Email Templates**: Dynamically renders HTML emails using the Jinja2 engine. Follows modern responsive email design rules (within 600px, inline CSS, navy blue gradients `#0A192F` -> `#172A45`, and elegant cards). It automatically serves **English (en) or Chinese (zh-CN)** templates based on Logto's `locale` parameter, with graceful fallback to default templates if a specific workflow template is missing.
*   **🔒 Strict Security & Privacy Sanitization**:
    *   **Access Control**: All endpoints enforce `Authorization: Bearer <Token>` or `X-Bridge-Token` headers.
    *   **Data Masking**: Strictly sanitizes logs, preventing verification codes, invite links, SMTP passwords, and plain email addresses/phone numbers from being written into files or stdout.
*   **🛠️ Graceful Disaster Recovery (`always_return_2xx`)**: If target external services fail completely (e.g. Alibaba Cloud balance run-out, or all SMTP servers down), this option forces the gateway to return `2xx OK` to Logto, avoiding disruptive frontend error popups and protecting the end-user authentication experience.

---

## 📐 Architecture & Data Flow Topology

Here is the core architecture and data flow of `Logto Bridge Gateway`:

```mermaid
graph TD
    subgraph Logto Platform
        L[Logto Core Service]
    end

    subgraph Logto Bridge Gateway (FastAPI)
        Auth[Security Dependency layer verify_api_token]
        Router[Router Layer]
        SMS_C[AliCloud SMS Client]
        Mail_C[SMTP Load-Balanced Dispatcher]
        Jinja[Jinja2 Template Engine]
        
        L -->|1. HTTP Webhook Request| Auth
        Auth -->|2. Token Verified| Router
        
        Router -->|3a. POST /api/sms| SMS_C
        Router -->|3b. POST /api/email| Jinja
        Jinja -->|4. Render HTML| Mail_C
    end

    subgraph Third-Party Providers
        Ali[Alibaba Cloud DYPNSAPI SMS]
        SMTP_Pool[SMTP Server Pool]
        SMTP1[SMTP Account A]
        SMTP2[SMTP Account B]
        SMTP3[SMTP Account C]
        
        SMS_C -->|5a. Threadpool Call| Ali
        Mail_C -->|5b. Round-Robin Dispatch| SMTP_Pool
        SMTP_Pool -.-> SMTP1
        SMTP_Pool -.-> SMTP2
        SMTP_Pool -.-> SMTP3
    end

    subgraph End Users
        User_Phone[End User Mobile]
        User_Email[End User Mailbox]
        
        Ali -->|6a. Deliver SMS| User_Phone
        SMTP_Pool -->|6b. Send Beautiful Email| User_Email
    end
    
    style Auth fill:#f9f,stroke:#333,stroke-width:2px
    style Router fill:#bbf,stroke:#333,stroke-width:2px
    style SMTP_Pool fill:#dfd,stroke:#333,stroke-width:2px
```

---

## 📂 Directory Layout

```text
logto-bridge/
├── app/
│   ├── __init__.py
│   ├── server.py             # FastAPI instance, lifespan management, and healthcheck
│   ├── api/                  # API routing & security dependency
│   │   ├── deps.py           # Authorization header token verification (verify_api_token)
│   │   ├── email.py          # Email webhook endpoint, rendering and round-robin dispatch
│   │   └── sms.py            # SMS webhook endpoint, converting and forwarding to AliCloud
│   ├── core/                 # Core utilities
│   │   ├── config.py         # Configuration settings & environment variable overrides (Pydantic v2)
│   │   └── logging.py        # Global log formats for centralized observability
│   ├── integrations/         # Service integrations
│   │   ├── email.py          # SMTP Round-Robin and Failover delivery logic
│   │   └── sms.py            # Alibaba Cloud SDK threadpool-isolated wrapper
│   └── templates/            # Multi-language HTML email templates
│       ├── zh-CN/            # Simplified Chinese templates (SignIn.html, Register.html etc.)
│       └── en/               # English templates
├── config/
│   ├── config.toml           # Production configuration file (copy from config.example.toml)
│   └── config.example.toml   # Template configuration file
├── tests/                    # Unit and integration test suites
├── Dockerfile                # Lightweight multi-stage Docker build config
├── docker-compose.yml        # Docker Compose orchestrator
├── pyproject.toml            # Python packaging and dependency config (PEP 621)
└── AGENTS.md                 # Development guidelines and coding contracts for AI/Agents
```

---

## 🚀 Quick Start

### Option 1: Using `uv` Package Manager (Recommended)

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/molyleaf/logto-bridge.git
    cd logto-bridge
    ```

2.  **Create Virtual Environment & Install Dependencies**:
    ```bash
    uv venv --python 3.12
    # Activate virtualenv (Windows)
    .venv\Scripts\activate
    # Activate virtualenv (Linux/macOS)
    source .venv/bin/activate
    
    # Install dependencies with dev options
    uv pip install -e ".[dev]"
    ```

3.  **Prepare the Config File**:
    Copy the example TOML file and configure your credentials:
    ```bash
    cp config/config.example.toml config/config.toml
    ```

4.  **Run Development Server**:
    ```bash
    uvicorn app.server:app --reload --port 8000
    ```
    Access interactive Swagger docs at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

### Option 2: Using Standard `pip`

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    pip install -e ".[dev]"
    ```
2.  **Start Server**:
    ```bash
    uvicorn app.server:app --port 8000
    ```

---

### Option 3: Using Docker & Docker Compose (Production Environment)

To guarantee secret credentials safety, the TOML config file is not packaged into the Docker image but is either mounted or overridden by environment variables.

1.  **Build and Start Containers**:
    ```bash
    docker-compose up -d --build
    ```

2.  **View Logs**:
    ```bash
    docker-compose logs -f logto-bridge
    ```

3.  **Health Check**:
    Verifies container status using the lightweight endpoint `/healthz`:
    ```bash
    curl http://localhost:8000/healthz
    ```

---

## 🛠️ Configuration Settings

Modify all settings in `config/config.toml`. Here are the core settings:

```toml
# ==============================================================================
# Logto Bridge Production Configuration
# ==============================================================================

# Authorization secret token. Requests must match this via Bearer or X-Bridge-Token
api_token = "your-extremely-secure-api-token-here"

# Alibaba Cloud Number Authentication Service (DYPNSAPI) SMS config
[sms.alicloud]
access_key_id = "LTAI5tXxxxxxxxxxxxxxxxxx"
access_key_secret = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
endpoint = "dypnsapi.aliyuncs.com"
sign_name = "My App Name" # Must match approved signature in AliCloud console
template_code = "SMS_200000000" # Approved template code
code_length = 6 # Verification code length (4-8)
valid_time = 300 # Expiration time in seconds (5 minutes)
always_return_2xx = false # Force return 200 to Logto even if delivery fails

# Global email settings
[email]
always_return_2xx = false # Force return 200 to Logto even if all SMTP mailers fail

# Load-balanced SMTP accounts
[[email.smtp_accounts]]
host = "smtp.primary-email.com"
port = 465
username = "sender1@primary-email.com"
password = "primary_smtp_password"
use_tls = true
sender_email = "security@primary-email.com"
sender_name = "Security Center"

[[email.smtp_accounts]]
host = "smtp.backup-email.com"
port = 587
username = "sender2@backup-email.com"
password = "backup_smtp_password"
use_tls = false # StartTLS
sender_email = "no-reply@backup-email.com"
sender_name = "System Notification"
```

### 💡 Environment Variable Overrides

For secure deployments (e.g. in Kubernetes/Docker), configurations can be overridden with high-priority environment variables:

*   `BRIDGE_API_TOKEN`: Overrides `api_token` setting.
*   `BRIDGE_SMS_ACCESS_KEY_ID`: Overrides `sms.alicloud.access_key_id`.
*   `BRIDGE_SMS_ACCESS_KEY_SECRET`: Overrides `sms.alicloud.access_key_secret`.

---

## 📖 API Contract Specifications

### 1. Authorization Header
All endpoints require a matching key. Pass it using either:

*   Option 1: `Authorization: Bearer <api_token>` (Recommended)
*   Option 2: `X-Bridge-Token: <api_token>`

---

### 2. SMS Gateway Endpoint: `POST /api/sms`

Expected payload pushed by Logto's SMS webhook connector:

*   **Request JSON**:
    ```json
    {
      "to": "+8613800138000",
      "type": "SignIn",
      "payload": {
        "code": "837492",
        "locale": "zh-CN"
      },
      "ip": "192.168.1.100"
    }
    ```

*   **Success Response (200 OK)**:
    ```json
    {
      "status": "success",
      "message": "SMS sent successfully via AliCloud",
      "requestId": "908C86EF-4F58-5BE8-BD79-DFD111667EA5"
    }
    ```

---

### 3. Email Gateway Endpoint: `POST /api/email`

Expected payload pushed by Logto's Email webhook connector:

*   **Request JSON**:
    ```json
    {
      "to": "user@example.com",
      "type": "Register",
      "payload": {
        "code": "482094",
        "locale": "en",
        "link": "https://auth.example.com/verify?token=xyz"
      },
      "ip": "192.168.1.100"
    }
    ```

*   **Success Response (200 OK)**:
    ```json
    {
      "status": "success",
      "message": "Email rendered and sent successfully via load-balanced SMTP pool"
    }
    ```

---

## 🎨 HTML Email Template Matrix

Supported authentication workflows stored in `app/templates/{locale}/{type}.html`:

| `type` Flow Name | Chinese Subject | English Subject | Description |
| :--- | :--- | :--- | :--- |
| `SignIn` | 登录身份验证码 | Sign In Verification Code | Direct sign-in or multi-factor confirmation |
| `Register` | 欢迎注册 - 身份验证码 | Welcome - Registration Verification Code | Registering a new account |
| `ForgotPassword` | 重置密码 - 验证安全码 | Reset Password Verification Code | Resetting or changing user passwords |
| `OrganizationInvitation` | 您已获邀加入组织 | Organization Invitation | Organization invite containing `link` parameter |
| `BindNewIdentifier` | 绑定新账号 - 验证安全码 | Bind New Identifier - Verification Code | Binding a new email or phone number |
| `MfaVerification` | 多因素身份验证 (MFA) - 验证安全码 | Multi-Factor Authentication (MFA) - Verification Code | Extra verification code for MFA challenge |
| `TestConnection` | Logto 邮件服务连接测试成功 | Logto Mail Connector Test Successful | Connection testing inside Logto admin panel |

> [!TIP]
> **Graceful Template Fallback**: If Logto requests a non-standard `type` flow, the gateway will silently fallback and render the `SignIn.html` template rather than throwing a `500` error, maximizing system availability.

---

## ⚖️ License

Distributed under the **MIT License**. See `LICENSE` for details.
