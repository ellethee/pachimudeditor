"""`pachimudeditor live ...`: client da riga di comando contro il finto server (sempre) e il MUD reale (se si puo' costruire)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from pachimudeditor.cli import app
from tests.live.conftest import FAKE_TOKEN, Target
from tests.support.live_fake_server import FakeLiveServer

ENV = "CLI_TEST_LIVE_TOKEN"
runner = CliRunner()


async def invoke(args: list[str], *, token: str | None, monkeypatch: pytest.MonkeyPatch, env: str = ENV) -> tuple[int, Any, str]:
    """Esegue la CLI in un thread (usa `asyncio.run`) e restituisce exit code, JSON di stdout e stderr."""
    if token is None:
        monkeypatch.delenv(env, raising=False)
    else:
        monkeypatch.setenv(env, token)
    result = await asyncio.to_thread(runner.invoke, app, ["live", *args])
    out = result.stdout.strip()
    return result.exit_code, json.loads(out) if out else None, result.stderr


async def cli(target: Target, args: list[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, Any, str]:
    """Come `invoke`, puntando al server sotto prova con `--socket`/`--token-env`."""
    return await invoke(["--socket", target.socket, "--token-env", ENV, *args], token=target.token, monkeypatch=monkeypatch)


async def test_read_commands(target: Target, monkeypatch: pytest.MonkeyPatch) -> None:
    """status, ping, info, who, player get, zone list: exit 0 e `{"ok": true, "result": ...}`."""
    code, doc, _ = await cli(target, ["status"], monkeypatch)
    assert code == 0 and doc["ok"] and doc["result"]["connected"] is True and doc["result"]["protocol"] == 1
    assert "player.set" in doc["result"]["commands"]
    for cmd in (["ping"], ["info"], ["zone", "list"]):
        code, doc, _ = await cli(target, cmd, monkeypatch)
        assert code == 0 and doc["ok"], (cmd, doc)
    code, doc, _ = await cli(target, ["who", "--prefix", "Tes", "--limit", "5", "--no-linkdead"], monkeypatch)
    assert code == 0 and [p["name"] for p in doc["result"]["players"]] == [target.player]
    code, doc, _ = await cli(target, ["player", "get", target.player], monkeypatch)
    assert code == 0 and doc["result"]["name"] == target.player and "gold" in doc["result"]["fields"]


async def test_write_commands(target: Target, monkeypatch: pytest.MonkeyPatch) -> None:
    """player set (anche annidato), echo, load, zone reset."""
    code, doc, _ = await cli(target, ["player", "set", target.player, "gold=777", "conditions.drunk=0", "--no-save"], monkeypatch)
    assert code == 0, doc
    assert doc["result"]["applied"]["gold"]["new"] == 777 and doc["result"]["applied"]["conditions.drunk"]["new"] == 0
    assert doc["result"]["saved"] is False
    code, doc, _ = await cli(target, ["echo", "ciao dalla cli", "--player", target.player], monkeypatch)
    assert code == 0 and doc["result"]["recipients"] == 1
    code, doc, _ = await cli(target, ["load", "mob", str(target.mob_vnum), "--room", str(target.room), "--count", "2"], monkeypatch)
    assert code == 0 and len(doc["result"]["loaded"]) == 2
    code, doc, _ = await cli(target, ["load", "obj", str(target.obj_vnum), "--player", target.player, "--notify"], monkeypatch)
    assert code == 0 and len(doc["result"]["loaded"]) == 1
    code, doc, _ = await cli(target, ["zone", "reset", "--room", str(target.room), "--only-if-empty"], monkeypatch)
    assert code == 0 and "executed" in doc["result"]


async def test_mud_errors_exit_1(target: Target, monkeypatch: pytest.MonkeyPatch) -> None:
    """Errori del MUD: exit 1 con il codice stabile del protocollo, un solo JSON."""
    code, doc, _ = await cli(target, ["player", "get", "Nessuno"], monkeypatch)
    assert code == 1 and doc["error"]["code"] == "not_found"
    code, doc, _ = await cli(target, ["player", "set", target.player, "gold=-5", "--no-save"], monkeypatch)
    assert code == 1 and doc["error"]["code"] == "value_out_of_range" and doc["error"]["params"]["field"] == "gold"
    code, doc, _ = await cli(target, ["load", "obj", str(target.denied_obj), "--room", str(target.room)], monkeypatch)
    assert code == 1 and doc["error"]["code"] == "forbidden_by_policy"


async def test_auth_failure_exit_4_and_token_never_printed(target: Target, monkeypatch: pytest.MonkeyPatch) -> None:
    """Token sbagliato: exit 4; ne' stdout ne' stderr contengono il token."""
    bad = "x" * 40
    code, doc, err = await invoke(["--socket", target.socket, "--token-env", ENV, "who"], token=bad, monkeypatch=monkeypatch)
    assert code == 4 and doc["error"]["code"] == "auth_failed"
    assert bad not in json.dumps(doc) + err


async def test_missing_token_and_usage_exit_2(target: Target, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Token mancante, nome di variabile che sembra un token, opzioni incoerenti: exit 2."""
    monkeypatch.chdir(tmp_path)
    code, doc, _ = await invoke(["--socket", target.socket, "--token-env", ENV, "who"], token=None, monkeypatch=monkeypatch)
    assert code == 2 and doc["error"]["code"] == "token_missing"
    code, doc, err = await invoke(
        ["--socket", target.socket, "--token-env", target.token + "-x", "who"], token=None, monkeypatch=monkeypatch
    )
    assert code == 2 and doc["error"]["code"] == "usage" and target.token not in err
    for args in (["who"], ["--socket", target.socket, "--world", "w", "who"], ["--socket", "relativo", "who"]):
        code, doc, _ = await invoke(args, token=target.token, monkeypatch=monkeypatch)
        assert code == 2 and doc["error"]["code"] == "usage", args
    for args in (["zone", "reset"], ["zone", "reset", "--zone", "1", "--room", "2"], ["echo", "x"], ["load", "mob", "1"],
                 ["player", "set", target.player, "gold"]):  # fmt: skip
        code, doc, _ = await cli(target, args, monkeypatch)
        assert code == 2 and doc["error"]["code"] == "usage", args


