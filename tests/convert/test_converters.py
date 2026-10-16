"""Convertitori di coppia: casi "golden" (`golden/cases.json`) sui DTO, senza I/O.

Ogni caso parte da un DTO base (valori neutri) con i campi di `set` sovrascritti, lo passa dal convertitore della
coppia e confronta i campi attesi (`expect`, sottoinsieme del DTO di arrivo in camelCase; `null` = elemento scartato)
e l'insieme delle perdite `(codice, gravita')`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from pachimudeditor.common.adapters.convert.converter import ConvertContext, get_converter
from pachimudeditor.common.adapters.models import MobOut, ObjectOut, ResetCommandOut, RoomOut

CASES = json.loads((Path(__file__).parent / "golden" / "cases.json").read_text(encoding="utf-8"))

BASE: dict[str, tuple[type, dict[str, Any]]] = {
    "mob": (
        MobOut,
        {
            "id": 1,
            "vnum": 1,
            "zoneId": 1,
            "keywords": "m",
            "shortDescription": "un mob",
            "longDescription": "",
            "detailedDescription": "",
            "level": 1,
            "thac0": 20,
            "armorClass": 0,
            "hpDiceCount": 1,
            "hpDieSize": 8,
            "hpBonus": 0,
            "damageDiceCount": 1,
            "damageDieSize": 4,
            "damageBonus": 0,
            "gold": 0,
            "experience": 0,
            "sex": 0,
            "flags": [],
            "raceId": None,
            "classId": None,
            "alignment": 0,
            "debuffSkillId": None,
            "shopId": None,
            "questIds": [],
            "isBanker": False,
            "teachesClassIds": None,
            "teachesSkillIds": None,
            "extra": {},
        },
    ),
    "object": (
        ObjectOut,
        {
            "id": 1,
            "vnum": 1,
            "zoneId": 1,
            "keywords": "o",
            "shortDescription": "un oggetto",
            "longDescription": "",
            "actionDescription": None,
            "objectType": 6,
            "weight": 1,
            "cost": 1,
            "rent": 0,
            "value0": None,
            "value1": None,
            "value2": None,
            "value3": None,
            "extraFlags": [],
            "wearFlags": [],
            "affects": {},
            "extra": {},
        },
    ),
    "room": (
        RoomOut,
        {
            "id": 1,
            "vnum": 1,
            "zoneId": 1,
            "name": "Stanza",
            "description": "",
            "sectorType": 0,
            "flags": [],
            "healRate": 100,
            "manaRate": 100,
            "clanId": None,
            "owner": None,
            "extra": {},
        },
    ),
    "reset": (
        ResetCommandOut,
        {
            "id": 0,
            "zoneId": 1,
            "orderIndex": 0,
            "commandType": 0,
            "ifFlag": False,
            "arg1": None,
            "arg2": None,
            "arg3": None,
            "arg4": None,
            "argStr": None,
            "extra": {},
        },
    ),
}


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden(case: dict[str, Any]) -> None:
    """Il caso produce i campi attesi e le perdite attese."""
    model, base = BASE[case["entity"]]
    source = model.model_validate({**base, **case["set"]})
    converter = get_converter(*case["pair"])
    converted = getattr(converter, case["entity"])(source, ConvertContext(target_races={"human", "elf", "song_bird", "orc"}))
    if case["expect"] is None:
        assert converted.value is None
    else:
        dumped = converted.value.model_dump(by_alias=True, mode="json")
        for key, value in case["expect"].items():
            assert dumped[key] == value, (key, dumped[key], value)
    assert sorted((l.code, l.severity) for l in converted.losses) == sorted(tuple(x) for x in case["losses"])


def test_pairs_registered_and_generic_fallback() -> None:
    """Le sei coppie dei tre mondi sono specifiche; qualunque altra e' il ripiego generico."""
    kinds = ("pachimud", "basedmud", "dikumod")
    for a in kinds:
        for b in kinds:
            if a != b:
                assert not get_converter(a, b).generic
    assert get_converter("mapping", "pachimud").generic
    assert get_converter("dikumod", "mapping").generic
