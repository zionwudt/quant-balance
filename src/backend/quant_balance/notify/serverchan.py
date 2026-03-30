"""Server酱通知。"""

from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from quant_balance.notify.base import Notifier


class ServerChanNotifier(Notifier):
    """Server酱通知。"""

    channel = "serverchan"

    def __init__(self, sendkey: str) -> None:
        self.sendkey = str(sendkey or "").strip()
        if not self.sendkey:
            raise ValueError("notify.serverchan.sendkey 未配置。")

    def send(self, title: str, content: str) -> bool:
        request = Request(
            f"https://sctapi.ftqq.com/{self.sendkey}.send",
            data=urlencode({"title": title, "desp": content}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(request, timeout=10) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body or "{}")
        return int(data.get("code", -1)) == 0
