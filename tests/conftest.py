import pytest


@pytest.fixture
def anyio_backend():
    """
    指定 AnyIO 异步测试所采用的后端引擎。
    """
    return "asyncio"
