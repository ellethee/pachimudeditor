"""`pachimudeditor live ...`: client sottile da riga di comando del canale `livectl` (specifica: `docs/backend/live-control-protocol.md`).

Output: un solo documento JSON su stdout (`{"ok": true, "result": ...}` oppure `{"ok": false, "error": {...}}`), diagnostica umana su stderr.
Il token si legge solo da una variabile d'ambiente (o dal `.env` della cartella di lavoro), mai da argomenti, e non viene mai stampato.
Exit code: 0 ok, 1 errore del MUD, 2 uso/configurazione, 3 canale non raggiungibile, 4 autenticazione/negoziazione, 5 esito sconosciuto.
"""

import asyncio
import getpass
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from pachimudeditor.cli.helpers.workdir import WorkdirOption, resolve_workdir, use_workdir
from pachimudeditor.common.adapters.live import LiveError
from pachimudeditor.common.adapters.live_client import LONG_COMMANDS, LONG_WAIT_S, LiveClient

app = typer.Typer(help="Client da riga di comando del canale live verso un MUD acceso (output JSON).", no_args_is_help=True)
player_app = typer.Typer(help="Giocatori connessi.", no_args_is_help=True)
zone_app = typer.Typer(help="Zone del gioco.", no_args_is_help=True)
load_app = typer.Typer(help="Crea mob od oggetti nel gioco.", no_args_is_help=True)
obj_app = typer.Typer(help="Oggetti istanza nell'inventario di un giocatore connesso (feature `inventory`).", no_args_is_help=True)
app.add_typer(player_app, name="player")
app.add_typer(zone_app, name="zone")
app.add_typer(load_app, name="load")
app.add_typer(obj_app, name="obj")

DEFAULT_TOKEN_ENV = "PACHIMUDEDITOR_LIVE_TOKEN"
DEFAULT_TIMEOUT_S = 5.0
EXIT_MUD, EXIT_USAGE, EXIT_UNREACHABLE, EXIT_AUTH, EXIT_UNKNOWN = 1, 2, 3, 4, 5
_INT_RE = re.compile(r"-?\d+")
_ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class _Target:
    """Opzioni globali grezze: la risoluzione (mondo, token) avviene al primo comando, cosi' `--help` non richiede configurazione."""

    world: str | None
    socket: str | None
    token_env: str | None
    timeout: float | None
    actor: str | None
    pretty: bool
    workdir: Path | None
    token: str = ""


class _Exit(Exception):
    """Esce con JSON di errore ed exit code."""

    def __init__(self, code: str, message: str, exit_code: int, **params: Any) -> None:
        """Memorizza codice del protocollo (o locale), messaggio ed exit code."""
        super().__init__(code)
        self.code, self.message, self.exit_code, self.params = code, message, exit_code, params


@app.callback()
def _options(
    ctx: typer.Context,
    world: Annotated[
        str | None, typer.Option("--world", help="Mondo configurato: legge params.live (socket, token_env, timeout_ms).")
    ] = None,
    socket: Annotated[str | None, typer.Option("--socket", help="Percorso assoluto del socket Unix (alternativa a --world).")] = None,
    token_env: Annotated[
        str | None, typer.Option("--token-env", help=f"NOME della variabile col token (default {DEFAULT_TOKEN_ENV}).")
    ] = None,
    timeout: Annotated[
        float | None, typer.Option("--timeout", min=0.2, help="Secondi per ogni scambio (default: timeout_ms del mondo, o 5).")
    ] = None,
    actor: Annotated[str | None, typer.Option("--actor", help="Nome registrato nell'audit del MUD (default cli:<utente>).")] = None,
    pretty: Annotated[bool, typer.Option("--pretty", help="JSON indentato.")] = False,
    workdir: WorkdirOption = None,
) -> None:
    """Dove sta il canale e come si risponde; il token arriva solo dall'ambiente."""
    ctx.meta["live"] = _Target(world, socket, token_env, timeout, actor, pretty, workdir or ctx.obj)


# ---------------------------------------------------------------------- risoluzione