async def test_token_from_dotenv_and_world(target: Target, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--world` legge params.live e il token dal `.env` della cartella di lavoro (variabile d'ambiente assente)."""
    (tmp_path / ".env").write_text(f"{ENV}={target.token}\n")
    live = {"socket": target.socket, "token_env": ENV, "timeout_ms": 2000}
    worlds = [{"id": "w", "kind": "dikumod", "path": str(tmp_path), "params": {"live": live}}]
    monkeypatch.setenv("WEBEDITOR_WORLDS", json.dumps(worlds))
    code, doc, _ = await invoke(["--world", "w", "--workdir", str(tmp_path), "ping"], token=None, monkeypatch=monkeypatch)
    assert code == 0 and doc["ok"], doc
    code, doc, _ = await invoke(["--world", "nope", "--workdir", str(tmp_path), "ping"], token=None, monkeypatch=monkeypatch)
    assert code == 2 and doc["error"]["code"] == "usage"
    worlds[0]["params"]["live"] = {**live, "enabled": False}
    monkeypatch.setenv("WEBEDITOR_WORLDS", json.dumps(worlds))
    code, doc, _ = await invoke(["--world", "w", "--workdir", str(tmp_path), "ping"], token=None, monkeypatch=monkeypatch)
    assert code == 2 and doc["error"]["code"] == "usage"


async def test_pretty_output(target: Target, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--pretty` indenta, senza cambiare il contenuto."""
    args = ["--pretty", "--socket", target.socket, "--token-env", ENV, "ping"]
    monkeypatch.setenv(ENV, target.token)
    result = await asyncio.to_thread(runner.invoke, app, ["live", *args])
    assert result.exit_code == 0 and result.stdout.count("\n") > 1 and json.loads(result.stdout)["ok"] is True


async def test_socket_absent_exit_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Socket assente: exit 3 `unreachable`."""
    code, doc, _ = await invoke(
        ["--socket", str(tmp_path / "no.sock"), "--token-env", ENV, "ping"], token=FAKE_TOKEN, monkeypatch=monkeypatch
    )
    assert code == 3 and doc["error"]["code"] == "unreachable" and FAKE_TOKEN not in json.dumps(doc)


async def test_write_class_disabled_exit_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Classe write disattivata: le letture funzionano, le scritture falliscono con `command_disabled` (exit 1)."""
    server = FakeLiveServer(tmp_path / "ro.sock", FAKE_TOKEN, write=False)
    await server.start()
    try:
        base = ["--socket", str(tmp_path / "ro.sock"), "--token-env", ENV]
        code, doc, _ = await invoke([*base, "who"], token=FAKE_TOKEN, monkeypatch=monkeypatch)
        assert code == 0
        code, doc, _ = await invoke([*base, "echo", "x", "--all"], token=FAKE_TOKEN, monkeypatch=monkeypatch)
        assert code == 1 and doc["error"]["code"] == "command_disabled"
        assert not any(c == "echo" for c, _ in server.calls)
    finally:
        await server.stop()


async def test_timeouts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Server muto: timeout sul `hello` = exit 3; scrittura senza risposta dopo l'invio = exit 5 (mai ritentata)."""
    sock = str(tmp_path / "mute.sock")
    received: list[str] = []
    hello_ok = {"id": 1, "ok": True, "result": {"protocol": 1, "mud": {}, "limits": {}, "features": [],
                                                 "commands": {"ping": {"class": "read"}, "echo": {"class": "write"}}}}  # fmt: skip
    mode = {"answer_hello": False}

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Risponde a `hello` solo se richiesto, ignora il resto."""
        while line := await reader.readline():
            received.append(json.loads(line)["cmd"])
            if mode["answer_hello"] and received[-1] == "hello":
                writer.write(json.dumps(hello_ok).encode() + b"\n")
                await writer.drain()

    server = await asyncio.start_unix_server(handle, path=sock)
    try:
        base = ["--socket", sock, "--token-env", ENV, "--timeout", "0.3"]
        code, doc, _ = await invoke([*base, "ping"], token=FAKE_TOKEN, monkeypatch=monkeypatch)
        assert code == 3 and doc["error"]["code"] == "timeout"
        mode["answer_hello"] = True
        received.clear()
        code, doc, _ = await invoke([*base, "echo", "x", "--all"], token=FAKE_TOKEN, monkeypatch=monkeypatch)
        assert code == 5 and doc["error"]["code"] == "outcome_unknown"
        assert received == ["hello", "echo"]  # niente secondo tentativo
    finally:
        server.close()
        await server.wait_closed()


async def test_inventory_commands(target: Target, monkeypatch: pytest.MonkeyPatch) -> None:
    """player inventory, obj get/set/remove: ref + fp dall'ultima lettura, `stale_ref` (exit 1), uso errato (exit 2). Non lascia tracce."""
    code, doc, _ = await cli(target, ["player", "inventory", target.player, "--brief"], monkeypatch)
    assert code == 0 and doc["result"]["count"] >= 4 and "values" not in doc["result"]["items"][0]
    vest = next(i for i in doc["result"]["items"] if i["slot"] is not None)
    code, doc, _ = await cli(target, ["obj", "get", target.player, vest["ref"]], monkeypatch)
    assert code == 0 and doc["result"]["item"]["fp"] == vest["fp"] and "cost" in doc["result"]["item"]
    item = doc["result"]["item"]
    base = ["obj", "set", target.player, vest["ref"], "--fp", vest["fp"], "--vnum", str(vest["vnum"]), "--no-save"]
    code, doc, _ = await cli(
        target, [*base, "description=Descrizione da CLI", "values.0=3", "affects.1.location=13", "affects.1.modifier=2"], monkeypatch
    )
    assert code == 0 and doc["result"]["item"]["description"] == "Descrizione da CLI" and doc["result"]["item"]["values"][0] == 3
    assert doc["result"]["item"]["affects"][1] == {"location": 13, "modifier": 2}
    code, doc, _ = await cli(target, [*base, "weight=1"], monkeypatch)  # fp vecchia
    assert code == 1 and doc["error"]["code"] == "stale_ref"
    code, doc, _ = await cli(target, ["obj", "get", target.player, vest["ref"]], monkeypatch)
    fresh_fp = doc["result"]["item"]["fp"]
    restore = ["obj", "set", target.player, vest["ref"], "--fp", fresh_fp, "--vnum", str(vest["vnum"]), "--no-save"]
    args = [*restore, f"description={item['description']}", f"values.0={item['values'][0]}", "affects.1.location=0", "affects.1.modifier=0"]
    code, doc, _ = await cli(target, args, monkeypatch)
    assert code == 0 and doc["result"]["item"]["fp"] == vest["fp"]
    # crea una bottiglia e la rimuove
    code, doc, _ = await cli(target, ["load", "obj", str(target.obj_vnum), "--player", target.player], monkeypatch)
    code, doc, _ = await cli(target, ["player", "inventory", target.player, "--brief"], monkeypatch)
    new = next(i for i in doc["result"]["items"] if i["ref"] == "inv:0")
    code, doc, _ = await cli(
        target, ["obj", "remove", target.player, "inv:0", "--fp", new["fp"], "--vnum", str(new["vnum"]), "--no-save"], monkeypatch
    )
    assert code == 0 and doc["result"]["removed"] is True and doc["result"]["destroyed"] == 1
    code, doc, _ = await cli(target, ["obj", "remove", target.player, "inv:0", "--fp", "00000000", "--no-save"], monkeypatch)
    assert code == 1 and doc["error"]["code"] == "stale_ref"
    for args in (["obj", "set", target.player, "eq:5", "--fp", "00000000", "weight"], ["obj", "set", target.player, "eq:5", "--fp", "00000000", "colore=1"],
                 ["obj", "set", target.player, "eq:5", "--fp", "00000000", "affects.0.location=3"],
                 ["obj", "set", target.player, "eq:5", "weight=1"], ["obj", "remove", target.player, "eq:5"]):  # fmt: skip
        code, doc, _ = await cli(target, args, monkeypatch)
        assert code == 2, args
