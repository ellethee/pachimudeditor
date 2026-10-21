"""Finto server del canale live (protocollo `livectl` v1): asyncio, socket Unix, nessun MUD.

Serve a due cose: provare l'editor (client, adapter) senza un MUD acceso e fare da riferimento eseguibile per i test di conformita'
(`tests/live/`), che si possono puntare anche al modulo C reale. Implementa gli stessi comandi, errori e limiti del modulo
(`docs/backend/live-control-protocol.md`) su un mondo in memoria.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import re
import time
from pathlib import Path
from typing import Any

MAX_LINE = 4096
MAX_TEXT = 400
RATE_PER_SEC = 20
CLASS_NAMES = ("magic_user", "cleric", "warrior", "thief", "druid", "monk", "barbarian", "sorcerer", "paladin", "ranger", "psi")
DENY_OBJ = ((150, 199), (1600, 1600), (5311, 5311), (13702, 13702), (21113, 21113), (21117, 21117), (21120, 21122))
# nome del campo -> (minimo, massimo)
SCALARS: dict[str, tuple[int, int]] = {
    "gold": (0, 2**31 - 1), "bankGold": (0, 2**31 - 1), "exp": (0, 2**31 - 1), "alignment": (-1000, 1000),
    "hit": (1, 32767), "mana": (0, 32767), "move": (0, 32767), "spellsToLearn": (0, 127),
    "str": (0, 25), "strAdd": (0, 100), "int": (0, 25), "wis": (0, 25), "dex": (0, 25), "con": (0, 25), "chr": (0, 25),
}  # fmt: skip
CONDITIONS = ("drunk", "full", "thirst")
READ_COMMANDS = ("ping", "info", "who", "player.get", "zone.list")
WRITE_COMMANDS = ("player.set", "zone.reset", "load.mob", "load.obj", "echo")
ZONES = [  # (index, num, name, top)
    (0, 1, "Scratch Zone", 0), (1, 2, "LIMBO", 49), (2, 3, "Temple", 199), (3, 14, "Midgaard", 3999), (4, 15, "Altrove", 9999),
]  # fmt: skip
CMD_RE = re.compile(r"[a-z]+(\.[a-z]+)*")
PROTECTED_FIELDS = ("maxHit", "maxMana", "maxMove", "race", "sex", "roomVnum")


class Err(Exception):
    """Errore di protocollo con codice stabile."""

    def __init__(self, code: str, message: str = "", **params: Any) -> None:
        """Memorizza codice, messaggio e parametri."""
        super().__init__(code)
        self.code, self.message, self.params = code, message or code, params


def _check_keys(obj: dict[str, Any], allowed: tuple[str, ...]) -> None:
    """Rifiuta chiavi sconosciute (il server e' severo)."""
    for k in obj:
        if k not in allowed:
            raise Err("bad_params", "parametro sconosciuto", field=k)


def _int(obj: dict[str, Any], key: str, required: bool = True) -> int | None:
    """Legge un intero (non bool) da `obj`."""
    if key not in obj:
        if required:
            raise Err("bad_params", "parametro mancante", field=key)
        return None
    v = obj[key]
    if isinstance(v, bool) or not isinstance(v, int):
        raise Err("bad_params", "tipo non valido", field=key)
    return v


def _str(obj: dict[str, Any], key: str, required: bool = True) -> str | None:
    """Legge una stringa da `obj`."""
    if key not in obj:
        if required:
            raise Err("bad_params", "parametro mancante", field=key)
        return None
    if not isinstance(obj[key], str):
        raise Err("bad_params", "tipo non valido", field=key)
    return obj[key]


def _bool(obj: dict[str, Any], key: str, default: bool) -> bool:
    """Legge un booleano facoltativo."""
    if key not in obj:
        return default
    if not isinstance(obj[key], bool):
        raise Err("bad_params", "tipo non valido", field=key)
    return obj[key]


def _dup_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Hook di `json.loads`: chiavi duplicate vietate."""
    d: dict[str, Any] = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate key")
        d[k] = v
    return d


def _no_float(_: str) -> Any:
    """Hook di `json.loads`: solo interi."""
    raise ValueError("not an integer")


class FakeLiveServer:
    """Server `livectl` su socket Unix con mondo in memoria."""

    def __init__(self, path: str | Path, token: str, *, write: bool = True, max_conn: int = 4, hello_timeout: float = 5.0) -> None:
        """Prepara lo stato; `start()` apre il socket."""
        self.path, self.token, self.write, self.max_conn, self.hello_timeout = str(path), token, write, max_conn, hello_timeout
        self.audit: list[str] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.echoes: list[tuple[str, str]] = []
        self.loaded: list[dict[str, Any]] = []
        self.resets: list[int] = []
        self.saves: list[str] = []
        self.started_at = int(time.time())
        self._server: asyncio.AbstractServer | None = None
        self._conns = 0
        self._next_conn = 0
        self._fail_times: list[float] = []
        self._lock_until = 0.0
        self.players: dict[str, dict[str, Any]] = {
            "tester": self._new_player("Tester", {"cleric": 3}, "playing"),
            "ghost": self._new_player("Ghost", {"warrior": 10}, "linkdead"),
        }

    @staticmethod
    def _new_player(name: str, levels: dict[str, int], state: str) -> dict[str, Any]:
        """Giocatore di prova con valori plausibili."""
        fields = {k: lo for k, (lo, _hi) in SCALARS.items()}
        fields.update(gold=150, exp=3000, hit=46, mana=135, move=84, str=18, strAdd=0, dex=14, con=14, **{"int": 12}, wis=12, chr=10)
        return {"name": name, "state": state, "fields": fields, "levels": dict(levels), "room": 3001,
                "conditions": dict.fromkeys(CONDITIONS, 5), "race": 3, "sex": 1}  # fmt: skip

    async def start(self) -> None:
        """Apre il socket Unix (0600)."""
        Path(self.path).unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(self._handle, path=self.path, limit=MAX_LINE * 4)
        Path(self.path).chmod(0o600)

    async def stop(self) -> None:
        """Chiude il server e rimuove il socket."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        Path(self.path).unlink(missing_ok=True)

    # ---- connessione -------------------------------------------------------------------------------------------------------

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Una connessione: righe JSON, `hello` obbligatorio, limiti come il modulo C."""
        if self._conns >= self.max_conn:
            err = {"id": None, "ok": False, "error": {"code": "too_many_connections", "message": "troppe connessioni"}}
            writer.write(json.dumps(err).encode() + b"\n")
            await writer.drain()
            writer.close()
            return
        self._conns += 1
        self._next_conn += 1
        state = {"authed": False, "fails": 0, "actor": "-", "id": self._next_conn, "tokens": float(RATE_PER_SEC), "last": time.monotonic()}
        try:
            while True:
                timeout = None if state["authed"] else self.hello_timeout
                try:
                    raw = await asyncio.wait_for(reader.readline(), timeout)
                except asyncio.LimitOverrunError, ValueError:
                    await self._send(writer, None, err=Err("line_too_long", "riga troppo lunga"))
                    break
                except TimeoutError:
                    break
                if not raw:
                    break
                if len(raw.rstrip(b"\r\n")) > MAX_LINE:
                    await self._send(writer, None, err=Err("line_too_long", "riga troppo lunga"))
                    break
                if not await self._line(raw, writer, state):
                    break
        finally:
            self._conns -= 1
            writer.close()

    async def _send(self, writer: asyncio.StreamWriter, rid: Any, result: Any = None, err: Err | None = None) -> None:
        """Scrive una risposta."""
        if err:
            body: dict[str, Any] = {"code": err.code, "message": err.message}
            if err.params:
                body["params"] = err.params
            msg = {"id": rid, "ok": False, "error": body}
        else:
            msg = {"id": rid, "ok": True, "result": result}
        writer.write(json.dumps(msg, separators=(",", ":")).encode() + b"\n")
        await writer.drain()

    async def _line(self, raw: bytes, writer: asyncio.StreamWriter, st: dict[str, Any]) -> bool:
        """Elabora una riga; False = chiudere la connessione."""
        try:
            text = raw.decode("utf-8").rstrip("\r\n")
            if not text:
                return True
            req = json.loads(text, object_pairs_hook=_dup_pairs, parse_float=_no_float, parse_constant=_no_float)
        except ValueError, UnicodeDecodeError:
            await self._send(writer, None, err=Err("bad_json", "json non valido"))
            return True
        rid = req.get("id") if isinstance(req, dict) else None
        valid_id = (isinstance(rid, int) and not isinstance(rid, bool) and 0 <= rid <= 2**53 - 1) or (
            isinstance(rid, str) and 0 < len(rid) <= 64 and rid.isascii() and rid.isprintable()
        )
        if not isinstance(req, dict) or not valid_id:
            await self._send(writer, None, err=Err("bad_request", "richiesta senza id valido"))
            return True
        cmd, params = req.get("cmd"), req.get("params", {})
        if not isinstance(cmd, str) or not isinstance(params, dict) or set(req) - {"id", "cmd", "params"} or not CMD_RE.fullmatch(cmd):
            await self._send(writer, rid, err=Err("bad_request", "richiesta malformata"))
            return True
        now = time.monotonic()
        st["tokens"] = min(float(RATE_PER_SEC), st["tokens"] + (now - st["last"]) * RATE_PER_SEC)
        st["last"] = now
        if st["tokens"] < 1:
            await self._send(writer, rid, err=Err("rate_limited", "troppe richieste", retry_after_ms=100))
            return True
        st["tokens"] -= 1
        try:
            if cmd == "hello":
                if st["authed"]:
                    raise Err("bad_request", "hello gia' eseguito")
                result = self._hello(params, st)
                self._audit(st, "hello", "ok")
            elif not st["authed"]:
                raise Err("auth_required", "autenticazione richiesta")
            else:
                result = self._dispatch(cmd, params, st)
        except Err as e:
            if cmd == "hello":
                self._audit(st, "hello", e.code)
            await self._send(writer, rid, err=e)
            return not (e.code == "auth_failed" and st["fails"] >= 3)
        await self._send(writer, rid, result)
        return True

    def _audit(self, st: dict[str, Any], cmd: str, result: str, target: str = "-", extra: str = "") -> None:
        """Riga di audit (mai il token)."""
        self.audit.append(f"conn={st['id']} actor={st['actor']} cmd={cmd} target={target} result={result} {extra}".rstrip())

    # ---- comandi -----------------------------------------------------------------------------------------------------------

    def commands(self) -> dict[str, Any]:
        """Comandi attivi per `hello`."""
        out: dict[str, Any] = {}
        for name in READ_COMMANDS + (WRITE_COMMANDS if self.write else ()):
            entry: dict[str, Any] = {"class": "write" if name in WRITE_COMMANDS else "read"}
            if name in ("player.get", "player.set"):
                fields = [*SCALARS, "conditions", "levels"]
                entry["fields"] = fields if name == "player.set" else [*fields, *PROTECTED_FIELDS]
            out[name] = entry
        return out

    def _hello(self, params: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
        """Autenticazione e capability discovery."""
        now = time.monotonic()
        if now < self._lock_until:
            raise Err("rate_limited", "troppi tentativi di autenticazione", retry_after_ms=int((self._lock_until - now) * 1000))
        _check_keys(params, ("protocols", "token", "client", "actor"))
        token = _str(params, "token")
        assert token is not None
        if not hmac.compare_digest(token.encode(), self.token.encode()):
            st["fails"] += 1
            self._fail_times = [t for t in self._fail_times if now - t < 60] + [now]
            if len(self._fail_times) > 10:
                self._lock_until = now + 30
            raise Err("auth_failed", "autenticazione fallita")
        protocols = params.get("protocols")
        if not isinstance(protocols, list):
            raise Err("bad_params", "protocols deve essere un array", field="protocols")
        if 1 not in protocols:
            raise Err("protocol_unsupported", "nessuna versione in comune", supported=[1])
        actor = _str(params, "actor", False) or "-"
        if len(actor) > 64:
            raise Err("bad_params", "actor troppo lungo")
        st["authed"], st["actor"] = True, actor
        return {
            "protocol": 1,
            "mud": {"kind": "fake", "name": "FakeMUD", "version": "0", "module": "fake-livectl"},
            "limits": {"max_line": MAX_LINE, "max_response": 65536, "max_pending": 8, "request_timeout_ms": 2000, "max_text": MAX_TEXT},
            "features": [],
            "commands": self.commands(),
        }

    def _dispatch(self, cmd: str, params: dict[str, Any], st: dict[str, Any]) -> Any:
        """Instrada un comando (allowlist) e registra audit."""
        if cmd not in READ_COMMANDS + WRITE_COMMANDS:
            raise Err("unknown_command", "comando sconosciuto")
        if cmd in WRITE_COMMANDS and not self.write:
            raise Err("command_disabled", "comando disattivato")
        self.calls.append((cmd, params))
        target: list[str] = []
        try:
            result = getattr(self, "c_" + cmd.replace(".", "_"))(params, target)
        except Err as e:
            self._audit(st, cmd, e.code, target[0] if target else "-")
            raise
        self._audit(st, cmd, "ok", target[0] if target else "-")
        return result

    def c_ping(self, p: dict[str, Any], _t: list[str]) -> Any:
        """`ping`."""
        _check_keys(p, ())
        return {"pong": True, "time": int(time.time())}

    def c_info(self, p: dict[str, Any], _t: list[str]) -> Any:
        """`info`."""
        _check_keys(p, ())
        counts = {s: sum(1 for x in self.players.values() if x["state"] == s) for s in ("playing", "linkdead")}
        now = int(time.time())
        return {"mud": {"kind": "fake", "name": "FakeMUD", "version": "0"}, "started_at": self.started_at, "now": now,
                "uptime_s": now - self.started_at, "pulse": 0, "ticks": 0,
                "players": {**counts, "connecting": 0}, "world": {"zones": len(ZONES), "mob_protos": 10, "obj_protos": 10}}  # fmt: skip

    @staticmethod
    def _zone_of_room(room: int) -> int:
        """Indice della prima zona con `top >= room`."""
        return next((z[0] for z in ZONES if z[3] >= room), len(ZONES) - 1)

    def c_who(self, p: dict[str, Any], _t: list[str]) -> Any:
        """`who`."""
        _check_keys(p, ("prefix", "limit", "linkdead"))
        prefix, limit = _str(p, "prefix", False), _int(p, "limit", False)
        limit = 100 if limit is None else limit
        if not 1 <= limit <= 200:
            raise Err("value_out_of_range", "limit fuori intervallo", field="limit", min=1, max=200)
        linkdead = _bool(p, "linkdead", True)
        rows = []
        for x in self.players.values():
            if (x["state"] == "linkdead" and not linkdead) or (prefix and not x["name"].lower().startswith(prefix.lower())):
                continue
            levels = {k: v for k, v in x["levels"].items() if v}
            rows.append({"name": x["name"], "state": x["state"], "level": max(levels.values(), default=0), "levels": levels,
                         "race": x["race"], "sex": x["sex"], "room": x["room"], "zone": self._zone_of_room(x["room"]),
                         "position": 8, "fighting": False, "idle": 0, "immortal": max(levels.values(), default=0) >= 51,
                         "invisible": 0})  # fmt: skip
        return {"players": rows[:limit], "count": min(len(rows), limit), "truncated": len(rows) > limit}

    def _find(self, name: str | None, target: list[str], *, need_playing: bool = True) -> dict[str, Any]:
        """Cerca un giocatore per nome."""
        if name is None or not (name[:1].isalpha() and name.replace("_", "").replace("-", "").isalnum() and len(name) <= 20):
            raise Err("bad_params", "nome non valido", field="name")
        x = self.players.get(name.lower())
        if x is None:
            raise Err("not_found", "giocatore non connesso", what="player")
        target.append(x["name"])
        if need_playing and x["state"] != "playing":
            raise Err("player_not_playing", "il giocatore non e' in gioco")
        return x

    def _fields(self, x: dict[str, Any]) -> dict[str, Any]:
        """Valori correnti dei campi."""
        return {**x["fields"], "maxHit": 41, "maxMana": 0, "maxMove": 0, "race": x["race"], "sex": x["sex"], "roomVnum": x["room"],
                "conditions": dict(x["conditions"]), "levels": {k: v for k, v in x["levels"].items() if v}}  # fmt: skip

    def c_player_get(self, p: dict[str, Any], t: list[str]) -> Any:
        """`player.get`."""
        _check_keys(p, ("name",))
        x = self._find(_str(p, "name"), t)
        return {"name": x["name"], "state": "playing", "fields": self._fields(x)}

    def c_player_set(self, p: dict[str, Any], t: list[str]) -> Any:
        """`player.set`: validazione completa prima di applicare, conferma per gli immortali."""
        _check_keys(p, ("name", "set", "save", "confirm_immortal"))
        save, confirm = _bool(p, "save", True), _bool(p, "confirm_immortal", False)
        sets = p.get("set")
        if not isinstance(sets, dict) or not 1 <= len(sets) <= 16:
            raise Err("bad_params", "set: da 1 a 16 campi", field="set")
        x = self._find(_str(p, "name"), t)
        changes: list[tuple[str, str, int]] = []  # (gruppo, chiave, valore)
        immortal = False
        for key, val in sets.items():
            if key in SCALARS:
                if isinstance(val, bool) or not isinstance(val, int):
                    raise Err("bad_params", "tipo non valido", field=key)
                lo, hi = SCALARS[key]
                if key in ("hit", "mana", "move"):
                    hi = min(hi, max(x["fields"][key], 41 if key == "hit" else 0))
                if not lo <= val <= hi:
                    raise Err("value_out_of_range", "valore fuori intervallo", field=key, min=lo, max=hi)
                changes.append(("fields", key, val))
            elif key in ("conditions", "levels") and isinstance(val, dict) and val:
                names = CONDITIONS if key == "conditions" else CLASS_NAMES
                for sub, v in val.items():
                    if sub not in names:
                        raise Err("bad_params", "campo sconosciuto", field=f"{key}.{sub}")
                    if isinstance(v, bool) or not isinstance(v, int):
                        raise Err("bad_params", "tipo non valido", field=f"{key}.{sub}")
                    lo, hi = (-1, 24) if key == "conditions" else (0, 59)
                    if not lo <= v <= hi:
                        raise Err("value_out_of_range", "valore fuori intervallo", field=f"{key}.{sub}", min=lo, max=hi)
                    if key == "levels":
                        if v > 0 and x["levels"].get(sub, 0) == 0:
                            raise Err(
                                "forbidden_by_policy", "il giocatore non ha quella classe", reason="class_not_owned", **{"class": sub}
                            )
                        if v >= 51 and v > x["levels"].get(sub, 0):
                            if not confirm:
                                raise Err(
                                    "forbidden_by_policy", "livello da immortale: serve confirm_immortal", reason="immortal_level", level=v
                                )
                            immortal = True
                    changes.append((key, sub, v))
            else:
                raise Err("bad_params", "campo non modificabile", field=key)
        applied: dict[str, Any] = {}
        for group, key, v in changes:
            store = x["fields"] if group == "fields" else x[group]
            name = key if group == "fields" else f"{group}.{key}"
            applied[name] = {"old": store[key], "new": v}
            store[key] = v
        if save:
            self.saves.append(x["name"])
        return {"name": x["name"], "applied": applied, "saved": save, "warnings": ["immortal_level"] if immortal else []}

    def c_zone_list(self, p: dict[str, Any], _t: list[str]) -> Any:
        """`zone.list`."""
        _check_keys(p, ())
        return {"zones": [{"index": i, "num": n, "name": name, "top": top, "lifespan": 20, "age": 0, "reset_mode": 2, "started": i > 0}
                          for i, n, name, top in ZONES]}  # fmt: skip

    def c_zone_reset(self, p: dict[str, Any], t: list[str]) -> Any:
        """`zone.reset`."""
        _check_keys(p, ("zone", "room", "only_if_empty"))
        zone, room = _int(p, "zone", False), _int(p, "room", False)
        only_empty = _bool(p, "only_if_empty", False)
        if (zone is None) == (room is None):
            raise Err("bad_params", "serve esattamente uno tra zone e room")
        if room is not None:
            if not 0 <= room <= 9999:
                raise Err("not_found", "stanza inesistente", what="room")
            zone = self._zone_of_room(room)
        assert zone is not None
        if not 0 <= zone < len(ZONES):
            raise Err("not_found", "zona inesistente", what="zone")
        if zone == 0:
            raise Err("forbidden_by_policy", "la zona 0 non e' resettabile dal canale", reason="zone_zero")
        t.append(f"zone:{zone}")
        executed = not (
            only_empty and any(x["state"] == "playing" and self._zone_of_room(x["room"]) == zone for x in self.players.values())
        )
        if executed:
            self.resets.append(zone)
        return {"zone": zone, "name": ZONES[zone][2], "executed": executed}

    def _load_target(self, p: dict[str, Any], t: list[str]) -> tuple[int, bool]:
        """Destinazione di `load.*`: (stanza, e' un giocatore)."""
        room, player = _int(p, "room", False), _str(p, "player", False)
        if (room is None) == (player is None):
            raise Err("bad_params", "serve esattamente uno tra room e player")
        if player is not None:
            return self._find(player, t)["room"], True
        assert room is not None
        if not 0 <= room <= 9999:
            raise Err("not_found", "stanza inesistente", what="room")
        t.append(f"room:{room}")
        return room, False

    def _load(self, p: dict[str, Any], t: list[str], kind: str) -> Any:
        """Corpo comune di `load.mob` e `load.obj`."""
        _check_keys(p, ("vnum", "room", "player", "count", "notify"))
        vnum, count = _int(p, "vnum"), _int(p, "count", False)
        count = 1 if count is None else count
        _bool(p, "notify", False)
        room, on_player = self._load_target(p, t)
        if not 1 <= count <= 10:
            raise Err("value_out_of_range", "count fuori intervallo", field="count", min=1, max=10)
        known = {"mob": {3000: "Magus"}, "obj": {3001: "una bottiglia", 1600: "un oggetto vietato"}}[kind]
        if vnum not in known:
            raise Err("not_found", "inesistente", what="mob" if kind == "mob" else "object")
        if kind == "obj" and any(lo <= (vnum or 0) <= hi for lo, hi in DENY_OBJ):
            raise Err("forbidden_by_policy", "oggetto non creabile dal canale", reason="deny_list", vnum=vnum)
        rows = [{"vnum": vnum, "name": known[vnum or 0], **({"room": room} if kind == "mob" else {"where": "player" if on_player else f"room:{room}"})}
                for _ in range(count)]  # fmt: skip
        self.loaded.extend({"kind": kind, **r} for r in rows)
        return {"loaded": rows}

    def c_load_mob(self, p: dict[str, Any], t: list[str]) -> Any:
        """`load.mob`."""
        return self._load(p, t, "mob")

    def c_load_obj(self, p: dict[str, Any], t: list[str]) -> Any:
        """`load.obj`."""
        return self._load(p, t, "obj")

    def c_echo(self, p: dict[str, Any], t: list[str]) -> Any:
        """`echo`."""
        _check_keys(p, ("text", "to"))
        text, to = _str(p, "text"), p.get("to")
        assert text is not None
        if not isinstance(to, dict) or len(to) != 1:
            raise Err("bad_params", "to deve avere una sola chiave", field="to")
        try:
            latin = text.encode("latin-1")
        except UnicodeEncodeError:
            raise Err("unencodable_text", "testo non rappresentabile in latin-1") from None
        if len(latin) > MAX_TEXT or not latin:
            raise Err("bad_params", "lunghezza del testo non valida", field="text", max=MAX_TEXT)
        if any(b < 0x20 or b == 0x7F for b in latin):
            raise Err("bad_params", "caratteri di controllo non ammessi", field="text")
        ((kind, dest),) = to.items()
        if kind == "all" and dest is True:
            n = sum(1 for x in self.players.values() if x["state"] == "playing")
            t.append("all")
        elif kind == "player" and isinstance(dest, str):
            n = 1 if self._find(dest, t) else 0
        elif kind == "room" and isinstance(dest, int) and not isinstance(dest, bool):
            if not 0 <= dest <= 9999:
                raise Err("not_found", "stanza inesistente", what="room")
            n = sum(1 for x in self.players.values() if x["state"] == "playing" and x["room"] == dest)
            t.append(f"room:{dest}")
        else:
            raise Err("bad_params", "destinatario non valido", field="to")
        self.echoes.append((kind, text))
        return {"recipients": n}