def _world_live(target: _Target) -> dict[str, Any]:
    """`params.live` del mondo indicato (dalla configurazione della cartella di lavoro)."""
    from pachimudeditor.common.adapters.registry import load_world_configs

    try:
        configs, _ = load_world_configs()
    except ValueError as exc:
        raise _Exit("usage", f"configurazione dei mondi non valida: {exc}", EXIT_USAGE) from exc
    config = next((c for c in configs if c.id == target.world), None)
    if config is None:
        raise _Exit("usage", f"mondo {target.world!r} non configurato", EXIT_USAGE)
    live = config.params.get("live")
    if not isinstance(live, dict) or live.get("enabled", True) is False:
        raise _Exit("usage", f"il mondo {target.world!r} non ha un canale live attivo (params.live)", EXIT_USAGE)
    return live


def _resolve(target: _Target) -> tuple[str, float]:
    """Socket e timeout da usare; imposta `target.token`. `_Exit` (exit 2) se la configurazione e' incompleta."""
    if (target.world is None) == (target.socket is None):
        raise _Exit("usage", "indicare esattamente uno tra --world e --socket", EXIT_USAGE)
    root = use_workdir(target.workdir) if target.world else resolve_workdir(target.workdir)
    socket, env_name, timeout = target.socket, target.token_env, target.timeout
    if target.world:
        live = _world_live(target)
        socket = live.get("socket")
        env_name = env_name or live.get("token_env")
        if timeout is None and isinstance(live.get("timeout_ms"), int):
            timeout = live["timeout_ms"] / 1000
    env_name = env_name or DEFAULT_TOKEN_ENV
    if not isinstance(socket, str) or not os.path.isabs(socket):
        raise _Exit("usage", "serve il percorso assoluto del socket", EXIT_USAGE)
    if not _ENV_NAME_RE.fullmatch(env_name):
        raise _Exit("usage", "--token-env vuole il NOME di una variabile d'ambiente, non il token", EXIT_USAGE)
    target.token = os.environ.get(env_name) or _dotenv_value(root / ".env", env_name)
    if not target.token:
        raise _Exit("token_missing", f"variabile {env_name} non impostata (ambiente o .env della cartella di lavoro)", EXIT_USAGE)
    return socket, timeout or DEFAULT_TIMEOUT_S


def _dotenv_value(path: Path, name: str) -> str:
    """Valore di `name` nel `.env` (vuoto se il file o la chiave mancano)."""
    from dotenv import dotenv_values

    return (dotenv_values(path).get(name) or "") if path.is_file() else ""


def _default_actor() -> str:
    """`cli:<utente unix>`."""
    try:
        return f"cli:{getpass.getuser()}"
    except OSError, KeyError:
        return "cli"


# ---------------------------------------------------------------------- esecuzione


def _classify(error: LiveError, *, handshake: bool, write: bool) -> _Exit:
    """Traduce un `LiveError` nell'exit code della specifica."""
    if error.code == "token_missing":
        code = EXIT_USAGE
    elif error.code in ("unreachable", "timeout"):
        code = EXIT_UNREACHABLE
    elif error.code == "outcome_unknown":
        code = EXIT_UNKNOWN
    elif handshake:
        code = EXIT_AUTH  # auth_failed, protocol_unsupported, rate_limited, too_many_connections, protocol_error sul hello
    else:
        code = EXIT_MUD
    return _Exit(error.code, error.message or error.code, code, **error.params)


async def _execute(target: _Target, socket: str, timeout: float, cmd: str | None, params: dict[str, Any] | None, *, write: bool) -> Any:
    """Handshake, poi `cmd` (o `ping` + sessione se `cmd` e' `None`: comando `status`). Le scritture non si ritentano mai."""
    token = target.token
    client = LiveClient(socket, lambda: token, timeout=timeout, default_actor=target.actor or _default_actor())
    try:
        try:
            session = await client.session()
        except LiveError as error:
            raise _classify(error, handshake=True, write=write) from None
        try:
            if cmd is None:
                await client.call("ping")
                return {"connected": True, "protocol": session.protocol, "mud": session.mud, "commands": sorted(session.commands)}
            wait = LONG_WAIT_S if cmd in LONG_COMMANDS else None
            return await client.call(cmd, params, write=write, wait=wait)
        except LiveError as error:
            raise _classify(error, handshake=False, write=write) from None
    finally:
        await client.close()


