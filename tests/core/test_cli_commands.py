"""Comandi CLI `init`, `worlds`, `serve`, `build-frontend`: tutto in cartelle temporanee, senza rete, senza avviare uvicorn."""

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from pachifast.config import get_settings
import typer
from typer.testing import CliRunner

from pachimudeditor.cli import app
from pachimudeditor.cli.commands import frontend, serve, worlds
from pachimudeditor.cli.helpers.workdir import CONFIG_ENV, PROJECT_MODULES, WORKDIR_ENV

runner = CliRunner(env={"COLUMNS": "250"})
PASSWORD = "una-password-lunga-abbastanza"


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Cartella di lavoro vuota: cwd e ambiente (i comandi fanno `chdir`, impostano `PACHIFAST_*` e caricano `.env`) ripristinati a fine test."""
    monkeypatch.chdir(tmp_path)
    for var in (
        CONFIG_ENV,
        WORKDIR_ENV,
        "WEBEDITOR_WORLDS",
        "PACHIMUDEDITOR_WORLDS",
        "WEBEDITOR_DEFAULT_WORLD",
        "PACHIFAST_HOST",
        "PACHIFAST_PORT",
    ):
        monkeypatch.delenv(var, raising=False)
    with mock.patch.dict(os.environ):
        _fresh_process_env()
        try:
            yield tmp_path
        finally:
            get_settings.cache_clear()  # `init` rilegge le impostazioni: la cache non deve sopravvivere all'ambiente ripristinato


def _fresh_process_env() -> None:
    """Toglie le `PACHIFAST_*`: `init` le carica da `.env` nel processo e rifiuta di rieseguire se il segreto e' gia' nell'ambiente."""
    for var in [v for v in os.environ if v.startswith("PACHIFAST_")]:
        del os.environ[var]


# ---------------------------------------------------------------------------- init


def test_init_creates_workdir_files_and_superuser(workdir: Path) -> None:
    """Su una cartella nuova (anche da creare) nascono shim, config, `.env`, migration e il primo superuser."""
    target = workdir / "nuova" / "lavoro"
    result = runner.invoke(app, ["init", "--workdir", str(target), "--password", PASSWORD, "--username", "capo"])
    assert result.exit_code == 0, result.output
    assert (target / PROJECT_MODULES).is_file() and (target / "pachimudeditor.yaml").is_file() and (target / ".env").is_file()
    assert list((target / "migrations" / "auth" / "versions").glob("*.py"))
    assert (target / "db.sqlite3").is_file()
    assert "Creato superuser" in result.output and "capo" in result.output and f"serve --workdir {target}" in result.output


def test_init_is_idempotent_and_never_overwrites(workdir: Path) -> None:
    """Rieseguito: i file modificati dall'utente restano, `.env` e' mantenuto, il superuser esiste gia'."""
    args = ["init", "--workdir", str(workdir), "--password", PASSWORD]
    assert runner.invoke(app, args).exit_code == 0
    _fresh_process_env()  # secondo avvio del processo
    (workdir / "pachimudeditor.yaml").write_text("# mio\nserver:\n  port: 9999\n", encoding="utf-8")
    env_before = (workdir / ".env").read_text(encoding="utf-8")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert (workdir / "pachimudeditor.yaml").read_text(encoding="utf-8") == "# mio\nserver:\n  port: 9999\n"
    assert (workdir / ".env").read_text(encoding="utf-8") == env_before
    assert "Mantenuto" in result.output and "Superuser gia" in result.output and "Creato pachimudeditor.yaml" not in result.output


def test_init_no_user_does_not_prompt_nor_create_user(workdir: Path) -> None:
    """`--no-user`: nessuna richiesta di password, nessun superuser."""
    result = runner.invoke(app, ["init", "--workdir", str(workdir), "--no-user"], input="")
    assert result.exit_code == 0, result.output
    assert "Password per" not in result.output and "superuser" not in result.output.lower()


