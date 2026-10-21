"""JSON Schema di `pachimudeditor.yaml`: struttura, kind/params, esempi del repo e file committato in radice."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from pachimudeditor.cli.helpers.schema import SCHEMA_HEADER, SCHEMA_ID, SCHEMA_NAME, build_schema, render_schema
from pachimudeditor.cli.helpers.templates import render_config

ROOT = Path(__file__).resolve().parents[2]


def _check(config: dict[str, Any], schema: dict[str, Any]) -> None:
    """Valida `config`: con `jsonschema` se installato, altrimenti controlli strutturali su mondi, kind e params."""
    try:
        import jsonschema
    except ImportError:
        worlds = schema["properties"]["webeditor_worlds"]["items"]
        rules = {r["if"]["properties"]["kind"]["const"]: r["then"]["properties"]["params"] for r in worlds["allOf"]}
        for world in config.get("webeditor_worlds") or []:
            assert world["kind"] in worlds["properties"]["kind"]["enum"]
            assert set(world) <= set(worlds["properties"])
            rule = rules.get(world["kind"])
            if rule and not rule["additionalProperties"]:
                assert set(world.get("params", {})) <= set(rule["properties"])
        return
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(config, schema)


def test_schema_structure() -> None:
    """Chiavi pachifast e dell'editor presenti, `kind` come enum, `params` per kind con `if/then`."""
    schema = build_schema()
    assert schema["$id"] == SCHEMA_ID and schema["title"] == "pachimudeditor.yaml" and schema["additionalProperties"] is True
    props = schema["properties"]
    assert {"server", "auth", "webeditor_worlds", "webeditor_default_world", "webeditor_convert_journal_dir", "config_path"} <= set(props)
    items = props["webeditor_worlds"]["items"]
    assert {"pachimud", "basedmud", "dikumod", "mapping"} <= set(items["properties"]["kind"]["enum"])
    dikumod = next(r for r in items["allOf"] if r["if"]["properties"]["kind"]["const"] == "dikumod")
    assert {"data_prefix", "live"} <= set(dikumod["then"]["properties"]["params"]["properties"])
    assert json.loads(render_schema()) == schema


def test_example_and_generated_config_validate() -> None:
    """`pachimudeditor.example.yaml` e il config generato da `init` rispettano lo schema; ha l'intestazione."""
    schema = build_schema()
    generated = render_config()
    assert generated.startswith(SCHEMA_HEADER)
    for text in (generated, (ROOT / "pachimudeditor.example.yaml").read_text(encoding="utf-8")):
        _check(yaml.safe_load(text) or {}, schema)


def test_params_of_wrong_kind_rejected() -> None:
    """Un param sconosciuto per il kind (o un kind inesistente) non passa."""
    schema = build_schema()
    bad_param = {"webeditor_worlds": [{"id": "x", "kind": "dikumod", "params": {"nope": 1}}]}
    bad_kind = {"webeditor_worlds": [{"id": "x", "kind": "boh"}]}
    for config in (bad_param, bad_kind):
        with pytest.raises((AssertionError, Exception)):
            _check(config, schema)


def test_committed_schema_is_up_to_date() -> None:
    """`pachimudeditor.schema.json` in radice e' quello generato (rigenerarlo: `pachimudeditor schema -o pachimudeditor.schema.json`)."""
    assert (ROOT / SCHEMA_NAME).read_text(encoding="utf-8") == render_schema()
