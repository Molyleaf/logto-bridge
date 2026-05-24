import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import verify_api_token
from app.integrations.sms import AliCloudSMSClient

logger = logging.getLogger(__name__)
router = APIRouter()

# 延迟初始化全局短信客户端单例
sms_client = AliCloudSMSClient()


class LogtoSMSPayload(BaseModel):
    """
    Logto 短信推送 payload 载荷。
    """

    code: str = Field(description="生成的短信验证码数字")


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
    # @ai-intent: 接收 Logto 标准短信 Webhook 并安全转换投递至阿里云 SendSmsVerifyCode
    # @ai-boundary: 信任边界入参检验（已通过 verify_api_token 与 Pydantic），将投递行为交由短信服务类执行
    # @ai-observe:
    #   Event Logging: [Logto 短信网关接入] + [类型: {request.type}] + [处理状态]

    logger.info(
        f"收到 Logto 的短信网关推送，类型: {request.type}，IP: {request.ip or '未知'}"
    )

    # 调用阿里云集成客户端
    result = await sms_client.send_verify_code(
        phone_number=request.to, code=request.payload.code
    )

    if result["success"]:
        return {
            "status": "success",
            "message": "SMS sent successfully via AliCloud",
            "requestId": result.get("request_id"),
        }
    else:
        logger.error(f"短信网关处理失败，阿里云返回错误: {result.get('message')}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AliCloud SMS service error: {result.get('message')}",
        )
