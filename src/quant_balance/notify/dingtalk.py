"""钉钉机器人通知。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from quant_balance.notify.base import Notifier


class DingTalkNotifier(Notifier):
    """钉钉机器人通知。"""

    channel = "dingtalk"

    def __init__(self, webhook: str, *, secret: str | None = None) -> None:
        self.webhook = str(webhook or "").strip()
        self.secret = str(secret or "").strip()
        if not self.webhook:
            raise ValueError("notify.dingtalk.webhook 未配置。")

    def send(self, title: str, content: str) -> bool:
        payload = {
            "msgtype": "text",
            "text": {
                "content": f"{title}\n{content}",
            },
        }
        request = Request(
            self._signed_webhook(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body or "{}")
        return int(data.get("errcode", -1)) == 0

    def _signed_webhook(self) -> str:
        if not self.secret:
            return self.webhook

        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        digest = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
        separator = "&" if "?" in self.webhook else "?"
        return f"{self.webhook}{separator}timestamp={timestamp}&sign={sign}"
