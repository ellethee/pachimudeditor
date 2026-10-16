"""Utility condivise dai test."""

from typing import Any

import httpx


def data(response: httpx.Response, status: int = 200) -> Any:
    """Verifica lo status e restituisce `data` dell'envelope (oppure None per i 204)."""
    assert response.status_code == status, f"{response.status_code}: {response.text}"
    if status == 204:
        return None
    body = response.json()
    assert body["success"] is True
    return body["data"]


def error_code(response: httpx.Response, status: int) -> str | None:
    """Verifica lo status di errore e restituisce il `code` del primo dettaglio (None per i 422 Pydantic)."""
    assert response.status_code == status, f"{response.status_code}: {response.text}"
    return response.json()["detail"][0].get("code")


async def by_vnum(client: httpx.AsyncClient, resource: str, vnum: int) -> dict[str, Any]:
    """L'elemento di `resource` con il vnum dato (dal listing)."""
    items = data(await client.get(f"/api/{resource}"))["items"]
    return next(i for i in items if i["vnum"] == vnum)
