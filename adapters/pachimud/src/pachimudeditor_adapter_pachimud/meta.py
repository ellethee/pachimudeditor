"""Metadati (enum, razze, classi) del mondo pachimud (mixin di `PachimudAdapter`)."""

from enum import Enum

from pachimudeditor_adapter_pachimud.base import PachimudSupport
from pachimudeditor_adapter_pachimud.definitions import read_classes, read_races
from pachimudeditor.common.adapters.models import ContentRef, Option
from pachimudeditor.common.enums import Direction, DoorFlag, ObjectType, SectorType, Sex, ZoneCommandType, ZoneResetMode


def _humanize(value: str) -> str:
    """`"WATER_NOSWIM"` -> `"Water noswim"`."""
    return value.replace("_", " ").capitalize()


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
            "objectType": enum_options(ObjectType),
            "zoneCommandType": enum_options(ZoneCommandType),
        }

    async def races(self) -> list[ContentRef]:
        """Le razze di `definitions/races/*.yaml`, rilette ad ogni chiamata (vuote senza `definitions_path`)."""
        return sorted(
            (ContentRef(id=race.race_id, name=race.name) for race in read_races(self.params.definitions_path).values()),
            key=lambda ref: ref.name,
        )

    async def classes(self) -> list[ContentRef]:
        """Le classi di `definitions/classes/*.yaml`, rilette ad ogni chiamata."""
        return sorted(
            (ContentRef(id=cls.class_id, name=cls.name) for cls in read_classes(self.params.definitions_path).values()),
            key=lambda ref: ref.name,
        )

    def content_ids(self) -> tuple[set[str] | None, set[str] | None]:
        """Gli id di razze e classi caricate dagli YAML (per i warning sui riferimenti dei mob); `None` = nessun controllo."""
        if self.params.definitions_path is None or not self.params.definitions_path.is_dir():
            return None, None
        return set(read_races(self.params.definitions_path)), set(read_classes(self.params.definitions_path))
