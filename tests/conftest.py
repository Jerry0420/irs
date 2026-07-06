import os
import tempfile

# 必須在 import app 前設定，讓 AppState 使用隔離的暫存資料目錄
os.environ["IRS_DATA_DIR"] = tempfile.mkdtemp(prefix="irs-test-")

import pytest
from fastapi.testclient import TestClient

from app import main as appmain


@pytest.fixture()
def client():
    # 每個測試都從乾淨的種子資料開始
    if appmain.state.file.exists():
        appmain.state.file.unlink()
    appmain.state.load()
    with TestClient(appmain.app, headers={"X-Admin-Token": "0000"}) as c:
        yield c
