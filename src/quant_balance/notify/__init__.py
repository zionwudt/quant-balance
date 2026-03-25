"""通知发送编排。"""

from __future__ import annotations

import logging
from typing import Literal

from quant_balance.data.common import load_app_config
from quant_balance.logging_utils import get_logger, log_event
from quant_balance.notify.base import Notifier
from quant_balance.notify.dingtalk import DingTalkNotifier
from quant_balance.notify.email_notify import EmailNotifier
from quant_balance.notify.serverchan import ServerChanNotifier
from quant_balance.notify.wecom import WecomNotifier

NotifyChannel = Literal["wecom", "dingtalk", "serverchan", "email"]
SUPPORTED_NOTIFY_CHANNELS = frozenset({"wecom", "dingtalk", "serverchan", "email"})

logger = get_logger(__name__)


def load_notify_settings(config: dict[str, object] | None = None) -> dict[str, object]:
    """解析通知配置，优先使用新 notify 结构并兼容旧 notifications。"""

    app_config = config or load_app_config()
    raw_notify = app_config.get("notify")
    if isinstance(raw_notify, dict):
        enabled = _normalize_enabled(raw_notify.get("enabled", []))
        return {
            "enabled": enabled,
            "wecom": dict(raw_notify.get("wecom") or {}),
            "dingtalk": dict(raw_notify.get("dingtalk") or {}),
            "serverchan": dict(raw_notify.get("serverchan") or {}),
            "email": dict(raw_notify.get("email") or {}),
        }

    legacy = dict(app_config.get("notifications") or {})
    enabled: list[str] = []
    if str(legacy.get("wecom_webhook") or "").strip():
        enabled.append("wecom")
    if str(legacy.get("dingding_webhook") or "").strip():
        enabled.append("dingtalk")
    if str(legacy.get("serverchan_sendkey") or "").strip():
        enabled.append("serverchan")
    if str(legacy.get("email_recipient") or "").strip():
        enabled.append("email")

    return {
        "enabled": enabled,
        "wecom": {
            "webhook": legacy.get("wecom_webhook", ""),
        },
        "dingtalk": {
            "webhook": legacy.get("dingding_webhook", ""),
            "secret": legacy.get("dingding_secret", ""),
        },
        "serverchan": {
            "sendkey": legacy.get("serverchan_sendkey", ""),
        },
        "email": {
            "smtp_host": legacy.get("smtp_host", ""),
            "smtp_port": legacy.get("smtp_port", 465),
            "sender": legacy.get("smtp_sender", ""),
            "receiver": legacy.get("email_recipient", ""),
            "password": legacy.get("smtp_password", ""),
            "username": legacy.get("smtp_username", ""),
            "use_ssl": legacy.get("smtp_use_ssl", True),
            "starttls": legacy.get("smtp_starttls", True),
        },
    }


def send_configured_notifications(
    *,
    title: str,
    content: str,
    config: dict[str, object] | None = None,
    strict: bool = False,
) -> list[dict[str, object]]:
    """按配置向已启用渠道发送通知。"""

    try:
        settings = load_notify_settings(config)
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise
        log_event(
            logger,
            "NOTIFY_SEND",
            level=logging.WARNING,
            channel="config",
            status="failed",
            detail=str(exc),
        )
        return [{
            "channel": "config",
            "status": "failed",
            "detail": str(exc),
        }]

    enabled = list(settings.get("enabled") or [])
    results: list[dict[str, object]] = []
    for channel in enabled:
        try:
            notifier = build_notifier(channel, settings)
            sent = notifier.send(title, content)
            status = "sent" if sent else "failed"
            if not sent:
                log_event(
                    logger,
                    "NOTIFY_SEND",
                    level=logging.WARNING,
                    channel=channel,
                    status=status,
                    detail="渠道返回失败状态",
                )
            results.append({
                "channel": channel,
                "status": status,
                "detail": None if sent else "渠道返回失败状态",
            })
        except Exception as exc:  # noqa: BLE001
            log_event(
                logger,
                "NOTIFY_SEND",
                level=logging.WARNING,
                channel=channel,
                status="failed",
                detail=str(exc),
            )
            results.append({
                "channel": channel,
                "status": "failed",
                "detail": str(exc),
            })
    return results


def build_notifier(channel: str, settings: dict[str, object]) -> Notifier:
    """构造指定渠道的通知发送器。"""

    normalized = _normalize_channel(channel)
    if normalized == "wecom":
        cfg = dict(settings.get("wecom") or {})
        return WecomNotifier(str(cfg.get("webhook") or ""))
    if normalized == "dingtalk":
        cfg = dict(settings.get("dingtalk") or {})
        return DingTalkNotifier(
            str(cfg.get("webhook") or ""),
            secret=str(cfg.get("secret") or ""),
        )
    if normalized == "serverchan":
        cfg = dict(settings.get("serverchan") or {})
        return ServerChanNotifier(str(cfg.get("sendkey") or ""))

    cfg = dict(settings.get("email") or {})
    return EmailNotifier(
        smtp_host=str(cfg.get("smtp_host") or ""),
        smtp_port=int(cfg.get("smtp_port", 465)),
        sender=str(cfg.get("sender") or ""),
        receiver=str(cfg.get("receiver") or ""),
        password=str(cfg.get("password") or ""),
        username=str(cfg.get("username") or ""),
        use_ssl=bool(cfg.get("use_ssl", True)),
        starttls=bool(cfg.get("starttls", True)),
    )


def _normalize_enabled(value: object) -> list[str]:
    if isinstance(value, str):
        raw_items = [value]
    else:
        raw_items = list(value or [])

    enabled: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        channel = _normalize_channel(item)
        if channel in seen:
            continue
        enabled.append(channel)
        seen.add(channel)
    return enabled


def _normalize_channel(value: object) -> str:
    channel = str(value or "").strip().lower()
    if channel not in SUPPORTED_NOTIFY_CHANNELS:
        supported = ", ".join(sorted(SUPPORTED_NOTIFY_CHANNELS))
        raise ValueError(f"不支持的通知渠道 {value!r}，当前支持: {supported}")
    return channel


__all__ = [
    "NotifyChannel",
    "SUPPORTED_NOTIFY_CHANNELS",
    "build_notifier",
    "load_notify_settings",
    "send_configured_notifications",
]