def _emit(target: _Target, doc: dict[str, Any]) -> None:
    """Scrive il documento JSON su stdout, senza mai il token."""
    text = json.dumps(doc, ensure_ascii=False, indent=2 if target.pretty else None, separators=None if target.pretty else (",", ":"))
    typer.echo(text.replace(target.token, "***") if target.token else text)


def _run(ctx: typer.Context, cmd: str | None, params: dict[str, Any] | None = None, *, write: bool = False) -> NoReturn:
    """Esegue il comando, stampa il JSON ed esce con l'exit code della specifica."""
    target: _Target = ctx.meta["live"]
    try:
        socket, timeout = _resolve(target)
        result = asyncio.run(_execute(target, socket, timeout, cmd, params, write=write))
    except _Exit as exc:
        error = {"code": exc.code, "message": exc.message, "params": exc.params}
        _emit(target, {"ok": False, "error": error})
        print(f"errore: {exc.code}: {exc.message}".replace(target.token, "***") if target.token else f"errore: {exc.code}", file=sys.stderr)
        raise typer.Exit(exc.exit_code) from None
    _emit(target, {"ok": True, "result": result})
    raise typer.Exit(0)


def _usage(ctx: typer.Context, message: str) -> NoReturn:
    """Uso errato: JSON `usage` ed exit 2."""
    target: _Target = ctx.meta["live"]
    _emit(target, {"ok": False, "error": {"code": "usage", "message": message, "params": {}}})
    print(f"errore: {message}", file=sys.stderr)
    raise typer.Exit(EXIT_USAGE)


def _one_of(ctx: typer.Context, what: str, **options: Any) -> dict[str, Any]:
    """Le opzioni valorizzate, con la verifica che sia presente esattamente una."""
    given = {k: v for k, v in options.items() if v not in (None, False)}
    if len(given) != 1:
        _usage(ctx, f"{what}: indicare esattamente una opzione tra {', '.join('--' + k for k in options)}")
    return given


def _parse_fields(ctx: typer.Context, pairs: list[str]) -> dict[str, Any]:
    """`gold=500 conditions.drunk=0` diventa `{"gold": 500, "conditions": {"drunk": 0}}` (interi se sembrano tali, altrimenti stringhe)."""
    out: dict[str, Any] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or not key or key.startswith(".") or key.endswith(".") or ".." in key:
            _usage(ctx, f"campo non valido {pair!r}: serve CAMPO=VALORE")
        node = out
        *parents, leaf = key.split(".")
        for part in parents:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                _usage(ctx, f"campo in conflitto: {key}")
        if leaf in node:
            _usage(ctx, f"campo ripetuto: {key}")
        node[leaf] = int(raw) if _INT_RE.fullmatch(raw) else raw
    return out


