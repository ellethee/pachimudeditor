"""Client asincrono del canale live (protocollo `livectl` v1), riusabile dagli adapter (SDK 1.5).

Una sola connessione per canale (un `LiveClient` per mondo): socket Unix, una riga JSON per messaggio, `hello` con il token, richieste
serializzate da un lock, riconnessione pigra a ogni richiesta (il MUD puo' essere spento o riavviato). Regole:

- il token viene chiesto a un callable a ogni connessione (variabile d'ambiente: nessuna copia a lungo termine) e **non** compare mai in
  log, eccezioni o `repr`; il percorso del socket nemmeno nei messaggi;
- i limiti di `hello` (`max_line` per le richieste, `max_response` per le risposte) sono rispettati: una richiesta o una risposta troppo
  grande e' un errore locale e la connessione si chiude;
- le letture si ritentano una volta se la connessione era caduta; le scritture **mai** dopo l'invio: timeout o caduta dopo l'invio sono
  `outcome_unknown` (il chiamante deve rileggere prima di ripetere);
- un comando non dichiarato in `hello` non viene inviato (`command_disabled`).
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pachimudeditor.common.adapters.live import (
    LiveApplied,
    LiveEchoIn,
    LiveEchoOut,
    LiveError,
    LiveInventory,
    LiveItem,
    LiveItemExpect,
    LiveItemRemoveOut,
    LiveItemSetIn,
    LiveItemSetOut,
    LiveLoadIn,
    LiveLoadOut,
    LivePlayerSetIn,
    LivePlayerSetOut,
    LivePlayerState,
    LiveServerInfo,
    LiveStatus,
    LiveWho,
    LiveZone,
    LiveZoneResetIn,
    LiveZoneResetOut,
    LiveZones,
    http_error,
)

log = logging.getLogger(__name__)

PROTOCOL = 1
DEFAULT_MAX_LINE = 4096
DEFAULT_MAX_RESPONSE = 65536
READ_LIMIT = 1 << 20
"""Tetto assoluto di una riga letta (protezione da un server che non manda mai `\\n`), oltre il `max_response` dichiarato."""
IDLE_RECONNECT_S = 240.0
"""Oltre questo tempo senza richieste si riapre la connessione prima di una scrittura (il MUD chiude dopo 300 s di inattivita')."""
CLIENT_NAME = "pachimudeditor"


@dataclass(frozen=True)
class LiveSession:
    """Cio' che il MUD ha dichiarato in `hello`."""

    protocol: int
    mud: dict[str, Any]
    max_line: int
    max_response: int
    features: list[str]
    commands: dict[str, dict[str, Any]]

    @property
    def classes(self) -> list[str]:
        """Classi di comandi attive (`read`, `write`)."""
        return sorted({str(c.get("class")) for c in self.commands.values() if c.get("class")})

    def fields(self, command: str) -> list[str]:
        """Campi dichiarati per un comando (`player.set`, `player.get`)."""
        return [str(f) for f in self.commands.get(command, {}).get("fields", [])]


@dataclass
class _Conn:
    """Una connessione autenticata."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    session: LiveSession
    actor: str
    next_id: int = 1
    last_used: float = field(default_factory=time.monotonic)


class _Lost(Exception):
    """Connessione persa o in timeout durante uno scambio; `sent` dice se la richiesta e' stata scritta per intero."""

    def __init__(self, sent: bool, timeout: bool) -> None:
        """Memorizza se la richiesta e' partita e se la causa e' un timeout."""
        super().__init__("connessione persa")
        self.sent, self.timeout = sent, timeout


class LiveClient:
    """Client di un canale `livectl`. `token` e' un callable (di solito `lambda: os.environ.get(NOME)`): `None` o vuoto = `token_missing`."""

    def __init__(
        self,
        socket_path: str,
        token: Callable[[], str | None],
        *,
        timeout: float = 3.0,
        default_actor: str = CLIENT_NAME,
    ) -> None:
        """Non apre nulla: la connessione nasce alla prima richiesta."""
        self._path, self._token, self.timeout, self._default_actor = socket_path, token, timeout, default_actor
        self._lock = asyncio.Lock()
        self._conn: _Conn | None = None

    def __repr__(self) -> str:
        """Senza token ne' percorso."""
        return f"<LiveClient connected={self._conn is not None}>"

    # ------------------------------------------------------------------ connessione

    async def close(self) -> None:
        """Chiude la connessione (se aperta)."""
        async with self._lock:
            await self._drop()

    async def _drop(self) -> None:
        """Chiude e dimentica la connessione corrente."""
        conn, self._conn = self._conn, None
        if conn is not None:
            conn.writer.close()
            try:
                await asyncio.wait_for(conn.writer.wait_closed(), 1.0)
            except OSError, TimeoutError:
                pass

    async def _read_line(self, reader: asyncio.StreamReader, limit: int) -> dict[str, Any]:
        """Una risposta: riga JSON entro `limit` byte. Alza `_Lost` (EOF/timeout) o `LiveError` (riga troppo grande, JSON non valido)."""
        try:
            raw = await asyncio.wait_for(reader.readline(), self.timeout)
        except TimeoutError:
            raise _Lost(True, True) from None
        except ValueError, asyncio.LimitOverrunError:
            raise LiveError("response_too_large", "risposta oltre il limite") from None
        except OSError:
            raise _Lost(True, False) from None
        if not raw.endswith(b"\n"):
            raise _Lost(True, False)  # EOF a meta' riga
        if len(raw.rstrip(b"\r\n")) > limit:
            raise LiveError("response_too_large", "risposta oltre il limite")
        try:
            msg = json.loads(raw)
        except ValueError:
            raise LiveError("protocol_error", "risposta non JSON") from None
        if not isinstance(msg, dict):
            raise LiveError("protocol_error", "risposta non valida")
        return msg

    async def _connect(self, actor: str) -> _Conn:
        """Apre il socket e fa `hello`. `unreachable`, `token_missing`, `auth_failed`, `protocol_unsupported`, `timeout`."""
        token = self._token()
        if not token:
            raise LiveError("token_missing", "variabile del token non impostata")
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(self._path, limit=READ_LIMIT), self.timeout)
        except TimeoutError:
            raise LiveError("unreachable", "connessione al canale in timeout") from None
        except OSError:
            raise LiveError("unreachable", "canale non raggiungibile") from None
        hello = {"id": 1, "cmd": "hello", "params": {"protocols": [PROTOCOL], "token": token, "client": CLIENT_NAME, "actor": actor[:64]}}
        try:
            writer.write(json.dumps(hello, separators=(",", ":")).encode() + b"\n")
            await asyncio.wait_for(writer.drain(), self.timeout)
            msg = await self._read_line(reader, DEFAULT_MAX_RESPONSE)
        except _Lost as lost:
            writer.close()
            raise LiveError("timeout" if lost.timeout else "unreachable", "handshake non completato") from None
        except OSError, TimeoutError:
            writer.close()
            raise LiveError("unreachable", "handshake non completato") from None
        except LiveError:
            writer.close()
            raise
        if msg.get("ok") is not True:
            writer.close()
            error = msg.get("error") if isinstance(msg.get("error"), dict) else {}
            code = str(error.get("code", "protocol_error"))
            params = error.get("params") if isinstance(error.get("params"), dict) else {}
            raise LiveError(code if code in ("auth_failed", "protocol_unsupported", "rate_limited", "too_many_connections") else "protocol_error",
                            "hello rifiutato", **params)  # fmt: skip
        result = msg.get("result") if isinstance(msg.get("result"), dict) else {}
        limits = result.get("limits") if isinstance(result.get("limits"), dict) else {}
        commands = result.get("commands") if isinstance(result.get("commands"), dict) else {}
        session = LiveSession(
            protocol=int(result.get("protocol", PROTOCOL)),
            mud=result.get("mud") if isinstance(result.get("mud"), dict) else {},
            max_line=int(limits.get("max_line", DEFAULT_MAX_LINE)),
            max_response=int(limits.get("max_response", DEFAULT_MAX_RESPONSE)),
            features=[str(f) for f in result.get("features", []) if isinstance(f, str)],
            commands={k: v for k, v in commands.items() if isinstance(v, dict)},
        )
        return _Conn(reader, writer, session, actor, next_id=2)

    async def _ensure(self, actor: str | None, *, write: bool) -> _Conn:
        """La connessione da usare: quella aperta se valida, altrimenti una nuova. Una scrittura con un `actor` diverso da quello della
        connessione la riapre (l'audit del MUD registra l'attore dell'`hello`); le letture non lo cambiano."""
        conn = self._conn
        if conn is not None:
            stale = conn.reader.at_eof() or conn.writer.is_closing()
            if write and time.monotonic() - conn.last_used > IDLE_RECONNECT_S:
                stale = True
            if write and actor and actor != conn.actor:
                stale = True
            if stale:
                await self._drop()
                conn = None
        if conn is None:
            conn = self._conn = await self._connect(actor or self._default_actor)
        return conn

    # ------------------------------------------------------------------ richieste

    async def _exchange(self, conn: _Conn, cmd: str, params: dict[str, Any] | None) -> Any:
        """Una richiesta e la sua risposta sulla connessione `conn`."""
        rid = conn.next_id
        conn.next_id += 1
        msg: dict[str, Any] = {"id": rid, "cmd": cmd}
        if params is not None:
            msg["params"] = params
        line = json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
        if len(line) - 1 > conn.session.max_line:
            raise LiveError("request_too_large", "richiesta oltre max_line")
        try:
            conn.writer.write(line)
            await asyncio.wait_for(conn.writer.drain(), self.timeout)
        except OSError, TimeoutError:
            raise _Lost(False, False) from None
        reply = await self._read_line(conn.reader, conn.session.max_response)
        conn.last_used = time.monotonic()
        if reply.get("id") != rid:
            raise LiveError("protocol_error", "risposta con id inatteso")
        if reply.get("ok") is True:
            return reply.get("result")
        error = reply.get("error") if isinstance(reply.get("error"), dict) else {}
        params_in = error.get("params") if isinstance(error.get("params"), dict) else {}
        raise LiveError(str(error.get("code", "protocol_error")), str(error.get("message", ""))[:200], **params_in)

    async def call(self, cmd: str, params: dict[str, Any] | None = None, *, actor: str | None = None, write: bool = False) -> Any:
        """Esegue un comando e restituisce `result`. Alza `LiveError`.

        `write=True` per i comandi di classe `write` (mai ritentati dopo l'invio, `actor` registrato nell'audit del MUD).
        """
        async with self._lock:
            for attempt in (0, 1):
                conn = await self._ensure(actor, write=write)
                if cmd not in conn.session.commands:
                    raise LiveError("command_disabled", "comando non dichiarato dal MUD")
                try:
                    return await self._exchange(conn, cmd, params)
                except _Lost as lost:
                    await self._drop()
                    if lost.sent and write:
                        raise LiveError("outcome_unknown", "connessione persa dopo l'invio") from None
                    if lost.timeout:
                        raise LiveError("timeout", "nessuna risposta dal MUD") from None
                    if attempt == 1:
                        raise LiveError("unreachable", "connessione caduta") from None
                except LiveError as error:
                    if error.code in ("response_too_large", "protocol_error"):
                        await self._drop()  # non ci si puo' risincronizzare
                    raise
        raise AssertionError("irraggiungibile")  # pragma: no cover

    async def session(self) -> LiveSession:
        """La sessione corrente (apre la connessione se serve): per conoscere comandi e limiti."""
        async with self._lock:
            return (await self._ensure(None, write=False)).session

    # ------------------------------------------------------------------ comandi tipizzati

    async def status(self) -> LiveStatus:
        """`hello` + `ping`: mai un'eccezione, lo stato dice cosa non va."""
        started = time.monotonic()
        try:
            await self.call("ping")
            session = await self.session()
        except LiveError as error:
            state = {"unreachable": "unreachable", "timeout": "unreachable", "auth_failed": "auth_failed", "token_missing": "token_missing"}
            return LiveStatus(state=state.get(error.code, "error"), code=http_error(error).detail[0]["code"])  # type: ignore[index]
        return LiveStatus(
            state="connected",
            reachable=True,
            protocol=session.protocol,
            mud=session.mud,
            classes=session.classes,
            commands=sorted(session.commands),
            features=session.features,
            editable_fields=session.fields("player.set"),
            latency_ms=round((time.monotonic() - started) * 1000),
        )

    async def who(self) -> LiveWho:
        """`who` (al massimo 200 voci, link morti compresi)."""
        result = await self.call("who", {"limit": 200, "linkdead": True})
        return LiveWho.model_validate(result or {})

    async def info(self) -> LiveServerInfo:
        """`info`."""
        return LiveServerInfo.model_validate(await self.call("info") or {})

    async def zones(self) -> LiveZones:
        """`zone.list`."""
        return LiveZones(zones=[LiveZone.model_validate(z) for z in (await self.call("zone.list") or {}).get("zones", [])])

    async def player_get(self, name: str) -> LivePlayerState:
        """`player.get`."""
        result = await self.call("player.get", {"name": name}) or {}
        session = await self.session()
        return LivePlayerState(
            name=result.get("name", name), state=result.get("state", "playing"), fields=result.get("fields", {}),
            editable_fields=session.fields("player.set"),
        )  # fmt: skip

    async def player_set(self, name: str, change: LivePlayerSetIn, *, actor: str | None = None) -> LivePlayerSetOut:
        """`player.set` (scrittura)."""
        params = {"name": name, "set": change.fields, "save": change.save, "confirm_immortal": change.confirm_immortal}
        result = await self.call("player.set", params, actor=actor, write=True) or {}
        return LivePlayerSetOut(
            name=result.get("name", name),
            applied={k: LiveApplied.model_validate(v) for k, v in result.get("applied", {}).items() if isinstance(v, dict)},
            saved=bool(result.get("saved")),
            warnings=[str(w) for w in result.get("warnings", [])],
        )

    async def zone_reset(self, reset: LiveZoneResetIn, *, actor: str | None = None) -> LiveZoneResetOut:
        """`zone.reset` (scrittura)."""
        params: dict[str, Any] = {"only_if_empty": reset.only_if_empty}
        params["zone" if reset.zone is not None else "room"] = reset.zone if reset.zone is not None else reset.room
        return LiveZoneResetOut.model_validate(await self.call("zone.reset", params, actor=actor, write=True) or {})

    async def load(self, kind: Literal["mob", "obj"], load: LiveLoadIn, *, actor: str | None = None) -> LiveLoadOut:
        """`load.mob` / `load.obj` (scrittura)."""
        params: dict[str, Any] = {"vnum": load.vnum, "count": load.count, "notify": load.notify}
        if load.room is not None:
            params["room"] = load.room
        else:
            params["player"] = load.player
        return LiveLoadOut.model_validate(await self.call(f"load.{kind}", params, actor=actor, write=True) or {})

    async def inventory(self, name: str) -> LiveInventory:
        """`player.inventory` (feature `inventory`)."""
        return LiveInventory.model_validate(await self.call("player.inventory", {"name": name}) or {})

    async def item_get(self, name: str, ref: str) -> LiveItem:
        """`obj.get`."""
        return LiveItem.model_validate((await self.call("obj.get", {"name": name, "ref": ref}) or {}).get("item") or {})

    async def item_set(self, name: str, ref: str, change: LiveItemSetIn, *, actor: str | None = None) -> LiveItemSetOut:
        """`obj.set` (scrittura): solo i campi presenti nella patch."""
        changes: dict[str, Any] = {k: getattr(change.set, k) for k in change.set.model_fields_set}
        if "affects" in changes:
            changes["affects"] = [None if a is None else a.model_dump() for a in changes["affects"]]
        params = {"name": name, "ref": ref, "expect": change.expect.model_dump(), "save": change.save, "set": changes}
        return LiveItemSetOut.model_validate(await self.call("obj.set", params, actor=actor, write=True) or {})

    async def item_remove(
        self, name: str, ref: str, expect: LiveItemExpect, *, save: bool = True, actor: str | None = None
    ) -> LiveItemRemoveOut:
        """`obj.remove` (scrittura)."""
        params = {"name": name, "ref": ref, "expect": expect.model_dump(), "save": save}
        return LiveItemRemoveOut.model_validate(await self.call("obj.remove", params, actor=actor, write=True) or {})

    async def echo(self, echo: LiveEchoIn, *, actor: str | None = None) -> LiveEchoOut:
        """`echo` (scrittura)."""
        to: dict[str, Any] = {"all": True} if echo.all else {"player": echo.player} if echo.player is not None else {"room": echo.room}
        return LiveEchoOut.model_validate(await self.call("echo", {"text": echo.text, "to": to}, actor=actor, write=True) or {})


__all__ = ["CLIENT_NAME", "LiveClient", "LiveSession"]
