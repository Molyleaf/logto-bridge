import json
import logging
import asyncio
from typing import Dict, Any

from alibabacloud_dypnsapi20170525.client import Client as DypnsapiClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dypnsapi20170525 import models as dypnsapi_models

from app.core.config import settings

logger = logging.getLogger(__name__)


class AliCloudSMSClient:
    """
    阿里云号码认证服务（DYPNSAPI）短信验证码接口客户端。

    @ai-intent: 封装阿里云短信发送逻辑，提供线程池隔离的异步调用方法。
    @ai-invariant: 短信发送操作必须幂等，能静默捕获并向上传递具体 API 错误。
    @ai-boundary: 只读配置输入，发起外部 HTTP 访问，采用线程池防止阻塞。
    @ai-context:
      Topology: app/integrations/sms.py (外部短信三方集成)
      Flow: Logto Request -> Parse -> AliCloudSMSClient.send_verify_code() -> Threadpool -> API Call
      Blast Radius: 阿里云 SDK 调用阻塞或报错会影响 Logto 手机验证码的投递。
    """

    def __init__(self):
        config = settings.alicloud_sms
        open_config = open_api_models.Config(
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
            endpoint=config.endpoint,
        )
        self.client = DypnsapiClient(open_config)
        self.sign_name = config.sign_name
        self.template_code = config.template_code
        self.scheme_name = config.scheme_name
        self.code_length = config.code_length
        self.valid_time = config.valid_time

    def _mask_phone(self, phone: str) -> str:
        """
        对手机号进行脱敏，仅保留前3位和后4位。
        """
        if len(phone) >= 7:
            return f"{phone[:3]}****{phone[-4:]}"
        return "****"

    async def send_verify_code(self, phone_number: str, code: str) -> Dict[str, Any]:
        """
        向指定手机号发送自定义验证码短信（通过线程池执行，防止阻塞事件循环）。

        @ai-intent: 执行线程池隔离的阿里云短信 API 调用，安全回传响应体。
        @ai-observe:
          Event Logging: [发送验证码短信] + [手机号: {phone_number}] + [成功/失败及原因]
          Golden Metrics: QPS 正常，请求响应耗时（基准：<500ms，触发告警：>2000ms）
          Data Sanitization: 敏感数据 [验证码 code] 绝对禁止落盘，[手机号 phone_number] 强制脱敏 (Mask)
        """
        masked_phone = self._mask_phone(phone_number)
        logger.info(f"开始通过阿里云号码服务发送短信验证码，目标手机号: {masked_phone}")

        def _sync_send() -> dypnsapi_models.SendSmsVerifyCodeResponse:
            # 计算分钟数（模板常定义 ${min} 或 ${valid_time}）
            valid_minutes = str(self.valid_time // 60)

            # 构建模板变量，兼容常见 template 参数名称
            param_dict = {
                "code": code,
                "min": valid_minutes,
                "valid_time": valid_minutes,
            }
            template_param = json.dumps(param_dict)

            request = dypnsapi_models.SendSmsVerifyCodeRequest(
                phone_number=phone_number,
                sign_name=self.sign_name,
                template_code=self.template_code,
                template_param=template_param,
                scheme_name=self.scheme_name,
                code_length=self.code_length,
                valid_time=self.valid_time,
            )
            return self.client.send_sms_verify_code(request)

        try:
            # 使用 asyncio.to_thread 进行线程隔离，防止同步的网络 IO 阻塞整个异步程序
            response = await asyncio.to_thread(_sync_send)

            body = response.body
            code_str = body.code
            message = body.message

            if code_str == "OK":
                logger.info(
                    f"短信验证码发送成功，手机号: {masked_phone}, RequestId: {body.request_id}"
                )
                return {
                    "success": True,
                    "request_id": body.request_id,
                    "code": code_str,
                    "message": message,
                }
            else:
                logger.error(
                    f"短信验证码发送失败，手机号: {masked_phone}, 错误码: {code_str}, 错误信息: {message}"
                )
                return {"success": False, "code": code_str, "message": message}
        except Exception as e:
            logger.exception(
                f"调用阿里云 SendSmsVerifyCode 接口发生未知异常，手机号: {masked_phone}"
            )
            return {"success": False, "code": "EXCEPTION", "message": str(e)}
