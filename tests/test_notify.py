"""测试通知渠道与编排。"""

from __future__ import annotations

import logging
from unittest.mock import patch

from quant_balance.notify import load_notify_settings, send_configured_notifications
from quant_balance.notify.dingtalk import DingTalkNotifier
from quant_balance.notify.email_notify import EmailNotifier
from quant_balance.notify.serverchan import ServerChanNotifier
from quant_balance.notify.wecom import WecomNotifier


class _DummyResponse:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False


def test_load_notify_settings_prefers_new_structure():
    payload = load_notify_settings({
        "notify": {
            "enabled": ["wecom", "email"],
            "wecom": {"webhook": "https://wecom"},
            "email": {"receiver": "demo@example.com"},
        },
        "notifications": {
            "wecom_webhook": "https://legacy",
        },
    })

    assert payload["enabled"] == ["wecom", "email"]
    assert payload["wecom"]["webhook"] == "https://wecom"
    assert payload["email"]["receiver"] == "demo@example.com"


def test_load_notify_settings_falls_back_to_legacy_notifications():
    payload = load_notify_settings({
        "notifications": {
            "wecom_webhook": "https://wecom",
            "dingding_webhook": "https://dingtalk",
            "serverchan_sendkey": "sendkey",
            "email_recipient": "demo@example.com",
            "smtp_host": "smtp.qq.com",
            "smtp_sender": "sender@example.com",
            "smtp_password": "secret",
        },
    })

    assert payload["enabled"] == ["wecom", "dingtalk", "serverchan", "email"]
    assert payload["serverchan"]["sendkey"] == "sendkey"
    assert payload["email"]["sender"] == "sender@example.com"


def test_wecom_notifier_uses_markdown_payload(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        assert timeout == 10
        return _DummyResponse('{"errcode":0}')

    monkeypatch.setattr("quant_balance.notify.wecom.urlopen", fake_urlopen)
    notifier = WecomNotifier("https://example.com/wecom")

    assert notifier.send("测试标题", "第一行\n第二行") is True
    assert captured["url"] == "https://example.com/wecom"
    assert '"msgtype": "markdown"' in captured["body"]


def test_dingtalk_notifier_adds_signature_when_secret_present(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        assert timeout == 10
        return _DummyResponse('{"errcode":0}')

    monkeypatch.setattr("quant_balance.notify.dingtalk.time.time", lambda: 1710000000.0)
    monkeypatch.setattr("quant_balance.notify.dingtalk.urlopen", fake_urlopen)
    notifier = DingTalkNotifier("https://example.com/dingtalk", secret="SEC123")

    assert notifier.send("测试标题", "测试正文") is True
    assert "timestamp=" in captured["url"]
    assert "sign=" in captured["url"]
    assert '"msgtype": "text"' in captured["body"]


def test_serverchan_notifier_posts_form_data(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        assert timeout == 10
        return _DummyResponse('{"code":0}')

    monkeypatch.setattr("quant_balance.notify.serverchan.urlopen", fake_urlopen)
    notifier = ServerChanNotifier("sendkey")

    assert notifier.send("测试标题", "测试正文") is True
    assert captured["url"].endswith("/sendkey.send")
    assert "title=%E6%B5%8B%E8%AF%95%E6%A0%87%E9%A2%98" in captured["body"]


def test_email_notifier_sends_via_smtp_ssl(monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):  # noqa: ANN001
            captured["host"] = host
            captured["port"] = port
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def login(self, username, password):
            captured["username"] = username
            captured["password"] = password

        def send_message(self, message):
            captured["subject"] = message["Subject"]
            captured["to"] = message["To"]

    monkeypatch.setattr("quant_balance.notify.email_notify.smtplib.SMTP_SSL", FakeSMTP)
    notifier = EmailNotifier(
        smtp_host="smtp.qq.com",
        smtp_port=465,
        sender="sender@example.com",
        receiver="demo@example.com",
        password="secret",
    )

    assert notifier.send("测试标题", "测试正文") is True
    assert captured["host"] == "smtp.qq.com"
    assert captured["username"] == "sender@example.com"
    assert captured["to"] == "demo@example.com"


def test_send_configured_notifications_logs_failure_without_raising(caplog):
    caplog.set_level(logging.WARNING, logger="quant_balance")

    class FakeNotifier:
        def __init__(self, sent: bool):
            self.sent = sent

        def send(self, title: str, content: str) -> bool:
            return self.sent

    with patch(
        "quant_balance.notify.build_notifier",
        side_effect=[FakeNotifier(True), RuntimeError("channel unavailable"), FakeNotifier(False)],
    ):
        items = send_configured_notifications(
            title="测试标题",
            content="测试正文",
            config={
                "notify": {
                    "enabled": ["wecom", "serverchan", "email"],
                    "wecom": {"webhook": "https://wecom"},
                    "serverchan": {"sendkey": "sendkey"},
                    "email": {
                        "smtp_host": "smtp.qq.com",
                        "sender": "sender@example.com",
                        "receiver": "demo@example.com",
                        "password": "secret",
                    },
                },
            },
        )

    assert [item["status"] for item in items] == ["sent", "failed", "failed"]
    assert "NOTIFY_SEND" in caplog.text
