"""Client asincrono minimo del canale live (`livectl`) per i test: righe JSON su socket Unix."""

from __future__ import annotations

import asyncio
import json
from typing import Any


class LiveClient:
    """Una connessione: `connect`, `hello`, `call`. Non nasconde gli errori: `call` restituisce la risposta intera."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Avvolge i flussi gia' aperti."""
        self.reader, self.writer, self._id = reader, writer, 0

    @classmethod
    async def connect(cls, path: str) -> LiveClient:
        """Apre il socket Unix."""
        reader, writer = await asyncio.open_unix_connection(path, limit=2**20)
        return cls(reader, writer)

    async def send_raw(self, data: bytes) -> None:
        """Scrive byte grezzi (per i test di input malformato)."""
        self.writer.write(data)
        await self.writer.drain()

    async def read(self, timeout: float = 10.0) -> dict[str, Any] | None:
        """Legge una risposta; `None` se la connessione e' chiusa."""
        line = await asyncio.wait_for(self.reader.readline(), timeout)
        return json.loads(line) if line else None

    async def call(self, cmd: str, params: dict[str, Any] | None = None, *, timeout: float = 10.0, retries: int = 30) -> dict[str, Any]:
        """Invia una richiesta e legge la risposta (la prima: le richieste sono in ordine). Su `rate_limited` aspetta e ripete (`retries`)."""
        for _ in range(retries + 1):
            self._id += 1
            msg: dict[str, Any] = {"id": self._id, "cmd": cmd}
            if params is not None:
                msg["params"] = params
            await self.send_raw(json.dumps(msg).encode() + b"\n")
            resp = await self.read(timeout)
            assert resp is not None, "connessione chiusa dal server"
            assert resp["id"] == self._id, (cmd, params, resp)
            if resp.get("ok") or resp["error"]["code"] != "rate_limited":
                return resp
            await asyncio.sleep(resp["error"].get("params", {}).get("retry_after_ms", 100) / 1000)
        return resp

    async def hello(self, token: str, actor: str = "test") -> dict[str, Any]:
        """`hello` con il token."""
        return await self.call("hello", {"protocols": [1], "token": token, "client": "pytest", "actor": actor})

    async def closed(self, timeout: float = 5.0) -> bool:
        """True se il server chiude la connessione entro `timeout`."""
        try:
            return await asyncio.wait_for(self.reader.read(), timeout) == b"" or True
        except TimeoutError:
            return False

    async def close(self) -> None:
        """Chiude la connessione."""
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except OSError:
            pass
