import logging
import sys

# @ai-intent: 全局初始化并配置符合安全与可观测性底线的日志流结构
# @ai-invariant: 日志格式必须统一，严禁任何可能包含敏感信息（API Token、密码、验证码）的无脱敏裸日志输出
# @ai-boundary: 劫持标准输出流 sys.stdout，隔离并统一应用内所有的日志打印动作


def setup_logging(level: str = "INFO") -> None:
    """
    配置标准 Python 日志输出格式。
    """
    # @ai-intent: 设置控制台日志输出流格式与级别
    log_format = (
        "[%(asctime)s] [%(levelname)s] [%(name)s] "
        "[%(filename)s:%(lineno)d] - %(message)s"
    )

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # 移除已有的 handler 以防重复打印
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    formatter = logging.Formatter(log_format)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)

    # 屏蔽第三方库的噪点日志
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