# ---------------------------------------------------------------------- comandi


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Handshake e ping: protocollo, MUD e comandi attivi."""
    _run(ctx, None)


@app.command("ping")
def ping(ctx: typer.Context) -> None:
    """`ping`."""
    _run(ctx, "ping")


@app.command("info")
def info(ctx: typer.Context) -> None:
    """`info`: informazioni sul MUD."""
    _run(ctx, "info")


@app.command("who")
def who(
    ctx: typer.Context,
    prefix: Annotated[str | None, typer.Option(help="Solo i nomi che iniziano cosi'.")] = None,
    limit: Annotated[int | None, typer.Option(min=1, max=200, help="Massimo di giocatori (1..200).")] = None,
    no_linkdead: Annotated[bool, typer.Option("--no-linkdead", help="Esclude i giocatori col collegamento caduto.")] = False,
) -> None:
    """`who`: i giocatori connessi."""
    params: dict[str, Any] = {k: v for k, v in {"prefix": prefix, "limit": limit}.items() if v is not None}
    if no_linkdead:
        params["linkdead"] = False
    _run(ctx, "who", params or None)


@player_app.command("get")
def player_get(ctx: typer.Context, name: Annotated[str, typer.Argument(help="Nome del giocatore.")]) -> None:
    """`player.get`: campi correnti in memoria."""
    _run(ctx, "player.get", {"name": name})


@player_app.command("set")
def player_set(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Nome del giocatore.")],
    fields: Annotated[list[str], typer.Argument(help="CAMPO=VALORE (gold=500, conditions.drunk=0, levels.warrior=40).")],
    no_save: Annotated[bool, typer.Option("--no-save", help="Non salvare il giocatore (default: salva).")] = False,
    confirm_immortal: Annotated[
        bool, typer.Option("--confirm-immortal", help="Conferma la promozione a un livello da immortale (>= 51).")
    ] = False,
) -> None:
    """`player.set`: modifica un giocatore connesso (scrittura)."""
    change = _parse_fields(ctx, fields)
    _run(ctx, "player.set", {"name": name, "set": change, "save": not no_save, "confirm_immortal": confirm_immortal}, write=True)


@player_app.command("inventory")
def player_inventory(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Nome del giocatore.")],
    brief: Annotated[bool, typer.Option("--brief", help="Solo ref, fp, vnum, slot, nome e tipo.")] = False,
    limit: Annotated[int | None, typer.Option(min=1, max=200, help="Massimo di oggetti (1..200, default 100).")] = None,
) -> None:
    """`player.inventory`: equipaggiamento e inventario (elenco piatto con `ref` e `fp`)."""
    params: dict[str, Any] = {"name": name, "brief": brief}
    if limit is not None:
        params["limit"] = limit
    _run(ctx, "player.inventory", params)


RefArg = Annotated[str, typer.Argument(help="Riferimento dell'oggetto letto da `player inventory` (eq:5, inv:2, inv:2/0).")]
FpOpt = Annotated[str, typer.Option("--fp", help="Impronta `fp` dell'oggetto, dall'ultima lettura (obbligatoria).")]
VnumOpt = Annotated[int | None, typer.Option("--vnum", help="`vnum` dell'ultima lettura (omesso = oggetto senza prototipo).")]
NoSaveOpt = Annotated[bool, typer.Option("--no-save", help="Non salvare il giocatore (default: salva).")]


@obj_app.command("get")
def obj_get(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Nome del giocatore.")],
    ref: RefArg,
    fp: Annotated[
        str | None, typer.Option("--fp", help="Se dato (con --vnum) verifica che l'oggetto non sia cambiato (`stale_ref`).")
    ] = None,
    vnum: VnumOpt = None,
) -> None:
    """`obj.get`: un oggetto con tutti i campi."""
    params: dict[str, Any] = {"name": name, "ref": ref}
    if fp is not None:
        params["expect"] = {"vnum": vnum, "fp": fp}
    _run(ctx, "obj.get", params)


def _item_changes(ctx: typer.Context, pairs: list[str]) -> dict[str, Any]:
    """`name=...`, `weight=3`, `values.1=8`, `affects.0.location=13 affects.0.modifier=2` diventano la patch di `obj.set` (array con `null` nei buchi)."""
    texts = ("name", "short_description", "description")
    out: dict[str, Any] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        head, _, tail = key.partition(".")
        if not sep or not key:
            _usage(ctx, f"campo non valido {pair!r}: serve CAMPO=VALORE")
        if head in texts and not tail:
            out[head] = raw
        elif head in ("weight", "extra_flags", "timer") and not tail and _INT_RE.fullmatch(raw):
            out[head] = int(raw)
        elif head == "values" and tail.isdigit() and _INT_RE.fullmatch(raw) and int(tail) < 4:
            arr = out.setdefault("values", [None] * 4)
            arr[int(tail)] = int(raw)
        elif head == "affects" and _INT_RE.fullmatch(raw) and re.fullmatch(r"[0-4]\.(location|modifier)", tail):
            idx, _, part = tail.partition(".")
            arr = out.setdefault("affects", [None] * 5)
            arr[int(idx)] = {**(arr[int(idx)] or {}), part: int(raw)}
        else:
            _usage(
                ctx,
                f"campo non valido {pair!r} (name, short_description, description, weight, extra_flags, timer, values.0-3, affects.0-4.location|modifier)",
            )
    for arr in (out.get("values"), out.get("affects")):
        while arr and arr[-1] is None:
            arr.pop()
    for affect in out.get("affects", []):
        if affect is not None and set(affect) != {"location", "modifier"}:
            _usage(ctx, "ogni affect vuole location e modifier")
    return out


@obj_app.command("set")
def obj_set(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Nome del giocatore.")],
    ref: RefArg,
    fields: Annotated[
        list[str],
        typer.Argument(
            help="CAMPO=VALORE: name, short_description, description, weight, extra_flags, timer, values.N, affects.N.location|modifier."
        ),
    ],
    fp: FpOpt,
    vnum: VnumOpt = None,
    no_save: NoSaveOpt = False,
) -> None:
    """`obj.set`: modifica un oggetto istanza (scrittura; `stale_ref` se l'oggetto non e' piu' quello letto)."""
    params = {"name": name, "ref": ref, "expect": {"vnum": vnum, "fp": fp}, "set": _item_changes(ctx, fields), "save": not no_save}
    _run(ctx, "obj.set", params, write=True)


@obj_app.command("remove")
def obj_remove(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Nome del giocatore.")],
    ref: RefArg,
    fp: FpOpt,
    vnum: VnumOpt = None,
    no_save: NoSaveOpt = False,
) -> None:
    """`obj.remove`: toglie e DISTRUGGE l'oggetto (con il contenuto, se contenitore). Non si annulla."""
    _run(ctx, "obj.remove", {"name": name, "ref": ref, "expect": {"vnum": vnum, "fp": fp}, "save": not no_save}, write=True)


@zone_app.command("list")
def zone_list(ctx: typer.Context) -> None:
    """`zone.list`."""
    _run(ctx, "zone.list")


@zone_app.command("reset")
def zone_reset(
    ctx: typer.Context,
    zone: Annotated[int | None, typer.Option(help="Indice della zona (da `zone list`).")] = None,
    room: Annotated[int | None, typer.Option(help="Vnum di una stanza: si resetta la sua zona.")] = None,
    only_if_empty: Annotated[bool, typer.Option("--only-if-empty", help="Non eseguire se un giocatore e' nella zona.")] = False,
) -> None:
    """`zone.reset` (scrittura)."""
    where = _one_of(ctx, "zone reset", zone=zone, room=room)
    _run(ctx, "zone.reset", {**where, "only_if_empty": only_if_empty}, write=True)


@zone_app.command("reload")
def zone_reload(ctx: typer.Context, vnum: Annotated[int, typer.Argument(help="Vnum della zona.")]) -> None:
    """`zone.reload` (scrittura, estensione pachimud): il gioco rilegge i file della zona e rifa' il reset."""
    _run(ctx, "zone.reload", {"vnum": vnum}, write=True)


content_app = typer.Typer(help="Contenuti (estensione pachimud): controllo e ricarica a caldo.", no_args_is_help=True)
app.add_typer(content_app, name="content")


@content_app.command("validate")
def content_validate(
    ctx: typer.Context, strict: Annotated[bool, typer.Option("--strict", help="Anche gli avvisi fanno fallire.")] = False
) -> None:
    """`content.validate` (lettura): problemi dei file con file e riga."""
    _run(ctx, "content.validate", {"strict": strict})


@content_app.command("reload")
def content_reload(
    ctx: typer.Context,
    kind: Annotated[str, typer.Argument(help="races, classes, skills, tables, socials, locales o all.")] = "all",
) -> None:
    """`content.reload` (scrittura): il gioco rilegge i file dei contenuti (tutto o niente)."""
    _run(ctx, "content.reload", {"kind": kind}, write=True)


board_app = typer.Typer(help="Bacheche (estensione pachimud).", no_args_is_help=True)
app.add_typer(board_app, name="board")


@board_app.command("delete")
def board_delete(
    ctx: typer.Context,
    board_id: Annotated[str, typer.Argument(help="Id della bacheca.")],
    message_id: Annotated[int, typer.Argument(help="Id riga del messaggio in board_message (non la posizione).")],
) -> None:
    """`board.delete` (scrittura): toglie un messaggio dal DB e dalla memoria del gioco."""
    _run(ctx, "board.delete", {"board_id": board_id, "id": message_id}, write=True)


@board_app.command("clear")
def board_clear(ctx: typer.Context, board_id: Annotated[str, typer.Argument(help="Id della bacheca.")]) -> None:
    """`board.clear` (scrittura): svuota la bacheca nel DB e nella memoria del gioco."""
    _run(ctx, "board.clear", {"board_id": board_id}, write=True)


@app.command("instances")
def instances(
    ctx: typer.Context,
    room: Annotated[int | None, typer.Option(help="Vnum della stanza.")] = None,
    mob: Annotated[int | None, typer.Option(help="Vnum del prototipo di mob.")] = None,
    obj: Annotated[int | None, typer.Option(help="Vnum del prototipo di oggetto (a terra).")] = None,
    zone: Annotated[int | None, typer.Option(help="Vnum della zona (mob della zona e oggetti a terra nelle sue stanze).")] = None,
    limit: Annotated[int, typer.Option(min=1, max=200)] = 100,
) -> None:
    """`instances.list` (estensione pachimud): istanze in memoria, uno solo tra --room, --mob, --obj, --zone."""
    where = _one_of(ctx, "instances", roomVnum=room, mobVnum=mob, objVnum=obj, zoneVnum=zone)
    _run(ctx, "instances.list", {**where, "limit": limit})


def _load(ctx: typer.Context, cmd: str, vnum: int, room: int | None, player: str | None, count: int, notify: bool) -> NoReturn:
    """Parametri comuni di `load.mob` e `load.obj`."""
    where = _one_of(ctx, cmd, room=room, player=player)
    _run(ctx, cmd, {"vnum": vnum, **where, "count": count, "notify": notify}, write=True)


@load_app.command("mob")
def load_mob(
    ctx: typer.Context,
    vnum: Annotated[int, typer.Argument(help="Vnum del mob.")],
    room: Annotated[int | None, typer.Option(help="Vnum della stanza.")] = None,
    player: Annotated[str | None, typer.Option(help="Nome del giocatore (il mob appare nella sua stanza).")] = None,
    count: Annotated[int, typer.Option(min=1, max=10, help="Quanti (1..10).")] = 1,
    notify: Annotated[bool, typer.Option("--notify", help="Messaggio neutro ai presenti.")] = False,
) -> None:
    """`load.mob` (scrittura)."""
    _load(ctx, "load.mob", vnum, room, player, count, notify)


@load_app.command("obj")
def load_obj(
    ctx: typer.Context,
    vnum: Annotated[int, typer.Argument(help="Vnum dell'oggetto.")],
    room: Annotated[int | None, typer.Option(help="Vnum della stanza.")] = None,
    player: Annotated[str | None, typer.Option(help="Nome del giocatore (l'oggetto va nel suo inventario).")] = None,
    count: Annotated[int, typer.Option(min=1, max=10, help="Quanti (1..10).")] = 1,
    notify: Annotated[bool, typer.Option("--notify", help="Messaggio neutro ai presenti.")] = False,
) -> None:
    """`load.obj` (scrittura)."""
    _load(ctx, "load.obj", vnum, room, player, count, notify)


@app.command("echo")
def echo(
    ctx: typer.Context,
    text: Annotated[str, typer.Argument(help="Testo da mostrare.")],
    all_: Annotated[bool, typer.Option("--all", help="A tutti i giocatori in gioco.")] = False,
    player: Annotated[str | None, typer.Option(help="Nome del giocatore.")] = None,
    room: Annotated[int | None, typer.Option(help="Vnum della stanza.")] = None,
) -> None:
    """`echo`: messaggio ai giocatori (scrittura)."""
    to = _one_of(ctx, "echo", all=all_, player=player, room=room)
    _run(ctx, "echo", {"text": text, "to": {"all": True} if "all" in to else to}, write=True)


__all__ = ["app"]
