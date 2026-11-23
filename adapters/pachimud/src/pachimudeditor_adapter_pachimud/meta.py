"""Metadati (enum, razze, classi) del mondo pachimud (mixin di `PachimudAdapter`)."""

import json
from enum import Enum
from functools import cache
from pathlib import Path

from pachimudeditor_adapter_pachimud.base import PachimudSupport
from pachimudeditor_adapter_pachimud.definitions import read_classes, read_races
from pachimudeditor_adapter_pachimud.loaders import OPEN_COMMANDS
from pachimudeditor.common.adapters.models import ContentRef, Option
from pachimudeditor.common.enums import Direction, DoorFlag, ObjectType, SectorType, Sex, ZoneCommandType, ZoneResetMode


def _humanize(value: str) -> str:
    """`"WATER_NOSWIM"` -> `"Water noswim"` (`LIQUID_CONTAINER` si chiama `DRINKCON` nel gioco)."""
    return "Drinkcon" if value == "LIQUID_CONTAINER" else value.replace("_", " ").capitalize()


CLIMATES = ("temperate", "desert", "arctic")
"""Clima di una zona (`climate` di `zone.yaml`): sceglie i messaggi del meteo (pioggia, neve, tempesta di sabbia)."""


FLAGS_CATALOG = Path(__file__).with_name("flags.json")
"""Copia versionata di `json-schema/flags.json` del gioco (`pachimud json-schema`); `tests/test_pachimud_files.py` la confronta col gioco."""

FLAG_ENUMS: dict[str, str] = {
    "room": "pachimudRoomFlags",
    "mob": "pachimudMobFlags",
    "object_extra": "pachimudObjectExtraFlags",
    "object_wear": "pachimudObjectWearFlags",
}
"""Sezione del catalogo -> nome della lista in `enums()` (l'uscita `exit` e' `doorFlag`)."""


@cache
def flag_catalog() -> dict[str, list[dict[str, object]]]:
    """Il catalogo dei flag del gioco: `{sezione: [{name, aliases, description: {it, en}, origin, implemented}]}`."""
    return json.loads(FLAGS_CATALOG.read_text(encoding="utf-8"))


def flag_options(section: str) -> list[Option]:
    """Le opzioni di una sezione del catalogo: il nome canonico e' l'etichetta (e il valore scritto nel file), il valore intero la posizione."""
    return [
        Option(
            value=i,
            label=str(f["name"]),
            description=f["description"],  # type: ignore[arg-type]
            aliases=f["aliases"] or None,  # type: ignore[arg-type]
            origin=str(f["origin"]),
            implemented=bool(f["implemented"]),
        )
        for i, f in enumerate(flag_catalog()[section])
    ]


def name_options(names: tuple[str, ...]) -> list[Option]:
    """Opzioni di un elenco di nomi (il valore e' la posizione, l'etichetta il nome: e' l'editor `enum` dei campi `extra`)."""
    return [Option(value=i, label=name) for i, name in enumerate(names)]


def enum_options(enum_cls: type[Enum]) -> list[Option]:
    """Le opzioni (`value`, `label`) di tutti i membri di un'enum."""
    return [Option(value=member.value, label=_humanize(member.name)) for member in enum_cls]


class MetaMixin(PachimudSupport):
    """Liste di opzioni e contenuti YAML (razze/classi)."""

    async def enums(self) -> dict[str, list[Option]]:
        """`{name: [{value, label}]}` per ogni enum che i form usano (significato in `common/enums.py`)."""
        return {
            "sectorType": enum_options(SectorType),
            "direction": enum_options(Direction),
            "doorFlag": enum_options(DoorFlag),
            "zoneResetMode": enum_options(ZoneResetMode),
            "sex": enum_options(Sex),
            "climate": name_options(CLIMATES),
            "openCmd": name_options(OPEN_COMMANDS),
            "objectType": enum_options(ObjectType),
            **{enum: flag_options(section) for section, enum in FLAG_ENUMS.items()},
            "zoneCommandType": [o for o in enum_options(ZoneCommandType) if o.value != ZoneCommandType.RANDOMIZE_EXITS],
        }

    async def races(self) -> list[ContentRef]:
        """Le razze di `definitions/races/*.yaml`, rilette ad ogni chiamata (vuote senza `definitions_path`)."""
        return sorted(
            (ContentRef(id=race.race_id, name=race.name) for race in read_races(self.params.layers).values()),
            key=lambda ref: ref.name,
        )

    async def classes(self) -> list[ContentRef]:
        """Le classi di `definitions/classes/*.yaml`, rilette ad ogni chiamata."""
        return sorted(
            (ContentRef(id=cls.class_id, name=cls.name) for cls in read_classes(self.params.layers).values()),
            key=lambda ref: ref.name,
        )

    def content_ids(self) -> tuple[set[str] | None, set[str] | None]:
        """Gli id di razze e classi caricate dagli YAML (per i warning sui riferimenti dei mob); `None` = nessun controllo."""
        if not self.params.definitions_path.is_dir():
            return None, None
        return set(read_races(self.params.layers)), set(read_classes(self.params.layers))
