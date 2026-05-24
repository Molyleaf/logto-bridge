import os
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
import tomli

# @ai-intent: 加载并校验应用程序的全局 TOML 配置，支持环境变量覆盖
# @ai-invariant: 配置文件的解析和校验必须严格执行，不允许任何缺失的关键字段在静默状态下运行
# @ai-boundary: 仅限于以只读方式读取配置文件，隔离所有外部可篡改源


class AliCloudSMSConfig(BaseModel):
    """
    阿里云短信发送相关参数。
    """

    access_key_id: str
    access_key_secret: str
    endpoint: str = "dypnsapi.aliyuncs.com"
    sign_name: str
    template_code: str
    scheme_name: str = "default scheme"
    code_length: int = 6
    valid_time: int = 300


class SMTPAccountConfig(BaseModel):
    """
    SMTP 邮件账户配置。
    """

    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True
    sender_email: str
    sender_name: str = "Logto"


class Settings(BaseModel):
    """
    全局配置根结构。
    """

    api_token: str
    sms: dict = Field(default_factory=dict)
    email: dict = Field(default_factory=dict)

    @property
    def alicloud_sms(self) -> AliCloudSMSConfig:
        """
        获取阿里云短信服务配置子集。
        """
        # @ai-intent: 解析并返回阿里云 SMS 配置
        return AliCloudSMSConfig(**self.sms.get("alicloud", {}))

    @property
    def smtp_accounts(self) -> List[SMTPAccountConfig]:
        """
        获取负载均衡的多个 SMTP 账户池。
        """
        # @ai-intent: 解析并返回负载均衡 SMTP 账户列表
        accounts = self.email.get("smtp_accounts", [])
        return [SMTPAccountConfig(**acc) for acc in accounts]


def load_settings() -> Settings:
    """
    从 config.toml（如果存在）或 config.example.toml（开发/测试备用）中加载配置。
    支持环境变量覆盖，如 BRIDGE_API_TOKEN 覆盖 api_token。
    """
    # @ai-intent: 执行配置文件定位、读取、环境变量合并和 Pydantic 最终校验
    # @ai-observe:
    #   Data Sanitization: 敏感的 AccessKey 和 SMTP 密码绝不能在此函数的日志里打印
    base_dir = Path(__file__).resolve().parent.parent.parent
    config_path = base_dir / "config" / "config.toml"

    if not config_path.exists():
        config_path = base_dir / "config" / "config.example.toml"

    with open(config_path, "rb") as f:
        config_data = tomli.load(f)

    # 支持核心环境变量覆盖
    if "BRIDGE_API_TOKEN" in os.environ:
        config_data["api_token"] = os.environ["BRIDGE_API_TOKEN"]

    if "BRIDGE_SMS_ACCESS_KEY_ID" in os.environ:
        config_data.setdefault("sms", {}).setdefault("alicloud", {})[
            "access_key_id"
        ] = os.environ["BRIDGE_SMS_ACCESS_KEY_ID"]

    if "BRIDGE_SMS_ACCESS_KEY_SECRET" in os.environ:
        config_data.setdefault("sms", {}).setdefault("alicloud", {})[
            "access_key_secret"
        ] = os.environ["BRIDGE_SMS_ACCESS_KEY_SECRET"]

    return Settings(**config_data)


# 全局共享实例
settings = load_settings()
