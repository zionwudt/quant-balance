"""通知发送抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    """通知发送器抽象基类。"""

    channel: str

    @abstractmethod
    def send(self, title: str, content: str) -> bool:
        """发送通知，成功返回 True。"""
