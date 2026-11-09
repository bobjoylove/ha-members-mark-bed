"""Local XLink UDP client for the Member's Mark WiFi adjustable base.

Protocol reconstructed from packet captures of the Member's Mark Base WiFi app:
  0x23 handshake (access key)  -> 0x2b reply carrying a 2-byte session id
  0x33 / 0x73 session setup
  0x83 "pipe" frames carry the bed command / status, 0x8b acknowledges them
  0xd0 keepalive -> 0xdb reply
Commands are Keeson remote key codes (32-bit, little endian). Holding a button
means re-sending its code every ~100 ms; sending 0 releases it.
"""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

PORT = 5987
HOLD_INTERVAL = 0.1
KEEPALIVE_INTERVAL = 10
STATUS_POLL_INTERVAL = 3   # background status refresh (picks up remote/app changes)
SESSION_TIMEOUT = 35
MAX_HOLD_SECONDS = 40

KEY_HEAD_UP = 0x00000001
KEY_HEAD_DOWN = 0x00000002
KEY_FOOT_UP = 0x00000004
KEY_FOOT_DOWN = 0x00000008
KEY_MASSAGE_STEP = 0x00000100
KEY_MASSAGE_TIMER = 0x00000200
KEY_MASSAGE_FOOT = 0x00000400
KEY_MASSAGE_HEAD = 0x00000800
KEY_ZERO_G = 0x00001000
KEY_MEMORY_1 = 0x00002000   # app button I
KEY_MEMORY_2 = 0x00004000   # app button II
SAVE_HOLD_SECONDS = 6       # long-press a preset this long to store the current position
KEY_MEMORY_3 = 0x00008000   # app button III
KEY_MEMORY_4 = 0x00010000   # app button M
KEY_LIGHT = 0x00020000
KEY_MASSAGE_OFF = 0x02000000
KEY_MASSAGE_PATTERN = 0x04000000   # app "wave" button: starts massage / cycles 4 patterns
KEY_FLAT = 0x08000000
KEY_MASSAGE_WAVE = 0x10000000


def _frame(ptype: int, payload: bytes) -> bytes:
    return bytes([ptype]) + struct.pack(">I", len(payload)) + payload


def _inner(key: int) -> bytes:
    k = struct.pack("<I", key)
    checksum = (0xEDFA - sum(k)) & 0xFFFF
    return bytes.fromhex("aa03000f000000000100000401") + k + struct.pack("<H", checksum) + b"\x55"


def parse_status(data: bytes) -> dict | None:
    """Parse a 0x83 status frame from the bed. Returns None if not a status frame."""
    if not data or data[0] != 0x83:
        return None
    j = data.find(b"\xaa\x83")
    if j < 0 or len(data) < j + 17:
        return None
    inner = data[j:]
    if len(inner) < 28:
        return None
    remaining = int.from_bytes(inner[20:23], "little") // 100
    timer = inner[25]
    # Byte 25 also reads 01 while a preset is being saved, so only trust it
    # as a massage timer when massage time is actually counting down.
    if remaining == 0:
        timer = 0xFF
    return {
        "head_raw": int.from_bytes(inner[13:15], "little"),
        "foot_raw": int.from_bytes(inner[15:17], "little"),
        "massage_head": inner[17],          # 0 = off, then intensity level
        "massage_foot": inner[18],
        # remaining massage time, 3 bytes LE in 10 ms units
        "massage_remaining": remaining,
        "massage_timer": None if timer == 0xFF else timer,   # 1/2/3 = 10/20/30 min
        "massage_pattern": inner[27],       # 0-3, cycled by the app's wave button
        "light": bool(inner[24] & 0x40),
        "raw": inner.hex(),
    }


class BedConnectionError(Exception):
    """Could not reach or authenticate with the bed."""


class _Proto(asyncio.DatagramProtocol):
    def __init__(self, client: "BedClient") -> None:
        self.client = client

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        self.client._on_datagram(data)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("UDP error: %s", exc)


