"""Fuzz mirato dalle specifiche OpenAPI: testi ostili in path, query e corpi JSON di tutte le rotte dell'editor.

Per ogni valore ostile ogni operazione (tranne `auth`/`admin`) riceve il valore in ogni parametro/campo di tipo stringa.
Atteso: mai 5xx (solo 2xx/4xx coerenti, con `detail` JSON sui 4xx dell'API).
"""

from typing import Any
from urllib.parse import quote

import httpx
import pytest

HOSTILE = [
    "",
    " ",
    "x" * 4_000,
    "a\x00b",
    "'; DROP TABLE zones; --",
    "../../etc/passwd",
    "%00%2e%2e%2f",
    "line1\r\nX-Injected: 1",
    "‮\u0000﻿\U0001f4a5퟿",
    "{{7*7}} ${jndi:ldap://x} <script>alert(1)</script>",
    "-1",
    "NaN",
]
SKIP_PREFIXES = ("/api/auth", "/api/admin", "/api/health", "/api/version", "/api/infos", "/api/v1")
# Le rotte con upload multipart sono coperte da test_limits / test_transfer
SKIP_PATHS = ("/api/transfer/zones/import",)


def _fill(schema: dict[str, Any], spec: dict[str, Any], value: str, depth: int = 0) -> Any:
    """Un valore valido per `schema` con ogni stringa libera sostituita da `value`."""
    if "$ref" in schema:
        return _fill(spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]], spec, value, depth)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"]
            return _fill(options[0], spec, value, depth) if options else None
    if "allOf" in schema:
        return _fill(schema["allOf"][0], spec, value, depth)
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "string":
        return value
    if kind in ("integer", "number"):
        return max(schema.get("minimum", 1), 1)
    if kind == "boolean":
        return True
    if kind == "array":
        return [_fill(schema.get("items", {}), spec, value, depth + 1)] if depth < 4 else []
    if kind == "object" or "properties" in schema:
        if depth >= 4:
            return {}
        return {k: _fill(v, spec, value, depth + 1) for k, v in schema.get("properties", {}).items()}
    return value


def _operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """`(metodo, percorso, operazione)` delle rotte da fuzzare."""
    found = []
    for path, item in spec["paths"].items():
        if path.startswith(SKIP_PREFIXES) or path in SKIP_PATHS:
            continue
        for method, operation in item.items():
            if method in ("get", "post", "put", "patch", "delete"):
                found.append((method.upper(), path, operation))
    return found


@pytest.mark.parametrize("value", HOSTILE, ids=[f"h{i}" for i in range(len(HOSTILE))])
async def test_hostile_text_is_never_a_500(client: httpx.AsyncClient, value: str) -> None:
    """Percorsi, query e corpi con testo ostile: nessuna risposta 5xx."""
    spec = (await client.get("/api/v1/openapi.json")).json()
    operations = _operations(spec)
    assert len(operations) > 60
    failures: list[str] = []
    statuses: set[int] = set()
    for method, path, operation in operations:
        url, query = path, {}
        for param in operation.get("parameters", []):
            schema = param.get("schema", {})
            is_text = schema.get("type") == "string" or "anyOf" in schema
            if param["in"] == "header" or not is_text and param["in"] != "path":
                continue
            fill = value if is_text else "1"
            if param["in"] == "path":
                url = url.replace("{" + param["name"] + "}", quote(fill, safe="") or "_")
            else:
                query[param["name"]] = fill
        body = operation.get("requestBody", {}).get("content", {}).get("application/json")
        try:
            request = client.build_request(
                method, "http://test" + url, params=query, json=_fill(body["schema"], spec, value) if body else None
            )
            response = await client.send(request)
        except httpx.InvalidURL, UnicodeError:  # il client stesso rifiuta l'URL: non arriva al server
            continue
        statuses.add(response.status_code)
        if response.status_code >= 500:
            failures.append(f"{method} {path} -> {response.status_code}: {response.text[:200]}")
    assert not failures, "\n".join(failures)
    assert 422 in statuses and statuses & {200, 201, 204}, statuses  # le richieste arrivano davvero ai gestori
