import json
from unittest.mock import MagicMock, patch
import pytest
from app.integrations.sms import AliCloudSMSClient


@pytest.mark.anyio
async def test_sms_send_verify_code_success():
    """
    测试当阿里云短信发送接口返回 OK 时，客户端正确返回成功状态与 RequestId。
    """
    with patch("app.integrations.sms.DypnsapiClient") as mock_dypns_client:
        mock_instance = MagicMock()
        mock_dypns_client.return_value = mock_instance

        # 模拟阿里云返回的响应结构
        mock_response = MagicMock()
        mock_response.body.code = "OK"
        mock_response.body.message = "OK"
        mock_response.body.request_id = "TEST-REQ-ID-1234"
        mock_instance.send_sms_verify_code.return_value = mock_response

        # 初始化客户端
        client = AliCloudSMSClient()

        # 投递验证码
        result = await client.send_verify_code("13000000000", "554433")

        # 断言
        assert result["success"] is True
        assert result["code"] == "OK"
        assert result["request_id"] == "TEST-REQ-ID-1234"

        # 验证底层调用参数
        mock_instance.send_sms_verify_code.assert_called_once()
        called_args = mock_instance.send_sms_verify_code.call_args[0][0]

        assert called_args.phone_number == "13000000000"
        # 校验模板参数 JSON 内容是否包含正确的验证码
        param_dict = json.loads(called_args.template_param)
        assert param_dict["code"] == "554433"


@pytest.mark.anyio
async def test_sms_send_verify_code_failure():
    """
    测试当阿里云短信发送返回业务错误码时，客户端能优雅捕获并返回包含错误原因的字典。
    """
    with patch("app.integrations.sms.DypnsapiClient") as mock_dypns_client:
        mock_instance = MagicMock()
        mock_dypns_client.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.body.code = "isv.BUSINESS_LIMIT_CONTROL"
        mock_response.body.message = "发送频率超限"
        mock_instance.send_sms_verify_code.return_value = mock_response

        client = AliCloudSMSClient()
        result = await client.send_verify_code("13000000000", "998877")

        assert result["success"] is False
        assert result["code"] == "isv.BUSINESS_LIMIT_CONTROL"
        assert result["message"] == "发送频率超限"
