from unittest.mock import AsyncMock, patch
import pytest
import aiosmtplib
from app.integrations.email import EmailDispatcher


@pytest.mark.anyio
async def test_email_round_robin_success():
    """
    测试多邮件投递时，自动按 Round-Robin 轮询顺序选择 SMTP 账号发送。
    """
    with patch("app.integrations.email.aiosmtplib.SMTP") as mock_smtp_cls:
        # 模拟 aiosmtplib.SMTP 客户端行为
        mock_client = AsyncMock()
        mock_smtp_cls.return_value = mock_client

        dispatcher = EmailDispatcher()
        # 强制重置索引确保可预测性
        dispatcher.current_index = 0

        # 账户数量
        num_accounts = len(dispatcher.accounts)
        assert num_accounts >= 2

        # 第一次投递：应该使用索引 0 的账号
        success1 = await dispatcher.send_email(
            "test1@test.com", "Test Subject 1", "<h1>Test 1</h1>"
        )
        assert success1 is True

        # 检查实例化参数
        mock_smtp_cls.assert_any_call(
            hostname=dispatcher.accounts[0].host,
            port=dispatcher.accounts[0].port,
            username=dispatcher.accounts[0].username,
            password=dispatcher.accounts[0].password,
            use_tls=dispatcher.accounts[0].use_tls,
            timeout=10.0,
        )

        # 第二次投递：应该使用索引 1 的账号 (Round-Robin)
        success2 = await dispatcher.send_email(
            "test2@test.com", "Test Subject 2", "<h1>Test 2</h1>"
        )
        assert success2 is True

        mock_smtp_cls.assert_any_call(
            hostname=dispatcher.accounts[1].host,
            port=dispatcher.accounts[1].port,
            username=dispatcher.accounts[1].username,
            password=dispatcher.accounts[1].password,
            use_tls=dispatcher.accounts[1].use_tls,
            timeout=10.0,
        )


@pytest.mark.anyio
async def test_email_failover_success():
    """
    测试当某一个 SMTP 账号失效抛出异常时，分发器静默故障转移，尝试下一个账号并发送成功。
    """
    with patch("app.integrations.email.aiosmtplib.SMTP") as mock_smtp_cls:
        # 创建两个不同的 mock client 实例
        # 实例 1：模拟抛出连接超时异常
        mock_client_fail = AsyncMock()
        mock_client_fail.__aenter__.side_effect = aiosmtplib.SMTPConnectError(
            "Connection timed out"
        )

        # 实例 2：模拟成功投递
        mock_client_success = AsyncMock()

        # 让 mock_smtp_cls 依次返回这两个实例
        mock_smtp_cls.side_effect = [mock_client_fail, mock_client_success]

        dispatcher = EmailDispatcher()
        dispatcher.current_index = 0

        # 触发邮件投递
        # 即使第一个账号超时失败，它应该自动重试并利用第二个账号发送成功，最终返回 True
        success = await dispatcher.send_email(
            "user@failover.com", "Test Failover", "<h1>Try</h1>"
        )

        assert success is True
        # 验证底层被实例化调用了两次（对应第一次失败，第二次成功故障转移）
        assert mock_smtp_cls.call_count == 2
