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


@patch("app.api.email.email_dispatcher.send_email", new_callable=AsyncMock)
def test_email_webhook_route_organization_invitation(mock_send_email):
    """
    测试组织邀请 (OrganizationInvitation) 邮件投递。包含 link 但不包含 code。
    """
    mock_send_email.return_value = True

    headers = {"Authorization": f"Bearer {settings.api_token}"}

    payload = {
        "to": "invitee@example.com",
        "type": "OrganizationInvitation",
        "payload": {
            "link": "https://your-app.com/invite-accept?invitation-id=abcd1234",
            "locale": "en",
        },
        "ip": "1.2.3.4",
    }

    response = client.post("/api/email", json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    mock_send_email.assert_called_once()
    called_kwargs = mock_send_email.call_args[1]

    assert called_kwargs["to_email"] == "invitee@example.com"
    assert called_kwargs["subject"] == "Organization Invitation"
    # HTML 内容应该正确渲染，包含邀请链接
    assert (
        "https://your-app.com/invite-accept?invitation-id=abcd1234"
        in called_kwargs["html_content"]
    )
    assert "Logto Collaboration" in called_kwargs["html_content"]


@patch("app.api.email.email_dispatcher.send_email", new_callable=AsyncMock)
def test_email_webhook_subjects_mapping(mock_send_email):
    """
    遍历测试所有支持的 Logto 邮件类型及多语言，确保翻译后的主题行完全符合预期，并且未知类型能够安全兜底。
    """
    # 账号映射列表
    test_cases = [
        ("SignIn", "zh-CN", "登录身份验证码"),
        ("SignIn", "en", "Sign In Verification Code"),
        ("Register", "zh-CN", "欢迎注册 - 身份验证码"),
        ("Register", "en", "Welcome - Registration Verification Code"),
        ("ForgotPassword", "zh-CN", "重置密码 - 验证安全码"),
        ("ForgotPassword", "en", "Reset Password Verification Code"),
        ("OrganizationInvitation", "zh-CN", "您已获邀加入组织"),
        ("OrganizationInvitation", "en", "Organization Invitation"),
        ("BindNewIdentifier", "zh-CN", "绑定新账号 - 验证安全码"),
        ("BindNewIdentifier", "en", "Bind New Identifier - Verification Code"),
        ("MfaVerification", "zh-CN", "多因素身份验证 (MFA) - 验证安全码"),
        (
            "MfaVerification",
            "en",
            "Multi-Factor Authentication (MFA) - Verification Code",
        ),
        ("Generic", "zh-CN", "安全身份验证码"),
        ("Generic", "en", "Security Verification Code"),
        ("TestConnection", "zh-CN", "Logto 邮件服务连接测试成功"),
        ("TestConnection", "en", "Logto Mail Connector Test Successful"),
        # 未知/自定义类型兜底测试
        ("CustomFlow", "zh-CN", "安全身份验证码"),
        ("CustomFlow", "en", "Security Verification Code"),
    ]

    headers = {"Authorization": f"Bearer {settings.api_token}"}

    for flow_type, locale, expected_subject in test_cases:
        mock_send_email.reset_mock()
        mock_send_email.return_value = True

        payload = {
            "to": "check@example.com",
            "type": flow_type,
            "payload": {"code": "112233", "locale": locale},
        }

        response = client.post("/api/email", json=payload, headers=headers)
        assert response.status_code == 200

        mock_send_email.assert_called_once()
        called_kwargs = mock_send_email.call_args[1]
        assert called_kwargs["subject"] == expected_subject


@patch("app.api.sms.sms_client.send_verify_code", new_callable=AsyncMock)
def test_sms_always_return_2xx_on_failure(mock_send_verify_code):
    """
    测试开启 always_return_2xx 情况下，即便阿里云短信发送失败，接口仍返回 200 响应。
    """
    # 模拟发送失败
    mock_send_verify_code.return_value = {
        "success": False,
        "message": "isv.BUSINESS_LIMIT_CONTROL",
    }

    # 通过 patch.dict 修改全局配置的字典值开启 always_return_2xx 为 True 开展测试
    with patch.dict(settings.sms["alicloud"], {"always_return_2xx": True}):
        headers = {"Authorization": f"Bearer {settings.api_token}"}
        payload = {
            "to": "+8618800001111",
            "type": "SignIn",
            "payload": {"code": "887766"},
        }
        response = client.post("/api/sms", json=payload, headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert "BUSINESS_LIMIT_CONTROL" in response.json()["message"]


@patch("app.api.email.email_dispatcher.send_email", new_callable=AsyncMock)
def test_email_always_return_2xx_on_failure(mock_send_email):
    """
    测试开启 email_always_return_2xx 情况下，即便所有 SMTP 服务发送均失败，接口仍返回 200 响应。
    """
    # 模拟发送失败
    mock_send_email.return_value = False

    # 通过 patch.dict 修改全局配置的字典值开启 email.always_return_2xx 为 True 开展测试
    with patch.dict(settings.email, {"always_return_2xx": True}):
        headers = {"Authorization": f"Bearer {settings.api_token}"}
        payload = {
            "to": "user@gmail.com",
            "type": "Register",
            "payload": {"code": "776655", "locale": "zh-CN"},
        }
        response = client.post("/api/email", json=payload, headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert "SMTP servers failed" in response.json()["message"]


@patch("app.api.email.email_dispatcher.send_email", new_callable=AsyncMock)
def test_payload_extra_fields_compatibility(mock_send_email):
    """
    测试当 Logto 传入额外的未知 payload 属性（如 application 和 organization 对象）时，
    接口能正常兼容解析，不会报 Pydantic 校验错误，并且允许接受和保存该数据。
    """
    mock_send_email.return_value = True

    headers = {"Authorization": f"Bearer {settings.api_token}"}
    payload = {
        "to": "user@gmail.com",
        "type": "Register",
        "payload": {
            "code": "776655",
            "locale": "en",
            "application": {"name": "Test Application Pro"},
            "organization": {"name": "Acme Org"},
        },
    }
    response = client.post("/api/email", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # 校验接口动作与参数是否正常捕获
    mock_send_email.assert_called_once()
    called_kwargs = mock_send_email.call_args[1]

    assert "776655" in called_kwargs["html_content"]
