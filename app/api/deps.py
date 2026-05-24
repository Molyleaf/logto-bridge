import logging
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

logger = logging.getLogger(__name__)

# 定义标准 HTTPBearer 安全验证，自动解析 Authorization Header
security_scheme = HTTPBearer(auto_error=False)

# @ai-intent: 对接口请求执行严格的安全凭证校验，支持标准 Bearer 及自定义 X-Bridge-Token
# @ai-invariant: 若配置了 api_token，任何不匹配或缺失 Token 的请求必须强行阻断并回传 401，严禁静默忽略
# @ai-boundary: 劫持入参 Header 信息，拦截恶意流量


async def verify_api_token(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    x_bridge_token: str = Header(default=None, alias="X-Bridge-Token"),
) -> None:
    """
    FastAPI 路由依赖项，检查请求头中是否包含合法的 API 安全令牌。
    同时兼容:
    1. Standard Header -> Authorization: Bearer <token>
    2. Custom Header   -> X-Bridge-Token: <token>
    """
    # 获取全局配置的秘钥
    configured_token = settings.api_token

    # 如果本地配置的 token 仍未修改或者是空字符串，为了极致安全，仍必须进行占位拦截
    if not configured_token:
        logger.critical(
            "系统未配置 api_token 或 api_token 为空！为了系统安全，已临时拦截所有投递请求。"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="System configuration error: API Token not set",
        )

    token_candidate = None

    # 1. 优先尝试标准 Bearer Token
    if credentials and credentials.credentials:
        token_candidate = credentials.credentials

    # 2. 其次尝试自定义 Header 字段
    elif x_bridge_token:
        token_candidate = x_bridge_token

    if not token_candidate:
        logger.warning(
            "拒绝访问：请求头未携带任何 Authorization 凭证或 X-Bridge-Token！"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization credentials are required",
        )

    if token_candidate != configured_token:
        logger.warning("拒绝访问：请求携带了无效/不匹配的 API 安全令牌！")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authorization credentials",
        )

    # 验证成功，静默通过
