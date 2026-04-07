from __future__ import annotations

import asyncio
import threading

from quant_balance.api.routes import ws


def test_notify_event_schedules_broadcast_on_background_loop(
    monkeypatch,
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []
    delivered = threading.Event()

    async def fake_broadcast(
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        seen.append((event_type, payload))
        delivered.set()

    monkeypatch.setattr(ws, "broadcast_event", fake_broadcast)

    loop = asyncio.new_event_loop()
    thread = threading.Thread(
        target=_run_loop,
        args=(loop,),
        daemon=True,
    )
    thread.start()

    try:
        monkeypatch.setattr(ws, "_event_loop", loop)
        ws.notify_event("scan_complete", {"scan_id": "scan-1"})
        assert delivered.wait(timeout=1.0)
        assert seen == [("scan_complete", {"scan_id": "scan-1"})]
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1.0)
        loop.close()
        monkeypatch.setattr(ws, "_event_loop", None)


def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()
