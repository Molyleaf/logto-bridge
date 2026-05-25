import logging
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import verify_api_token
from app.integrations.sms import AliCloudSMSClient
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# 延迟初始化全局短信客户端单例
sms_client = AliCloudSMSClient()


class LogtoSMSPayload(BaseModel):
    """
    Logto 短信推送 payload 载荷。
    """

    code: Optional[str] = Field(default=None, description="生成的短信验证码数字")
    link: Optional[str] = Field(default=None, description="邀请链接或重定向激活链接")
    locale: Optional[str] = Field(
        default=None, description="用户的首选语言环境 (如 zh-CN, en)"
    )

    # 允许接收任何其他自定义字段，如 application / organization 等
    model_config = {"extra": "allow"}


class LogtoSMSRequest(BaseModel):
    """
    Logto HTTP 自定义短信连接器推送的完整 JSON 报文契约。
    """

    to: str = Field(description="接收方手机号（如 +8613000000000）")
    type: str = Field(
        description="短信验证流用途（如 SignIn, Register, ForgotPassword 等）"
    )
    payload: LogtoSMSPayload = Field(description="短信动态内容载荷")
    ip: Optional[str] = Field(default=None, description="触发请求的用户 IP 终端地址")


@router.post("/sms", dependencies=[Depends(verify_api_token)])
async def handle_logto_sms(request: LogtoSMSRequest):
    """
    接收来自 Logto 的 HTTP 报文，并调用阿里云接口投递短信。
    """
    # @ai-intent: 接收 Logto 标准短信 Webhook 并安全转换投递至阿里云 SendSmsVerifyCode，支持 2xx 降级
    # @ai-boundary: 信任边界入参检验（已通过 verify_api_token 与 Pydantic），将投递行为交由短信服务类执行
    # @ai-observe:
    #   Event Logging: [Logto 短信网关接入] + [类型: {request.type}] + [处理状态]

    logger.info(
        f"收到 Logto 的短信网关推送，类型: {request.type}，IP: {request.ip or '未知'}"
    )

    # 校验并归一化手机号格式（遵循只在边界校验一次的原则）
    phone_cleaned = request.to.strip().replace(" ", "").replace("-", "")

    if phone_cleaned.startswith("+"):
        if not phone_cleaned.startswith("+86"):
            logger.warning(f"拒绝发送短信：手机号 {request.to} 国家代码不是 +86")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only +86 or standard Chinese mobile numbers are supported. (仅支持 +86 或中国大陆规范手机号)",
            )

        # 检查是否符合 +861xxxxxxxxxx 格式
        national_part = phone_cleaned[3:]
        if not re.match(r"^1[3-9]\d{9}$", national_part):
            logger.warning(
                f"拒绝发送短信：手机号 {request.to} 不符合 +861xxxxxxxxxx 格式规范"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Chinese mobile number format. (手机号格式不符合中国大陆 11 位手机号规范)",
            )
        normalized_phone = national_part
    else:
        # 检查是否为中国规范手机号 1xxxxxxxxxx
        if not re.match(r"^1[3-9]\d{9}$", phone_cleaned):
            logger.warning(
                f"拒绝发送短信：手机号 {request.to} 不是合法的中国大陆手机号"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only +86 or standard Chinese mobile numbers are supported. (仅支持 +86 或中国大陆规范手机号)",
            )
        normalized_phone = phone_cleaned

    # 调用阿里云集成客户端
    result = await sms_client.send_verify_code(
        phone_number=normalized_phone, code=request.payload.code or ""
    )

    if result["success"]:
        return {
            "status": "success",
            "message": "SMS sent successfully via AliCloud",
            "requestId": result.get("request_id"),
        }
    else:
        logger.error(f"短信网关处理失败，阿里云返回错误: {result.get('message')}")

        # 兼容性容灾降级处理：若配置为 always_return_2xx，则返回 200 OK 告知 Logto，避免认证流中断
        if settings.alicloud_sms.always_return_2xx:
            logger.warning("已启用 always_return_2xx 策略，强制向 Logto 返回 2xx 响应")
            return {
                "status": "failed",
                "message": f"AliCloud SMS service error: {result.get('message')}",
                "requestId": result.get("request_id"),
            }

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AliCloud SMS service error: {result.get('message')}",
        )
