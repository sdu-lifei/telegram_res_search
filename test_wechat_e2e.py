import asyncio
import sys
import os
import time
import xml.etree.ElementTree as ET

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pansou_py.api.wechat import wechat_message
from pansou_py.core.config import settings
from unittest.mock import MagicMock, AsyncMock
import pytest

# Setup environment for test
settings.WECHAT_TOKEN = "test_token"

@pytest.mark.asyncio
async def test_wechat_flow():
    print("Testing WeChat message flow locally...")
    
    # Mock BackgroundTasks
    bg_tasks = MagicMock()
    
    # Create a mock Request
    request = MagicMock()
    
    # Fake XML body for search "庆余年"
    xml_body = """
    <xml>
        <ToUserName><![CDATA[gh_123456789]]></ToUserName>
        <FromUserName><![CDATA[openid_test_user]]></FromUserName>
        <CreateTime>1773492417</CreateTime>
        <MsgType><![CDATA[text]]></MsgType>
        <Content><![CDATA[庆余年]]></Content>
        <MsgId>1234567890</MsgId>
    </xml>
    """
    request.body = AsyncMock(return_value=xml_body.encode('utf-8'))
    
    # Fake query params (bypass signature check for local test if possible, or mock it)
    # Actually _verify_signature uses sorted items. Let's mock it to always return True.
    import pansou_py.api.wechat as wechat_mod
    wechat_mod._verify_signature = lambda signature, timestamp, nonce: True
    
    request.query_params = {
        "signature": "fake",
        "timestamp": "1773492417",
        "nonce": "fake"
    }

    print("--- Calling wechat_message ---")
    start = time.time()
    response = await wechat_message(request, bg_tasks)
    duration = time.time() - start
    
    print(f"--- Response (received in {duration:.2f}s) ---")
    print(f"Status: {response.status_code}")
    print(f"Media Type: {response.media_type}")
    
    content = response.body.decode('utf-8')
    print("Content:")
    print(content)
    
    # Verify XML structure
    root = ET.fromstring(content)
    reply_text = root.find("Content").text
    print("\nReply Content Preview:")
    print(reply_text[:200] + "...")
    
    if "庆余年" in reply_text and ("网盘" in reply_text or "抓取" in reply_text):
        print("\n✅ End-to-end test PASSED.")
    else:
        print("\n❌ End-to-end test FAILED (unexpected reply content).")

if __name__ == "__main__":
    asyncio.run(test_wechat_flow())
