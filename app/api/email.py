import logging
from typing import Optional, Dict
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.api.deps import verify_api_token
from app.integrations.email import EmailDispatcher
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# 延迟初始化全局邮件分发器单例
email_dispatcher = EmailDispatcher()

# 初始化 Jinja2 环境
base_dir = Path(__file__).resolve().parent.parent
templates_dir = base_dir / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=select_autoescape(["html", "xml"]),
)


class LogtoEmailPayload(BaseModel):
    """
    Logto 邮件推送 payload 载荷。
    """

    code: Optional[str] = Field(
        default=None, description="生成的邮箱验证码或链接安全码"
    )
    link: Optional[str] = Field(default=None, description="邀请链接或重定向激活链接")
    locale: Optional[str] = Field(
        default="en", description="用户的首选语言环境 (如 zh-CN, en)"
    )

    # 允许接收任何其他自定义字段，如 application / organization 等
    model_config = {"extra": "allow"}


class LogtoEmailRequest(BaseModel):
    """
    Logto HTTP 自定义邮件连接器推送的完整 JSON 报文契约。
    """

    to: str = Field(description="接收方邮箱地址")
    type: str = Field(
        description="邮件验证流用途（如 SignIn, Register, ForgotPassword 等）"
    )
    payload: LogtoEmailPayload = Field(description="邮件动态内容载荷")
    ip: Optional[str] = Field(default=None, description="触发请求的用户 IP 终端地址")


@router.post("/email", dependencies=[Depends(verify_api_token)])
async def handle_logto_email(request: LogtoEmailRequest):
    """
    接收来自 Logto 的 HTTP 邮件发送请求，根据类型和语言渲染 HTML，并通过负载均衡 SMTP 发送。
    """
    # @ai-intent: 接收 Logto 标准邮件 Webhook 并渲染双语 HTML，再通过负载均衡 SMTP 安全投递
    # @ai-boundary: 信任边界入参检验（已通过 verify_api_token 与 Pydantic），将投递行为交由邮件分发器执行
    # @ai-observe:
    #   Event Logging: [Logto 邮件网关接入] + [类型: {request.type}] + [接收箱: {request.to}] + [处理状态]

    logger.info(
        f"收到 Logto 的邮件网关推送，类型: {request.type}，IP: {request.ip or '未知'}"
    )

    # 1. 语言国际化判断
    user_locale = request.payload.locale or "en"
    lang = "zh-CN" if user_locale.lower().startswith("zh") else "en"

    flow_type = request.type
    template_rel_path = f"{lang}/{flow_type}.html"

    # 2. 检查特定模板是否存在，若不存在则优雅降级到 SignIn 基础模板，防止服务崩溃
    if not (templates_dir / template_rel_path).exists():
        logger.warning(
            f"模板 {template_rel_path} 未找到，将优雅降级使用通用模板 {lang}/SignIn.html"
        )
        template_rel_path = f"{lang}/SignIn.html"

    # 3. 渲染 HTML 内容
    # 验证码有效期默认设置为 5 分钟，或复用阿里云 SMS 设置的有效时间
    valid_minutes = str(settings.alicloud_sms.valid_time // 60)

    try:
        template = jinja_env.get_template(template_rel_path)
        # 将 payload 中的所有自定义属性与预定义关键字段一同透传给 Jinja2 上下文，保证对 Logto 额外扩展参数的完美支持
        render_context = {
            "code": request.payload.code or "",
            "link": request.payload.link or "",
            "valid_minutes": valid_minutes,
            **request.payload.model_dump(),
        }
        html_content = template.render(**render_context)
    except Exception as e:
        logger.exception("Jinja2 渲染邮件 HTML 模板发生严重异常！")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email template rendering failed: {str(e)}",
        )

    # 4. 根据类型定义多语言主题
    subject_map: Dict[str, Dict[str, str]] = {
        "SignIn": {"zh-CN": "登录身份验证码", "en": "Sign In Verification Code"},
        "Register": {
            "zh-CN": "欢迎注册 - 身份验证码",
            "en": "Welcome - Registration Verification Code",
        },
        "ForgotPassword": {
            "zh-CN": "重置密码 - 验证安全码",
            "en": "Reset Password Verification Code",
        },
        "OrganizationInvitation": {
            "zh-CN": "您已获邀加入组织",
            "en": "Organization Invitation",
        },
        "BindNewIdentifier": {
            "zh-CN": "绑定新账号 - 验证安全码",
            "en": "Bind New Identifier - Verification Code",
        },
        "MfaVerification": {
            "zh-CN": "多因素身份验证 (MFA) - 验证安全码",
            "en": "Multi-Factor Authentication (MFA) - Verification Code",
        },
        "Generic": {
            "zh-CN": "安全身份验证码",
            "en": "Security Verification Code",
        },
        "TestConnection": {
            "zh-CN": "Logto 邮件服务连接测试成功",
            "en": "Logto Mail Connector Test Successful",
        },
    }

    subject = subject_map.get(flow_type, {}).get(lang)
    if not subject:
        subject = "安全身份验证码" if lang == "zh-CN" else "Security Verification Code"

    # 5. 调用 SMTP 负载均衡分发器进行发送
    success = await email_dispatcher.send_email(
        to_email=request.to, subject=subject, html_content=html_content
    )

    if success:
        return {
            "status": "success",
            "message": "Email rendered and sent successfully via load-balanced SMTP pool",
        }
    else:
        logger.critical(
            f"邮件网关投递彻底失败，全部 SMTP 均已宕机或被拒，收件地址: {request.to}"
        )

        # 兼容性容灾降级处理：若配置为 always_return_2xx，则返回 200 OK 告知 Logto，避免认证流中断
        if settings.email_always_return_2xx:
            logger.warning("已启用 always_return_2xx 策略，强制向 Logto 返回 2xx 响应")
            return {
                "status": "failed",
                "message": "All configured SMTP servers failed to deliver the email",
            }

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="All configured SMTP servers failed to deliver the email",
        )
