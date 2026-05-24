import os
import logging
from fastapi import FastAPI

from app.core.logging import setup_logging
from app.api.sms import router as sms_router
from app.api.email import router as email_router

# 1. 初始化符合可观测性底线的日志流配置
log_level = os.environ.get("LOG_LEVEL", "INFO")
setup_logging(log_level)
logger = logging.getLogger("app.server")

# 2. 构造 FastAPI 应用根实例
app = FastAPI(
    title="Logto Bridge Gateway",
    description="Bridge HTTP webhook requests from Logto to Alibaba Cloud DYPNSAPI SMS and multiple SMTP mailers.",
    version="0.1.0",
)

# 3. 挂载子路由层
app.include_router(sms_router, prefix="/api", tags=["SMS API"])
app.include_router(email_router, prefix="/api", tags=["Email API"])


@app.get("/healthz", tags=["System Maintenance"])
async def healthz():
    """
    提供给 Docker Healthcheck 探针的本地轻量级健康检查接口。
    """
    # @ai-intent: 轻量响应以回报网关存活状态
    return {"status": "healthy", "service": "logto-bridge"}


@app.on_event("startup")
async def startup_event():
    """
    应用启动时的声明事件。
    """
    logger.info("==================================================================")
    logger.info(" Logto Bridge Gateway 成功启动！运行于 FastAPI 容器中。")
    logger.info(" 正在代理服务：阿里云号码验证短信服务 (DYPNSAPI) & 负载均衡邮件池")
    logger.info("==================================================================")
