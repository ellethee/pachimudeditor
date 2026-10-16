"""Processo figlio dei test di isolamento: gira con `python -I`, quindi senza PYTHONPATH/cwd, e con `pachimud` nascosto.

Uso: `python -I isolated_child.py <modo> <json-argomenti>`; stampa `OK ...` su stdout se le verifiche passano.
Il finder in testa a `sys.meta_path` fa fallire ogni import di `pachimud`.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ARGS = json.loads(sys.argv[2])
REPO = ARGS["repo"]  # radice del repo dell'editor (per `tests.support`)


class HidePachimud:
    """Nasconde `pachimud` (anche quello installato in editabile): ogni suo import fallisce."""

    def find_spec(self, name, path=None, target=None):  # type: ignore[no-untyped-def]
        """`ModuleNotFoundError` per `pachimud` e i suoi sottomoduli."""
        if name == "pachimud" or name.startswith("pachimud."):
            raise ModuleNotFoundError(f"No module named {name!r} (nascosto dal test)", name=name)
        return None


sys.meta_path.insert(0, HidePachimud())
sys.path.append(REPO)


def prepare_app():  # type: ignore[no-untyped-def]
    """Ambiente di test (DB auth temporaneo, utente) e app con i soli mondi dati (nessun mondo pachimud)."""
    from tests.support import stack

    workdir = Path(ARGS["workdir"])
    stack.apply_environment(workdir)
    stack.create_test_user()
    os.environ["WEBEDITOR_WORLDS"] = json.dumps(ARGS["worlds"])
    os.environ["WEBEDITOR_DEFAULT_WORLD"] = ARGS["worlds"][0]["id"]
    os.environ.pop("PACHIMUD_CONFIG_PATH", None)
    from pachimudeditor.app import create_editor_app

    app = create_editor_app(serve_spa=False)
    assert "pachimud" not in sys.modules, "pachimud importato"
    return app


async def serve_without_pachimud(app) -> None:  # type: ignore[no-untyped-def]
    """`/api/worlds` e zone funzionano, le rotte pachimud non esistono."""
    import httpx

    from tests.support import stack

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as anon:
        token = (await anon.post("/api/auth/token", data={"username": stack.TEST_USER, "password": stack.TEST_PASSWORD})).json()[
            "access_token"
        ]
        auth = {"Authorization": f"Bearer {token}"}
        worlds = (await anon.get("/api/worlds", headers=auth)).json()["data"]
        assert [w["id"] for w in worlds] == [w["id"] for w in ARGS["worlds"]], worlds
        zones = (await anon.get("/api/zones", headers=auth)).json()["data"]
        assert zones["total"] > 0, zones
        for path in ("/api/world/overview", "/api/players/accounts", "/api/instances/mobs", "/api/content/races"):
            status = (await anon.get(path, headers=auth)).status_code
            assert status == 404, (path, status)
    assert "pachimud" not in sys.modules
    print(f"OK zones={zones['total']}")


async def pachimud_scenario(app) -> None:  # type: ignore[no-untyped-def]
    """Il mondo pachimud funziona end-to-end con `pachimud` bloccato, su un DB creato prima dal gioco (copia temporanea)."""
    import io
    import zipfile

    import httpx

    from tests.support import stack

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        token = (await client.post("/api/auth/token", data={"username": stack.TEST_USER, "password": stack.TEST_PASSWORD})).json()[
            "access_token"
        ]
        auth = {"Authorization": f"Bearer {token}"}

        async def call(method: str, path: str, expect: int = 200, **kw):  # type: ignore[no-untyped-def]
            """Richiesta autenticata con verifica dello status; restituisce `data` (None per i 204)."""
            response = await client.request(method, path, headers=auth, **kw)
            assert response.status_code == expect, (method, path, response.status_code, response.text[:300])
            return (
                response.json().get("data")
                if expect != 204 and response.headers.get("content-type", "").startswith("application/json")
                else response
            )

        worlds = await call("GET", "/api/worlds")
        pachimud = next(w for w in worlds if w["id"] == "pachimud")
        assert pachimud["capabilities"]["supportsPlayers"] and pachimud["capabilities"]["supportsTransfer"], pachimud
        zones = await call("GET", "/api/zones")
        assert zones["total"] == 2, zones
        assert (await call("GET", "/api/rooms"))["total"] == 3 and (await call("GET", "/api/mobs"))["total"] == 2
        assert (await call("GET", "/api/objects"))["total"] == 2
        # zona nuova, stanza, modifica, export, cancellazione
        zone = await call(
            "POST", "/api/zones", 201, json={"vnum": 77, "name": "Isolata", "builder": "t", "bottomVnum": 7700, "topVnum": 7799}
        )
        room = await call("POST", "/api/rooms", 201, json={"vnum": 7700, "zoneId": zone["id"], "name": "Stanza", "description": "x"})
        room = await call("PUT", f"/api/rooms/{room['id']}", json={"name": "Stanza due"})
        assert room["name"] == "Stanza due"
        bundle = await call("GET", f"/api/transfer/zones/{zone['id']}/export/bundle")
        assert "Stanza due" in bundle["files"]["rooms.yaml"], bundle
        await call("DELETE", f"/api/rooms/{room['id']}", 204)
        await call("DELETE", f"/api/zones/{zone['id']}", 204)
        # re-import dello zip esportato
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, text in bundle["files"].items():
                archive.writestr(f"{bundle['folder']}/{name}", text)
        upload = {"files": ("z.zip", buffer.getvalue(), "application/zip")}
        preview = await call("POST", "/api/transfer/zones/import?dryRun=false&confirm=true", files=upload)
        assert preview["applied"] is True and preview["rooms"]["create"] == 1, preview
        assert (await call("GET", "/api/zones"))["total"] == 3
        # giocatori, mondo, istanze, contenuti
        account = await call("POST", "/api/players/accounts", 201, json={"username": "mario", "password": "password123"})
        assert (await call("GET", "/api/players/accounts"))["total"] == 1 and account["isBanned"] is False
        assert (await call("GET", "/api/world/overview"))["counts"]["zones"] == 3
        assert (await call("GET", "/api/instances/mobs"))["total"] == 0
        assert len(await call("GET", "/api/content/races")) >= 30
        assert any(r["id"] == "human" for r in await call("GET", "/api/meta/races"))
    assert "pachimud" not in sys.modules, "pachimud importato durante l'uso del mondo"
    print("OK pachimud-world")


def serve_pachimud() -> None:
    """Costruisce l'app con un mondo pachimud (parametri espliciti) e ne esegue lo scenario."""
    from tests.support import stack

    workdir = Path(ARGS["workdir"])
    stack.apply_environment(workdir)
    stack.create_test_user()
    from pachimudeditor.app import create_editor_app

    app = create_editor_app(serve_spa=False)
    asyncio.run(pachimud_scenario(app))


def setup_pachimud_params() -> None:
    """`prepare_worlds` accetta un mondo pachimud con `database_url` e senza il gioco; senza parametri e' un errore chiaro."""
    from pachimudeditor.common.adapters.bootstrap import WorldSetupError, prepare_worlds

    os.environ["WEBEDITOR_WORLDS"] = json.dumps(ARGS["worlds"])
    os.environ.pop("WEBEDITOR_DEFAULT_WORLD", None)
    os.environ.pop("PACHIMUD_CONFIG_PATH", None)
    try:
        configs, default = prepare_worlds()
    except WorldSetupError as exc:
        print(f"ERR {exc}")
        return
    print(f"OK {[c.id for c in configs]} {default}")


{
    "serve": lambda: asyncio.run(serve_without_pachimud(prepare_app())),
    "pachimud": serve_pachimud,
    "setup": setup_pachimud_params,
}[sys.argv[1]]()
