"""Asserzioni comuni dei test del canale live."""

from __future__ import annotations

from typing import Any


def ok(resp: dict[str, Any]) -> Any:
    """Asserisce una risposta di successo e ne restituisce il `result`."""
    assert resp["ok"] is True, resp
    return resp["result"]


def err(resp: dict[str, Any], code: str) -> dict[str, Any]:
    """Asserisce un errore con quel `code` e ne restituisce il corpo."""
    assert resp["ok"] is False, resp
    assert resp["error"]["code"] == code, resp
    return resp["error"]
