from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.server import app
from app.core.config import settings

client = TestClient(app)


def test_healthz():
    """
    测试健康检查端点无需安全凭证即可公开访问。
    """
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "logto-bridge"}


def test_auth_missing():
    """
    验证未携带 Token 时拒绝访问。
    """
    response = client.post("/api/sms", json={})
    assert response.status_code == 401
    assert "credentials are required" in response.json()["detail"]


def test_auth_invalid():
    """
    验证携带错误 Token 时拒绝访问。
    """
    headers = {"Authorization": "Bearer wrong_token_secret"}
    response = client.post("/api/sms", json={}, headers=headers)
    assert response.status_code == 401
    assert "Invalid or expired" in response.json()["detail"]


@patch("app.api.sms.sms_client.send_verify_code", new_callable=AsyncMock)
def test_sms_webhook_route(mock_send_verify_code):
    """
    测试 Logto 短信网关接收端路由解析、安全校验与外部投递对接。
    """
    # 模拟发送成功
    mock_send_verify_code.return_value = {
        "success": True,
        "request_id": "MOCK-ALI-REQ-101",
    }

    # 使用全局配置的 api_token 作为 Header
    headers = {"Authorization": f"Bearer {settings.api_token}"}

    payload = {
        "to": "+8618800001111",
        "type": "SignIn",
        "payload": {"code": "887766"},
        "ip": "10.0.0.5",
    }

    response = client.post("/api/sms", json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["requestId"] == "MOCK-ALI-REQ-101"

    # 校验调用参数
    mock_send_verify_code.assert_called_once_with(
        phone_number="+8618800001111", code="887766"
    )


@patch("app.api.email.email_dispatcher.send_email", new_callable=AsyncMock)
def test_email_webhook_route_zh(mock_send_email):
    """
    测试 Logto 邮件网关接收端路由解析，校验中文模板渲染和 SMTP 投递流程。
    """
    mock_send_email.return_value = True

    headers = {"X-Bridge-Token": settings.api_token}  # 使用自定义 X-Bridge-Token 头

    payload = {
        "to": "user@gmail.com",
        "type": "Register",
        "payload": {"code": "776655", "locale": "zh-CN"},
        "ip": "127.0.0.1",
    }

    response = client.post("/api/email", json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # 验证底层发信动作
    mock_send_email.assert_called_once()
    called_kwargs = mock_send_email.call_args[1]

    assert called_kwargs["to_email"] == "user@gmail.com"
    # 主题应当自动翻译为注册邮件的中文标题
    assert called_kwargs["subject"] == "欢迎注册 - 身份验证码"
    # HTML 内容应该正确渲染，包含验证码与有效期
    assert "776655" in called_kwargs["html_content"]
    assert "Logto 安全中心" in called_kwargs["html_content"]