def test_init_prompts_for_password_when_missing(workdir: Path) -> None:
    """Senza `--password` la chiede (con conferma) e crea l'utente."""
    result = runner.invoke(app, ["init", "--workdir", str(workdir)], input=f"{PASSWORD}\n{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    assert "Creato superuser" in result.output


def test_init_rejects_short_password(workdir: Path) -> None:
    """Password troppo corta: errore pulito, nessun traceback."""
    result = runner.invoke(app, ["init", "--workdir", str(workdir), "--password", "corta"])
    assert result.exit_code != 0 and "Password too short" in result.output


def test_init_database_url(workdir: Path) -> None:
    """`--database-url` sposta il DB di autenticazione (niente `db.sqlite3` di default)."""
    db = workdir / "altro.sqlite3"
    result = runner.invoke(app, ["init", "--workdir", str(workdir), "--no-user", "--database-url", f"sqlite+aiosqlite:///{db}"])
    assert result.exit_code == 0, result.output
    assert db.is_file() and not (workdir / "db.sqlite3").exists()


def test_init_keeps_existing_config_file(workdir: Path) -> None:
    """Se esiste gia' un `pachifast.yaml` (nome legacy) `init` non crea anche `pachimudeditor.yaml`."""
    (workdir / "pachifast.yaml").write_text("server:\n  port: 8200\n", encoding="utf-8")
    result = runner.invoke(app, ["init", "--workdir", str(workdir), "--no-user"])
    assert result.exit_code == 0, result.output
    assert not (workdir / "pachimudeditor.yaml").exists()


# ---------------------------------------------------------------------------- worlds


def test_worlds_list_without_worlds(workdir: Path, fake_plugins: None) -> None:
    """Nessun mondo: messaggio guida ed esito 0 per `list`, esito 1 per `check`."""
    listing = runner.invoke(app, ["worlds", "list"])
    assert listing.exit_code == 0 and "Nessun mondo configurato" in listing.output
    check = runner.invoke(app, ["worlds", "check"])
    assert check.exit_code == 1 and "Nessun mondo configurato" in check.output


def test_worlds_list_shows_configured_world(workdir: Path, fake_plugins: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`list` mostra id, kind, nome e default senza toccare i dati."""
    monkeypatch.setenv("WEBEDITOR_WORLDS", '[{"id": "w1", "kind": "fake", "name": "Primo", "path": "/x"}]')
    result = runner.invoke(app, ["worlds", "list"])
    assert result.exit_code == 0, result.output
    assert "w1" in result.output and "Primo" in result.output and "*" in result.output


def test_worlds_bad_configuration_is_a_clean_error(workdir: Path, fake_plugins: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON malformato o validazione del plugin fallita: messaggio leggibile ed esito 1."""
    monkeypatch.setenv("WEBEDITOR_WORLDS", "{non json")
    bad_json = runner.invoke(app, ["worlds", "list"])
    assert bad_json.exit_code == 1 and "Configurazione dei mondi non valida" in bad_json.output
    monkeypatch.setenv("WEBEDITOR_WORLDS", '[{"id": "w", "kind": "fake"}]')
    no_path = runner.invoke(app, ["worlds", "check"])
    assert no_path.exit_code == 1 and "manca path (fake)" in no_path.output


def test_worlds_check_missing_path(workdir: Path, fake_plugins: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un `path` inesistente e' un ERRORE senza aprire il dato."""
    monkeypatch.setenv("WEBEDITOR_WORLDS", f'[{{"id": "w", "kind": "fake", "path": "{workdir / "manca"}"}}]')
    result = runner.invoke(app, ["worlds", "check"])
    assert result.exit_code == 1 and "ERRORE" in result.output and "inesistente" in result.output


def test_worlds_check_reports_ok_and_failures(workdir: Path, fake_plugins: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """`check` apre davvero i mondi: ok con il conteggio delle zone; un adapter che fallisce e' ERRORE (esito 1)."""
    (workdir / "dati").mkdir()
    monkeypatch.setenv("WEBEDITOR_WORLDS", f'[{{"id": "w", "kind": "fake", "path": "{workdir / "dati"}"}}]')
    # l'adapter fittizio non implementa list_zones: errore riportato con tipo e messaggio
    failed = runner.invoke(app, ["worlds", "check"])
    assert failed.exit_code == 1 and "NotImplementedError" in failed.output

    async def fine(_registry: Any, _world_id: str) -> tuple[bool, str]:
        """Sonda sostitutiva: il mondo risponde."""
        return True, "3 zone"

    monkeypatch.setattr(worlds, "_probe", fine)
    ok = runner.invoke(app, ["worlds", "check"])
    assert ok.exit_code == 0, ok.output
    assert "ok" in ok.output and "3 zone" in ok.output


class _Boom(Exception):
    """Errore con `detail` come gli `HTTPException` pachifast."""

    detail = [{"message": "database non raggiungibile"}]


class _Adapter:
    """Adapter finto per `_probe`: `list_zones` fallisce o risponde, con rapporto di schema facoltativo."""

    def __init__(self, error: Exception | None = None, reason: str | None = None, report: Any = None) -> None:
        """Imposta l'esito di `list_zones` e gli hook facoltativi."""
        self.error = error
        if reason:
            self.unavailable_reason = lambda: reason
        if report is not None:
            self.schema_report = lambda: report

    async def list_zones(self, params: Any) -> Any:
        """Risponde con 7 zone o alza l'errore impostato."""
        if self.error:
            raise self.error
        return mock.Mock(total=7)


class _Registry:
    """Registro finto con un solo adapter."""

    def __init__(self, adapter: Any) -> None:
        """Conserva l'adapter."""
        self.adapter = adapter

    def get(self, _world_id: str) -> Any:
        """Sempre lo stesso adapter."""
        return self.adapter


async def test_probe_variants() -> None:
    """`_probe`: successo con rapporto di schema, motivo di indisponibilita', `detail` di HTTPException, errore generico."""
    report = mock.Mock(summary=lambda: "schema 3 ok", warnings=[mock.Mock(code="x", message="attenzione")])
    assert await worlds._probe(_Registry(_Adapter(report=report)), "w") == (True, "7 zone; schema 3 ok")
    assert await worlds._probe(_Registry(_Adapter(error=RuntimeError("x"), reason="DB assente")), "w") == (False, "DB assente")
    assert await worlds._probe(_Registry(_Adapter(error=_Boom())), "w") == (False, "database non raggiungibile")
    assert await worlds._probe(_Registry(_Adapter(error=ValueError("rotto"))), "w") == (False, "ValueError: rotto")
    assert worlds._schema_warnings(_Registry(_Adapter(report=report)), ["w"]) == ["w: [x] attenzione"]
    assert worlds._schema_warnings(_Registry(_Adapter()), ["w"]) == []


def test_where_and_caps_helpers() -> None:
    """`_where`: URL redatto se l'adapter lo sa dare, altrimenti il path; `_caps`: solo le capability vere, senza `read_only`."""
    params = mock.Mock(redacted_url=lambda: "sqlite:///x")
    assert worlds._where(mock.Mock(params=params), mock.Mock(path="/p")) == "sqlite:///x"
    assert worlds._where(object(), mock.Mock(path=None)) == "-"
    info = mock.Mock(capabilities=mock.Mock(model_dump=lambda: {"read_only": True, "supports_players": True, "supports_transfer": False}))
    assert worlds._caps(info) == "players"


# ---------------------------------------------------------------------------- serve


@pytest.fixture
def served(workdir: Path, fake_plugins: None, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Cartella inizializzata, SPA finta e `uvicorn.run` sostituito: ritorna i parametri con cui sarebbe partito."""
    import uvicorn

    from pachimudeditor import spa

    (workdir / PROJECT_MODULES).write_text("", encoding="utf-8")
    monkeypatch.setattr(spa, "static_dir", lambda: workdir)
    calls: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda target, **kwargs: calls.update(target=target, **kwargs))
    return calls


def test_serve_starts_uvicorn_with_defaults(workdir: Path, served: dict[str, Any]) -> None:
    """Default 127.0.0.1:8123 sulla factory dell'app, senza reload e senza `.env`."""
    result = runner.invoke(app, ["serve", "--workdir", str(workdir)])
    assert result.exit_code == 0, result.output
    assert served["target"] == serve.APP_FACTORY and served["factory"] is True
    assert (served["host"], served["port"]) == ("127.0.0.1", 8123)
    assert served["reload"] is False and served["reload_dirs"] is None and served["env_file"] is None and served["log_level"] == "info"


def test_serve_options_env_file_and_reload(workdir: Path, served: dict[str, Any]) -> None:
    """Opzioni di riga di comando, `.env` esistente e reload sulla cartella del pacchetto."""
    (workdir / ".env").write_text("X=1\n", encoding="utf-8")
    result = runner.invoke(
        app, ["serve", "--workdir", str(workdir), "--host", "0.0.0.0", "--port", "9100", "--reload", "--log-level", "DEBUG"]
    )
    assert result.exit_code == 0, result.output
    assert (served["host"], served["port"], served["reload"], served["log_level"]) == ("0.0.0.0", 9100, True, "debug")
    assert served["env_file"] == str(workdir / ".env") and served["reload_dirs"] and served["reload_dirs"][0].endswith("pachimudeditor")


def test_serve_open_browser_uses_loopback_for_wildcard(workdir: Path, served: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """`--open` programma l'apertura del browser (senza aprirlo) su 127.0.0.1 anche se si ascolta su 0.0.0.0."""
    timers: list[tuple[float, Any, tuple[str, ...]]] = []

    class FakeTimer:
        """Sostituisce `threading.Timer`: registra e non parte."""

        def __init__(self, delay: float, fn: Any, args: tuple[str, ...]) -> None:
            """Registra la richiesta."""
            timers.append((delay, fn, args))

        def start(self) -> None:
            """Non fa nulla."""

    monkeypatch.setattr(serve.threading, "Timer", FakeTimer)
    result = runner.invoke(app, ["serve", "--workdir", str(workdir), "--host", "0.0.0.0", "--port", "9101", "--open"])
    assert result.exit_code == 0, result.output
    assert timers and timers[0][2] == ("http://127.0.0.1:9101/",)


def test_serve_requires_initialized_workdir(workdir: Path, served: dict[str, Any]) -> None:
    """Senza `project_modules.py` suggerisce `init` e non avvia nulla."""
    (workdir / PROJECT_MODULES).unlink()
    result = runner.invoke(app, ["serve", "--workdir", str(workdir)])
    assert result.exit_code != 0 and "init" in result.output and "target" not in served


def test_serve_missing_workdir(workdir: Path, served: dict[str, Any]) -> None:
    """Cartella inesistente: errore chiaro."""
    result = runner.invoke(app, ["serve", "--workdir", str(workdir / "nope")])
    assert result.exit_code != 0 and "non esiste" in result.output and "target" not in served


def test_serve_without_frontend(workdir: Path, served: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Senza SPA impacchettata suggerisce `build-frontend`."""
    from pachimudeditor import spa

    monkeypatch.setattr(spa, "static_dir", lambda: None)
    result = runner.invoke(app, ["serve", "--workdir", str(workdir)])
    assert result.exit_code != 0 and "build-frontend" in result.output and "target" not in served


def test_serve_invalid_worlds_stops_before_uvicorn(workdir: Path, served: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """Mondi non validi: esito 1 con il messaggio, uvicorn non parte."""
    monkeypatch.setenv("WEBEDITOR_WORLDS", '[{"id": "w", "kind": "non-esiste", "path": "/x"}]')
    result = runner.invoke(app, ["serve", "--workdir", str(workdir)])
    assert result.exit_code == 1 and "non-esiste" in result.output and "target" not in served


def test_resolve_address_from_env_and_yaml(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ordine: opzione, variabili d'ambiente, YAML, default."""
    (workdir / "pachimudeditor.yaml").write_text("server:\n  host: 10.0.0.5\n  port: 8200\n", encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(workdir / "pachimudeditor.yaml"))
    assert serve.resolve_address(None, None) == ("10.0.0.5", 8200)
    monkeypatch.setenv("PACHIFAST_HOST", "h")
    monkeypatch.setenv("PACHIFAST_PORT", "8300")
    assert serve.resolve_address(None, None) == ("h", 8300)
    assert serve.resolve_address("o", 1) == ("o", 1)


# ---------------------------------------------------------------------------- build-frontend


def _frontend_checkout(root: Path) -> Path:
    """Finto checkout con `frontend/package.json`."""
    (root / "frontend").mkdir(parents=True)
    (root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    return root / "frontend"


def test_find_frontend_dir(workdir: Path) -> None:
    """`--frontend-dir` esplicito, `./frontend` oppure errore se non c'e' `package.json`."""
    fe = _frontend_checkout(workdir)
    assert frontend.find_frontend_dir(fe) == fe.resolve()
    assert frontend.find_frontend_dir(None) == fe.resolve()
    with pytest.raises(typer.BadParameter):
        frontend.find_frontend_dir(workdir / "assente")


def test_copy_spa_replaces_target_and_requires_index(tmp_path: Path) -> None:
    """La SPA sostituisce il vecchio contenuto; senza `index.html` nel build si rifiuta e non tocca nulla."""
    dist, target = tmp_path / "dist", tmp_path / "static"
    dist.mkdir()
    target.mkdir()
    (target / "vecchio.txt").write_text("x", encoding="utf-8")
    with pytest.raises(typer.BadParameter):
        frontend.copy_spa(dist, target)
    assert (target / "vecchio.txt").exists()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    frontend.copy_spa(dist, target)
    assert (target / "index.html").is_file() and not (target / "vecchio.txt").exists()


def test_build_frontend_without_pnpm(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Senza pnpm nel PATH: errore chiaro, nessun processo lanciato."""
    monkeypatch.setattr(frontend.shutil, "which", lambda _name: None)
    run = mock.Mock()
    monkeypatch.setattr(frontend.subprocess, "run", run)
    result = runner.invoke(app, ["build-frontend"])
    assert result.exit_code != 0 and "pnpm non trovato" in result.output
    run.assert_not_called()


def test_build_frontend_without_checkout(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Da un'installazione senza sorgenti del frontend: errore con il suggerimento."""
    monkeypatch.setattr(frontend.shutil, "which", lambda _name: "/usr/bin/pnpm")
    monkeypatch.setattr(frontend, "PACKAGE_DIR", workdir / "a" / "b" / "pkg")
    result = runner.invoke(app, ["build-frontend"])
    assert result.exit_code != 0 and "Cartella frontend non trovata" in result.output


def test_build_frontend_runs_pnpm_and_copies(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`pnpm install --frozen-lockfile` + `pnpm build` nel frontend e copia di `dist/spa`; `--skip-install` salta il primo."""
    fe = _frontend_checkout(workdir)
    package = workdir / "src" / "pachimudeditor"
    monkeypatch.setattr(frontend, "PACKAGE_DIR", package)
    monkeypatch.setattr(frontend.shutil, "which", lambda _name: "/usr/bin/pnpm")
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], cwd: Path, check: bool) -> None:
        """Registra il comando e, per `build`, produce la SPA."""
        commands.append(cmd)
        if cmd[1] == "build":
            (cwd / "dist" / "spa").mkdir(parents=True, exist_ok=True)
            (cwd / "dist" / "spa" / "index.html").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(frontend.subprocess, "run", fake_run)
    result = runner.invoke(app, ["build-frontend", "--frontend-dir", str(fe)])
    assert result.exit_code == 0, result.output
    assert commands == [["/usr/bin/pnpm", "install", "--frozen-lockfile"], ["/usr/bin/pnpm", "build"]]
    assert (package / "static" / "index.html").read_text(encoding="utf-8") == "ok"
    commands.clear()
    assert runner.invoke(app, ["build-frontend", "--frontend-dir", str(fe), "--skip-install"]).exit_code == 0
    assert commands == [["/usr/bin/pnpm", "build"]]


def test_build_frontend_pnpm_failure_is_reported(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Se pnpm esce con errore il comando fallisce senza copiare nulla."""
    fe = _frontend_checkout(workdir)
    monkeypatch.setattr(frontend, "PACKAGE_DIR", workdir / "pkg")
    monkeypatch.setattr(frontend.shutil, "which", lambda _name: "/usr/bin/pnpm")

    def failing(cmd: list[str], **_kwargs: Any) -> None:
        """pnpm fallisce."""
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(frontend.subprocess, "run", failing)
    result = runner.invoke(app, ["build-frontend", "--frontend-dir", str(fe)])
    assert result.exit_code != 0 and not (workdir / "pkg" / "static").exists()
