"""Smoke test del backend (senza pytest): solo chiamate GET di sola lettura.

Uso (server gia' avviato, utente superuser di test):
    SMOKE_USER=tester SMOKE_PASSWORD=... uv run python scripts/smoke.py [base_url]

Verifica auth obbligatoria, envelope, paginazione, ordinamento, ricerca, filtro `zoneId`,
grafo delle stanze ed errori con codice stabile.
"""

import os
import sys

import httpx


def check(condition: bool, label: str) -> None:
    """Stampa l'esito di un controllo e termina con errore se fallisce."""
    print(("OK   " if condition else "FAIL ") + label)
    if not condition:
        sys.exit(1)


def main() -> None:
    """Esegue lo smoke test contro `base_url` (default http://127.0.0.1:8123)."""
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"
    with httpx.Client(base_url=base, timeout=30) as client:
        check(client.get("/api/zones").status_code == 401, "senza token: 401")
        token = client.post(
            "/api/auth/token",
            data={"username": os.environ["SMOKE_USER"], "password": os.environ["SMOKE_PASSWORD"]},
        ).json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        def get(path: str, **params: object) -> httpx.Response:
            """GET autenticato."""
            return client.get(path, params=params)

        paths = get("/api/v1/openapi.json").json()["paths"]
        for route in ("/api/zones", "/api/rooms", "/api/rooms/graph", "/api/mobs", "/api/objects", "/api/meta/enums"):
            check(route in paths, f"OpenAPI contiene {route}")

        for name in ("zones", "rooms", "mobs", "objects"):
            r = get(f"/api/{name}", page=1, pageSize=5)
            body = r.json()
            check(r.status_code == 200 and body["success"] is True, f"GET /api/{name} envelope")
            data = body["data"]
            check({"items", "total", "page", "pageSize", "pages"} <= set(data), f"/api/{name} forma paginata")
            check(len(data["items"]) <= 5, f"/api/{name} rispetta pageSize")
            full = get(f"/api/{name}").json()["data"]
            check(len(full["items"]) == full["total"], f"/api/{name} senza page/pageSize: tutte le righe")
            if data["items"]:
                first = data["items"][0]
                check("zoneId" in first or name == "zones", f"/api/{name} camelCase")
                one = get(f"/api/{name}/{first['id']}")
                check(one.status_code == 200 and one.json()["data"]["id"] == first["id"], f"GET /api/{name}/{{id}}")
                if name != "zones":
                    check(get(f"/api/{name}/{first['id']}/usage").status_code == 200, f"GET /api/{name}/{{id}}/usage")
            desc = get(f"/api/{name}", orderBy="-vnum").json()["data"]["items"]
            check(desc == sorted(desc, key=lambda i: -i["vnum"]), f"/api/{name} orderBy=-vnum")
            check(get(f"/api/{name}", orderBy="nonexistent").status_code == 422, f"/api/{name} orderBy invalido: 422")
            check(get(f"/api/{name}/999999999").status_code == 404, f"/api/{name}/999999999: 404")

        err = get("/api/zones/999999999").json()["detail"][0]
        check(err["code"] == "zones.not_found", f"errore con codice stabile ({err['msg']})")

        zones = get("/api/zones").json()["data"]["items"]
        if zones:
            zid = zones[0]["id"]
            check(get(f"/api/zones/{zid}/summary").status_code == 200, "GET zones/{id}/summary")
            check(get(f"/api/zones/{zid}/reset-commands").status_code == 200, "GET zones/{id}/reset-commands")
            for kind in ("room", "mob", "object"):
                check(get(f"/api/zones/{zid}/next-vnum", kind=kind).status_code == 200, f"zones/{{id}}/next-vnum {kind}")
            check(get("/api/zones", search=zones[0]["name"][:3]).json()["data"]["total"] >= 1, "zones search")
            rooms = get("/api/rooms", zoneId=zid).json()["data"]
            check(all(i["zoneId"] == zid for i in rooms["items"]), "rooms filtro zoneId")
            graph = get("/api/rooms/graph", zoneId=zid).json()["data"]
            check({"nodes", "edges"} <= set(graph), "rooms/graph nodes+edges")
            if rooms["items"]:
                detail = get(f"/api/rooms/{rooms['items'][0]['id']}").json()["data"]
                check("exits" in detail and "extraDescriptions" in detail, "rooms/{id} dettaglio")
        check(get("/api/zones/next-vnum").status_code == 200, "GET zones/next-vnum")

        enums = get("/api/meta/enums").json()["data"]
        check({"sectorType", "direction", "zoneCommandType"} <= set(enums), "meta/enums")
        check(get("/api/meta/races").status_code == 200, "meta/races")
        check(get("/api/meta/classes").status_code == 200, "meta/classes")
    print("Smoke test completato.")


if __name__ == "__main__":
    main()