class BedClient:
    """Async client. One instance per bed."""

    def __init__(self, host: str, access_key: bytes, port: int = PORT) -> None:
        if len(access_key) != 16:
            raise ValueError("access key must be 16 bytes")
        self.host = host
        self.port = port
        self.key = access_key
        self.session: bytes | None = None
        self.device_id: str | None = None
        self.status: dict = {}
        self._transport: asyncio.DatagramTransport | None = None
        self._msg = 0x0D
        self._handshake_fut: asyncio.Future | None = None
        self._last_rx = 0.0
        self._lock = asyncio.Lock()
        self._hold_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._listeners: list[Callable[[], None]] = []

    # ---------- listeners ----------
    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("listener failed")

    @property
    def connected(self) -> bool:
        return self.session is not None and (time.monotonic() - self._last_rx) < SESSION_TIMEOUT

    # ---------- connection ----------
    async def connect(self) -> None:
        async with self._lock:
            await self._connect_locked()

    async def _connect_locked(self) -> None:
        loop = asyncio.get_running_loop()
        if self._transport is None:
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _Proto(self), remote_addr=(self.host, self.port)
            )
        self.session = None
        for attempt in range(3):
            self._handshake_fut = loop.create_future()
            self._send(_frame(0x23, b"\x03\x02\x0b" + self.key + bytes.fromhex("006300001e")))
            try:
                await asyncio.wait_for(self._handshake_fut, 2)
                break
            except asyncio.TimeoutError:
                _LOGGER.debug("handshake attempt %s timed out", attempt + 1)
        else:
            raise BedConnectionError(f"no handshake reply from {self.host}")
        self._send(_frame(0x33, self.session + b"\x00"))
        self._send(_frame(0x73, b"\x03\x02\x0c" + self.key + b"\x00"))
        await asyncio.sleep(0.3)
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = loop.create_task(self._keepalive())
        _LOGGER.debug("connected to %s session %s", self.host, self.session.hex())
        self._notify()

    async def ensure_connected(self) -> None:
        if not self.connected:
            async with self._lock:
                if not self.connected:
                    await self._connect_locked()

    @property
    def _holding(self) -> bool:
        return self._hold_task is not None and not self._hold_task.done()

    def _poll_once(self) -> None:
        """Ask for a status frame. The bed only reports status in reply to a
        command frame, so send 'no button' (as the app does while idle).
        Skipped during a hold, where it would release the button."""
        if self.session is not None and not self._holding:
            self._send_key(0)

    async def refresh(self, seconds: float = 0.4, interval: float = 0.2) -> None:
        """Poll status for a short while (e.g. right after a button press)."""
        end = time.monotonic() + seconds
        while True:
            self._poll_once()
            await asyncio.sleep(interval)
            if time.monotonic() >= end:
                return

    async def _keepalive(self) -> None:
        last_ping = time.monotonic()
        while True:
            await asyncio.sleep(STATUS_POLL_INTERVAL)
            try:
                self._poll_once()
                if self.session is not None and time.monotonic() - last_ping >= KEEPALIVE_INTERVAL:
                    self._send(_frame(0xD0, self.session))
                    last_ping = time.monotonic()
                if not self.connected:
                    await self.ensure_connected()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("keepalive/reconnect failed: %s", err)
                self._notify()

    async def close(self) -> None:
        for task in (self._hold_task, self._keepalive_task):
            if task:
                task.cancel()
        if self._transport:
            self._transport.close()
            self._transport = None
        self.session = None

    def _send(self, data: bytes) -> None:
        if self._transport is not None:
            self._transport.sendto(data)

    def _on_datagram(self, data: bytes) -> None:
        if not data:
            return
        self._last_rx = time.monotonic()
        ptype = data[0]
        if ptype == 0x2B and len(data) >= 8:
            self.session = data[-3:-1]
            self.device_id = data[9:17].hex()
            if self._handshake_fut and not self._handshake_fut.done():
                self._handshake_fut.set_result(True)
        elif ptype == 0x83:
            st = parse_status(data)
            if st and st != self.status:
                self.status = st
                self._notify()

    # ---------- commands ----------
    def _send_key(self, key: int) -> None:
        payload = self.session + b"\x02" + struct.pack("<H", self._msg) + _inner(key)
        self._msg = (self._msg + 1) & 0xFFFF
        self._send(_frame(0x83, payload))

    async def press(self, key: int, repeats: int = 3) -> None:
        """Tap a button (presets, light)."""
        await self.stop()
        await self.ensure_connected()
        for _ in range(repeats):
            self._send_key(key)
            await asyncio.sleep(HOLD_INTERVAL)
        await self._release()

    async def start_hold(
        self,
        key: int,
        seconds: float = MAX_HOLD_SECONDS,
        until: Callable[[], bool] | None = None,
    ) -> None:
        """Hold a motor button until stop(), timeout, or `until()` returns True."""
        await self.stop()
        await self.ensure_connected()
        self._hold_task = asyncio.get_running_loop().create_task(
            self._hold(key, min(seconds, MAX_HOLD_SECONDS), until)
        )

    async def _hold(self, key: int, seconds: float, until) -> None:  # noqa: ANN001
        end = time.monotonic() + seconds
        try:
            while time.monotonic() < end:
                if until is not None and until():
                    break
                self._send_key(key)
                await asyncio.sleep(HOLD_INTERVAL)
        finally:
            await self._release()

    async def hold_for(self, key: int, seconds: float) -> None:
        """Hold a button for a fixed time and wait for it (e.g. long-press to save a preset)."""
        await self.start_hold(key, seconds)
        task = self._hold_task
        if task:
            await task

    async def stop(self) -> None:
        task, self._hold_task = self._hold_task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _release(self) -> None:
        if self.session is None:
            return
        for _ in range(3):
            self._send_key(0)
            await asyncio.sleep(HOLD_INTERVAL)
