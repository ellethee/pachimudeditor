"""`MappingAdapter`: un adapter generico guidato da un file YAML di mappatura (`kind: mapping`).

Configurazione (`webeditor_worlds`)::

    - {id: rom, kind: mapping, name: ROM, mapping: /percorso/rom.yaml, path: /percorso/a/basedmud/area, read_only: false}

`mapping` e' il YAML di mappatura (layout dei file, grammatica dei record, mapping sui DTO neutri: vedi
`docs/adapters/mapping-guide.md`), `path` la radice dei dati. Convenzioni:

- `id == vnum` per stanze, mob, oggetti; zona: `model.zone.id` (vnum minimo, `top` o posizione; senza valore univoco
  `-(posizione)`); uscita `vnum * exit_id_stride + direzione`; extra description `vnum * extra_id_stride + posizione`;
  reset = posizione nello script (commenti esclusi);
- cio' che non ha un campo neutro e' in `extra` (camelCase, riscrivibile);
- ogni scrittura riscrive solo i file toccati, in modo atomico: i record non modificati restano byte per byte.
"""

from enum import Enum

from pachimudeditor.common.enums import Sex
from pachimudeditor.common.enums import ObjectType
from pachimudeditor.common.enums import ZoneCommandType, ZoneResetMode
from pachimudeditor.common.enums import Direction, DoorFlag, SectorType

from pachimudeditor_adapter_mapping.model import EntityMapper, to_camel
from pachimudeditor_adapter_mapping.prototypes import PrototypesMixin
from pachimudeditor_adapter_mapping.zones import ZonesMixin
from pachimudeditor.sdk import AdapterCapabilities, AdapterInfo, WorldAdapter
from pachimudeditor.sdk import describe_resource, finish_resource, xf
from pachimudeditor.common.adapters.models import (
    ContentRef,
    ExitIn,
    ExitOut,
    ExtraDescriptionIn,
    ExtraDescriptionOut,
    MobIn,
    MobOut,
    ObjectIn,
    ObjectOut,
    Option,
    ResetCommandIn,
    ResetCommandOut,
    RoomDetail,
    RoomIn,
    ZoneIn,
    ZoneOut,
)


def _options(enum_cls: type[Enum]) -> list[Option]:
    """Opzioni (valore, etichetta) di un'enum dei DTO."""
    return [Option(value=m.value, label=m.name.replace("_", " ").capitalize()) for m in enum_cls]


class MappingAdapter(ZonesMixin, PrototypesMixin, WorldAdapter):
    """Adapter dei file di dati di un MUD descritto da un YAML di mappatura (vedi docstring del modulo)."""

    def capabilities(self) -> AdapterCapabilities:
        """Nucleo + script di reset + extra description; niente panoramica, istanze, giocatori, trasferimento, contenuti."""
        return AdapterCapabilities(
            read_only=self.config.read_only,
            supports_reset_scripts=self.spec.model.zone.resets is not None,
            supports_extra_descriptions=bool(self.spec.model.room.extra_descriptions),
        )

    # ------------------------------------------------------------------ describe

    def _enum_keys(self, mapper: EntityMapper) -> dict[str, str]:
        """Campo del DTO -> chiave di `enums()` per i campi di flag con una tabella esposta."""
        return {name: b.table.expose for name, b in mapper.bindings.items() if b.table is not None and b.table.expose and b.is_list}

    def describe(self) -> AdapterInfo:
        """Descrittori dei campi (dai DTO) con le tabelle esposte, i campi non supportati/derivati e le chiavi di `extra`
        (i campi del record non mappati: `mapper.extra_descriptors()`)."""
        zone_files = self.spec.layout.mode == "zone_files"
        pairs = [
            (describe_resource("zone", ZoneOut, ZoneIn), self.zone_map),
            (describe_resource("room", RoomDetail, RoomIn, skip=frozenset({"extra", "exits", "extra_descriptions"})), self.room_map),
            (describe_resource("exit", ExitOut, ExitIn, read_only=frozenset({"id", "room_id"})), self.exit_map),
            (describe_resource("extra_description", ExtraDescriptionOut, ExtraDescriptionIn), None),
            (describe_resource("mob", MobOut, MobIn), self.mob_map),
            (describe_resource("object", ObjectOut, ObjectIn), self.object_map),
            (describe_resource("reset_command", ResetCommandOut, ResetCommandIn), None),
        ]
        resources = []
        for info, mapper in pairs:
            keys = self._enum_keys(mapper) if mapper is not None else {}
            more = tuple(
                self.spec.grammar.records[sec.record]
                for fg in self.spec.grammar.files.values()
                for sec in fg.sections
                if info.type == "zone" and sec.entity == self.spec.model.zone.entity
            )
            extra = mapper.extra_descriptors(more) if mapper is not None else []
            if info.type == "zone" and zone_files:
                extra = [xf("file", ro=True), xf("style", ro=True), *extra]
            resources.append(
                finish_resource(
                    info,
                    extra,
                    enums={_camel(k): v for k, v in keys.items()},
                    unsupported=frozenset(mapper.unsupported_names())
                    if mapper is not None
                    else (frozenset({"ifValue", "comment"}) if info.type == "reset_command" else frozenset()),
                    read_only=frozenset(mapper.derived_names()) if mapper is not None else frozenset(),
                )
            )
        return AdapterInfo(
            id=self.config.id, kind=self.config.kind, name=self.config.name or self.spec.name,
            capabilities=self.capabilities(), resources=resources,
        )  # fmt: skip

    # ------------------------------------------------------------------ meta

    async def enums(self) -> dict[str, list[Option]]:
        """Enum standard dei DTO piu' le tabelle della mappatura con `expose` (flag: valore = bit; tipi: indice)."""
        out: dict[str, list[Option]] = {
            "sectorType": _options(SectorType),
            "direction": _options(Direction),
            "doorFlag": _options(DoorFlag),
            "zoneResetMode": _options(ZoneResetMode),
            "sex": _options(Sex),
            "objectType": _options(ObjectType),
            "zoneCommandType": _options(ZoneCommandType),
        }
        for table in self.tables.tables.values():
            if table.expose:
                out[table.expose] = table.options()
        return out

    def _refs(self, source: list[str] | str) -> list[ContentRef]:
        """Elenco di nomi da una lista inline o da una tabella."""
        names = source if isinstance(source, list) else list(self.tables[source].by_name)
        return [ContentRef(id=n, name=n.capitalize()) for n in names]

    async def races(self) -> list[ContentRef]:
        """Razze dichiarate in `meta.races` (vuote se la mappatura non le ha)."""
        return self._refs(self.spec.meta.races)

    async def classes(self) -> list[ContentRef]:
        """Classi dichiarate in `meta.classes`."""
        return self._refs(self.spec.meta.classes)


def _camel(name: str) -> str:
    """`extra_flags` -> `extraFlags`."""
    return to_camel(name)
