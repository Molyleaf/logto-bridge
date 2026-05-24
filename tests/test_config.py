import os
from app.core.config import settings, load_settings


def test_settings_loaded():
    """
    测试全局设置是否已正确加载，并且核心属性不为空。
    """
    assert settings is not None
    assert settings.api_token is not None

    # 确保阿里云配置已正确映射并具有默认值
    sms_cfg = settings.alicloud_sms
    assert sms_cfg.endpoint == "dypnsapi.aliyuncs.com"
    assert sms_cfg.code_length == 6

    # 确保 SMTP 账户池已正确映射
    accounts = settings.smtp_accounts
    assert len(accounts) >= 2
    assert accounts[0].host == "smtp.example1.com"
    assert accounts[1].host == "smtp.example2.com"


def test_env_override():
    """
    测试环境变量是否能够覆盖 TOML 中的默认配置。
    """
    os.environ["BRIDGE_API_TOKEN"] = "env_overridden_secret_token"
    os.environ["BRIDGE_SMS_ACCESS_KEY_ID"] = "env_ak_123"
    os.environ["BRIDGE_SMS_ACCESS_KEY_SECRET"] = "env_sk_456"

    temp_settings = load_settings()
    assert temp_settings.api_token == "env_overridden_secret_token"
    assert temp_settings.alicloud_sms.access_key_id == "env_ak_123"
    assert temp_settings.alicloud_sms.access_key_secret == "env_sk_456"

    # 清理环境变量以防影响其他测试
    del os.environ["BRIDGE_API_TOKEN"]
    del os.environ["BRIDGE_SMS_ACCESS_KEY_ID"]
    del os.environ["BRIDGE_SMS_ACCESS_KEY_SECRET"]
