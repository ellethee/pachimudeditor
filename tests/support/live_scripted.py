"""Server `livectl` scriptato per i test: fa `hello` e poi lascia decidere a una funzione, cosi' puo' sbagliare apposta (silenzio, caduta, righe enormi)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

Behavior = Callable[[int, dict[str, Any], asyncio.StreamWriter], Awaitable[bool]]


class Scripted:
    """Server che fa `hello` e poi lascia decidere a `behavior(n_connessione, richiesta, writer)`; True = chiudi la connessione."""

    def __init__(self, path: Path, behavior: Behavior, *, limits: dict[str, int] | None = None) -> None:
        """Prepara il server (non lo avvia)."""
        self.path, self.behavior, self.limits = path, behavior, limits or {}
        self.connections = 0
        self.requests: list[dict[str, Any]] = []
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        """Apre il socket."""
        self._server = await asyncio.start_unix_server(self._handle, path=str(self.path))

    async def stop(self) -> None:
        """Chiude il server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Una connessione."""
        self.connections += 1
        n = self.connections
        try:
            while line := await reader.readline():
                req = json.loads(line)
                if req["cmd"] == "hello":
                    result = {"protocol": 1, "mud": {"kind": "t"}, "features": [], "commands": {c: {"class": "read"} for c in ("ping", "who")}
                              | {c: {"class": "write"} for c in ("echo", "player.set")}, "limits": self.limits}  # fmt: skip
                    writer.write(json.dumps({"id": req["id"], "ok": True, "result": result}).encode() + b"\n")
                    await writer.drain()
                    continue
                self.requests.append(req)
                if await self.behavior(n, req, writer):
                    break
        finally:
            writer.close()


async def answer(writer: asyncio.StreamWriter, req: dict[str, Any], result: Any = None) -> None:
    """Risposta di successo."""
    writer.write(json.dumps({"id": req["id"], "ok": True, "result": result or {}}).encode() + b"\n")
    await writer.drain()
