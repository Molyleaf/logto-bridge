import logging
import asyncio
from typing import List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiosmtplib

from app.core.config import settings, SMTPAccountConfig

logger = logging.getLogger(__name__)


class EmailDispatcher:
    """
    SMTP 邮件分发器。

    @ai-intent: 轮询（Round-Robin）分发邮件，支持自动故障转移（Failover）。
    @ai-invariant: 保证只要池中有可用的 SMTP 账户，邮件就会尝试继续投递；采用协程锁以保障并发环境下索引更新的安全性。
    @ai-boundary: 只读配置，发送外部 SMTP 数据流量，处理重试与网络超时。
    @ai-context:
      Topology: app/integrations/email.py (外部邮件三方集成)
      Flow: Logto Request -> Template Render -> EmailDispatcher.send_email() -> Safe Index Update -> aiosmtplib Send -> Failover if needed
      Blast Radius: 所有 SMTP 均失效时将阻断 Logto 邮箱验证流。
    """

    def __init__(self):
        self.accounts: List[SMTPAccountConfig] = settings.smtp_accounts
        self.current_index = 0
        self.lock = asyncio.Lock()  # 保证多协程并发安全

    def _mask_email(self, email: str) -> str:
        """
        对邮箱进行脱敏处理，防止敏感信息落盘。
        """
        if "@" in email:
            local, domain = email.split("@", 1)
            if len(local) > 2:
                return f"{local[:2]}***@{domain}"
            return f"***@{domain}"
        return "***"

    async def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """
        异步发送 HTML 邮件，包含轮询负载均衡与顺序容灾重试。

        @ai-intent: 轮询池中 SMTP 账户进行高可靠异步邮件投递，支持多账号无缝容灾。
        @ai-observe:
          Event Logging: [发送邮件] + [邮箱: {to_email}] + [主题: {subject}] + [最终成功/失败状态]
          Golden Metrics: QPS 正常，请求响应耗时（基准：<1500ms，触发告警：>5000ms）
          Data Sanitization: 敏感数据 [验证码/激活链接] 禁止打印，[收件箱] 强制脱敏 (Mask)
        """
        if not self.accounts:
            logger.critical(
                "未配置任何 SMTP 发送账户，邮件无法发送！请检查 config.toml"
            )
            return False

        masked_to = self._mask_email(to_email)
        logger.info(f"开始投递邮件给 {masked_to}，主题: {subject}")

        # 协程安全地获取并更新轮询索引
        async with self.lock:
            start_index = self.current_index
            self.current_index = (self.current_index + 1) % len(self.accounts)

        num_accounts = len(self.accounts)

        # 顺序尝试所有 SMTP 账号
        for i in range(num_accounts):
            index = (start_index + i) % num_accounts
            account = self.accounts[index]

            logger.info(
                f"尝试使用 SMTP 账户 [{account.username} @ {account.host}] 发送邮件 (当前尝试: {i + 1}/{num_accounts})"
            )

            try:
                # 构造 MIME 邮件体
                message = MIMEMultipart()
                message["From"] = f"{account.sender_name} <{account.sender_email}>"
                message["To"] = to_email
                message["Subject"] = subject

                # 绑定 HTML 内容
                message.attach(MIMEText(html_content, "html", "utf-8"))

                # 建立 aiosmtplib 连接
                client = aiosmtplib.SMTP(
                    hostname=account.host,
                    port=account.port,
                    username=account.username,
                    password=account.password,
                    use_tls=account.use_tls,
                    timeout=10.0,  # 设置 10 秒超时以快速触发 failover，防止请求挂起
                )

                async with client:
                    await client.send_message(message)

                logger.info(
                    f"邮件投递成功！使用 SMTP 账户: [{account.username} @ {account.host}] -> 目标: {masked_to}"
                )
                return True

            except Exception as e:
                logger.error(
                    f"SMTP 账户 [{account.username} @ {account.host}] 发送失败: {str(e)}。已准备自动故障转移..."
                )
                # 捕获异常后继续循环，利用下一个 SMTP 节点发送

        logger.critical(
            f"所有配置的 SMTP 账户均投递失败！邮件发送彻底失败，目标: {masked_to}"
        )
        return False
