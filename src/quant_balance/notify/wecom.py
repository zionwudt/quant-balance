"""企业微信机器人通知。"""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from quant_balance.notify.base import Notifier


class WecomNotifier(Notifier):
    """企业微信机器人通知。"""

    channel = "wecom"

    def __init__(self, webhook: str) -> None:
        self.webhook = str(webhook or "").strip()
        if not self.webhook:
            raise ValueError("notify.wecom.webhook 未配置。")

    def send(self, title: str, content: str) -> bool:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n\n{content.replace(chr(10), '<br/>')}",
            },
        }
        request = Request(
            self.webhook,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body or "{}")
        return int(data.get("errcode", -1)) == 0
