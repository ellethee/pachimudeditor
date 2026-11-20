"""JSON Schema di `pachimudeditor.yaml`: lo schema di pachifast piu' le chiavi dell'editor (`webeditor_*`, `config_path`)."""

import json
from typing import Any

from pachimudeditor.common.adapters.plugins import KNOWN_KINDS, discover

SCHEMA_NAME = "pachimudeditor.schema.json"
"""Nome del file scritto nella cartella di lavoro e referenziato dall'intestazione `yaml-language-server`."""
SCHEMA_HEADER = f"# yaml-language-server: $schema=./{SCHEMA_NAME}\n"
"""Prima riga del `pachimudeditor.yaml` generato da `init`."""
SCHEMA_ID = "https://pachimudeditor.local/schemas/pachimudeditor.schema.json"

_STR = {"type": "string"}

_LIVE: dict[str, Any] = {
    "type": "object",
    "description": "Canale live verso il MUD acceso (modulo livectl).",
    "additionalProperties": False,
    "properties": {
        "transport": {"const": "unix", "description": "Unico trasporto supportato."},
        "socket": {"type": "string", "description": "Percorso ASSOLUTO del socket Unix."},
        "token_env": {"type": "string", "description": "NOME della variabile d'ambiente col token (mai il token nel yaml)."},
        "timeout_ms": {"type": "integer", "minimum": 200, "maximum": 60000, "default": 3000, "description": "Timeout in ms."},
        "enabled": {"type": "boolean", "default": True, "description": "`false` spegne il canale senza toglierlo."},
    },
    "required": ["socket", "token_env"],
}
"""`params.live` di un mondo con canale live (stessa forma per pachimud e dikumod)."""

# shortcut: params dei kind ufficiali scritti a mano (l'AdapterPlugin non li dichiara), da riallineare se un adapter cambia.
_PARAMS: dict[str, dict[str, Any]] = {
    "pachimud": {
        "definitions_path": {
            "type": "string",
            "description": "Cartella `definitions/` del gioco: contenuti YAML (zones, classes, races). Obbligatoria, o da `config_path`.",
        },
        "base_definitions_path": {
            "type": "string",
            "description": "Classi e razze di default del gioco (sola lettura); con `config_path` e un checkout del gioco si ricava da solo.",
        },
        "definition_path": {"type": "string", "description": "Sinonimo di `definitions_path` (nome usato nel `pachimud.yaml`)."},
        "database_url": {
            "type": "string",
            "description": "URL SQLAlchemy del DB dei giocatori (account e personaggi); facoltativo (se assente: da `config_path`, altrimenti niente giocatori).",
        },
        "config_path": {"type": "string", "description": "Path del `pachimud.yaml` del game server, da cui leggere i valori mancanti."},
        "live": _LIVE,
    },
    "basedmud": {},
    "mapping": {},
    "dikumod": {
        "data_prefix": {"type": "string", "default": "dikumoddata", "description": "Prefisso dei file dati (`<prefisso>.wld`, ...)."},
        "variant": {
            "enum": ["dikumod", "dikumod2"],
            "description": "Variante Diku (di norma rilevata da sola; solo `dikumod` e' supportata).",
        },
        "spec_assign": {
            "type": "string",
            "description": "Percorso ASSOLUTO di `spec_assign.c` (sola lettura; default `<radice>/src/spec_assign.c`): procedura speciale dei mob e filtro «insegna / gain».",
        },
        "rent_vnum": {
            "enum": ["signed", "unsigned"],
            "default": "signed",
            "description": "Tipo di `item_number` nel rent dei giocatori: `signed` (`sh_int`, vnum max 32767) o `unsigned` (`ush_int`, max 65535: gioco con la patch `leu-rent-vnum-unsigned.patch`).",
        },
        "live": _LIVE,
    },
}


def _world_schema(kinds: list[str]) -> dict[str, Any]:
    """Lo schema di un elemento di `webeditor_worlds`, con i `params` specifici per ogni `kind` (`if/then`)."""
    return {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string", "description": "Identificativo del mondo (header `X-World`)."},
            "kind": {"enum": kinds, "default": "pachimud", "description": "Tipo di adapter."},
            "name": {"type": ["string", "null"], "description": "Nome mostrato nell'editor."},
            "path": {"type": ["string", "null"], "description": "Cartella/file dei dati (adapter su file)."},
            "mapping": {"type": ["string", "null"], "description": "Per `kind: mapping`: path del YAML di mappatura."},
            "params": {"type": "object", "description": "Parametri dipendenti dal `kind`."},
            "read_only": {"type": "boolean", "default": False, "description": "Rifiuta le scritture."},
            "config_path": {"type": ["string", "null"], "description": "Per `kind: pachimud`: path del `pachimud.yaml` del game server."},
        },
        "allOf": [
            {
                "if": {"properties": {"kind": {"const": kind}}, "required": ["kind"]},
                "then": {"properties": {"params": {"type": "object", "properties": props, "additionalProperties": not props}}},
            }
            for kind, props in _PARAMS.items()
        ],
    }


def build_schema() -> dict[str, Any]:
    """Lo schema completo di `pachimudeditor.yaml` (kind ufficiali piu' quelli dei plugin installati)."""
    from pachifast.config.schema import build_config_schema

    schema = build_config_schema()
    kinds = sorted({*KNOWN_KINDS, *discover()})
    props: dict[str, Any] = dict(schema.get("properties", {}))
    props["webeditor_worlds"] = {
        "type": "array",
        "description": "Mondi dell'editor. Nessun mondo e' implicito (alternativa: variabile WEBEDITOR_WORLDS, JSON).",
        "items": _world_schema(kinds),
    }
    props["webeditor_default_world"] = {"type": ["string", "null"], "description": "Id del mondo usato senza `X-World`."}
    props["webeditor_convert_journal_dir"] = {
        "type": ["string", "null"],
        "description": "Cartella del giornale delle conversioni tra mondi (disattivato se assente).",
    }
    props["config_path"] = {"type": ["string", "null"], "description": "Path del `pachimud.yaml` del game server (kind pachimud)."}
    return {
        **schema,
        "$id": SCHEMA_ID,
        "title": "pachimudeditor.yaml",
        "description": "Configurazione di pachimudeditor: file pachifast piu' le chiavi dell'editor. Ambiente e .env hanno la precedenza.",
        "properties": props,
        "additionalProperties": True,
    }


def render_schema() -> str:
    """Lo schema serializzato (JSON indentato, newline finale)."""
    return json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"
