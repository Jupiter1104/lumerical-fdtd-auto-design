import pytest


@pytest.fixture(autouse=True)
def clear_real_feishu_webhook(monkeypatch):
    monkeypatch.delenv("FDTD_FEISHU_WEBHOOK", raising=False)
