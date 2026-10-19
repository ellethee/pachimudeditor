"""Stato e utilita' comuni ai mixin di `MappingAdapter`: mapping caricato, archivio, lock, mapper, uso dei vnum."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error
from pachimudeditor.common.enums import Direction

from pachimudeditor_adapter_mapping.grammar import Record
from pachimudeditor_adapter_mapping.model import EntityMapper, ResetMapper, Tables
from pachimudeditor_adapter_mapping.schema import RecordGrammar, TaggedStep, load_mapping
from pachimudeditor_adapter_mapping.store import FileEntry, Store, ZoneUnit
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    EntityKind,
    ExitOut,
    ExtraDescriptionOut,
    MobOut,
    ObjectOut,
    ResetCommandDraft,
    ResetUsage,
    RoomOut,
    ZoneOut,
)
from pachimudeditor.sdk import WorldConfig


def tag_grammar(grammar: RecordGrammar, list_name: str | None) -> RecordGrammar:
    """Grammatica fittizia degli elementi della lista `list_name` (passi del tag con `into: list_name`)."""
    for step in grammar.steps:
        if isinstance(step, TaggedStep):
            for ts in step.tags.values():
                if ts.into == list_name:
                    return RecordGrammar(steps=ts.steps)
    return RecordGrammar()


class MappingSupport:
    """Configurazione, archivio, mapper e controlli condivisi dai mixin."""

    def __init__(self, config: WorldConfig) -> None:
        """Carica la mappatura (`config.mapping`) e prepara l'archivio su `config.path` (nessuna lettura finche' non serve).

        Raises:
            ValueError: `mapping`/`path` mancanti o non validi (`MappingConfigError` per il YAML).
        """
        if not config.mapping:
            raise ValueError("Il mondo `mapping` richiede `mapping` (percorso del YAML di mappatura)")
        if not config.path:
            raise ValueError("Il mondo `mapping` richiede `path` (cartella dei dati)")
        root = Path(config.path).expanduser()
        if not root.is_dir():
            raise ValueError(f"Cartella dei dati non trovata: {root}")
        mapping_path = Path(config.mapping).expanduser()
        self.config = config
        self.spec = load_mapping(mapping_path)
        self.tables = Tables(self.spec, mapping_path.resolve().parent)
        self.store = Store(self.spec, root.resolve())
        self.lock = asyncio.Lock()
        """Un solo scrittore per volta: una scrittura puo' toccare piu' file."""
        self.rules = self.spec.rules
        model, records = self.spec.model, self.spec.grammar.records
        self.entity_record = {
            sec.entity: sec.record for fg in self.spec.grammar.files.values() for sec in fg.sections
        }  # ultima grammatica per entita' (le zone hanno stili diversi: vedi `zone_record`)
        zone_rec = next(sec.record for fg in self.spec.grammar.files.values() for sec in fg.sections if sec.entity == model.zone.entity)
        zr = self.spec.layout.zone_range
        consumed = frozenset(
            t.split(".")[0] for fm in (zr.bottom, zr.top) if fm is not None for t in ([fm.from_] if fm.from_ else []) + list(fm.to or {})
        )
        self.zone_map = EntityMapper(
            ZoneOut, model.zone, records[zone_rec], self.tables,
            structural=frozenset({"id", "vnum", "bottom_vnum", "top_vnum", "enabled"}), consumed=consumed,
            children=frozenset({model.zone.resets.field} if model.zone.resets and model.zone.resets.field else ()),
        )  # fmt: skip
        room_g, key = records[self.entity_record[model.room.entity]], frozenset({"id", "vnum", "zone_id"})
        lists = frozenset(n for n in (model.room.exits, model.room.extra_descriptions) if n)
        self.room_map = EntityMapper(
            RoomOut, model.room, room_g, self.tables, structural=key, children=lists,
            key_field=room_g.key,
        )  # fmt: skip
        mob_g, obj_g = records[self.entity_record[model.mob.entity]], records[self.entity_record[model.object.entity]]
        self.mob_map = EntityMapper(MobOut, model.mob, mob_g, self.tables, structural=key, key_field=mob_g.key)
        self.object_map = EntityMapper(ObjectOut, model.object, obj_g, self.tables, structural=key, key_field=obj_g.key)
        door_resets = model.exit.door_state == "resets"
        exit_structural = {"id", "room_id", "target_room_id", "target_room_vnum", "target_room_name"} | (
            {"is_open", "is_locked"} if door_resets else set()
        )
        self.exit_map = EntityMapper(
            ExitOut, model.exit, tag_grammar(room_g, model.room.exits), self.tables, structural=frozenset(exit_structural)
        )
        self.extra_desc_map = EntityMapper(
            ExtraDescriptionOut, model.extra_description, tag_grammar(room_g, model.room.extra_descriptions), self.tables,
            structural=frozenset({"id", "room_id"}),
        )  # fmt: skip
        self.reset_map = ResetMapper(self.spec, self.tables)

    # ------------------------------------------------------------------ comuni

    def ensure_writable(self) -> None:
        """409 `world.read_only` se il mondo e' in sola lettura (ultima difesa dell'adapter)."""
        if self.config.read_only:
            raise api_error(409, "world.read_only")

    def sync(self) -> Store:
        """Riallinea la cache al disco e restituisce l'archivio."""
        self.store.refresh()
        return self.store

    @asynccontextmanager
    async def writing(self) -> AsyncIterator[Store]:
        """Sezione di scrittura: lock unico e cache aggiornata; se qualcosa fallisce la cache e' invalidata (nessuna
        modifica in memoria non salvata deve restare o finire su disco al salvataggio successivo)."""
        async with self.lock:
            store = self.sync()
            try:
                yield store
            except BaseException:
                store.invalidate()
                raise

    def zone_or_404(self, zone_id: int) -> ZoneUnit:
        """La zona `zone_id` (404 `zones.not_found`)."""
        unit = self.sync().zone_by_id(zone_id)
        if unit is None:
            raise api_error(404, "zones.not_found")
        return unit

    def find_or_404(self, kind: str, vnum: int, code: str) -> tuple[ZoneUnit, Record]:
        """`(zona, record)` per vnum (404 `code`)."""
        found = self.sync().find(kind, vnum)
        if found is None:
            raise api_error(404, code)
        return found

    def key_name(self, kind: str) -> str:
        """Nome del campo vnum del record di `kind`."""
        return self.spec.grammar.records[self.entity_record[kind]].key or "vnum"

    def vnum(self, rec: Record) -> int:
        """Vnum del record."""
        return int(rec.fields[self.key_name(rec.entity)])

    def check_vnum_in_range(self, unit: ZoneUnit, vnum: int) -> None:
        """422 `mapping.vnum_out_of_range` se la zona ha un range e `vnum` ne e' fuori."""
        if self.rules.vnum_range_check and (unit.bottom, unit.top) != (0, 0) and not unit.bottom <= vnum <= unit.top:
            raise api_error(422, "mapping.vnum_out_of_range", vnum=vnum, bottom=unit.bottom, top=unit.top)

    # ------------------------------------------------------------------ script di reset

    def reset_fields(self, unit: ZoneUnit) -> list[dict[str, Any]]:
        """Tutti i record di reset della zona (comandi, commenti, sconosciuti) come dict di campi, in ordine."""
        src = self.spec.model.zone.resets
        if src is None:
            return []
        if src.field:
            return unit.header.fields.setdefault(src.field, [])
        spec = self._reset_section(unit)
        section = next((s for s in unit.file.doc.sections if s.spec is spec), None) if spec else None
        return [r.fields for r in section.records] if section else []

    def _reset_section(self, unit: ZoneUnit) -> Any:
        """La sezione di grammatica che contiene i reset della zona."""
        src = self.spec.model.zone.resets
        return next(
            (s for s in self.spec.grammar.files[unit.file.kind].sections if src and (s.header == src.section or s.entity == src.section)),
            None,
        )

    def set_reset_fields(self, unit: ZoneUnit, items: list[dict[str, Any]]) -> None:
        """Sostituisce lo script; i dict gia' presenti riusano il loro `Record` (testo sorgente invariato)."""
        src = self.spec.model.zone.resets
        if src is None:
            return
        if src.field:
            unit.header.fields[src.field] = items
            return
        spec = self._reset_section(unit)
        section = self.store.ensure_section(unit.file, spec)
        by_id = {id(r.fields): r for r in section.records}
        section.records[:] = [by_id.get(id(d)) or Record(spec.entity, d, spec.record, spec.header or "") for d in items]

    def commands(self, unit: ZoneUnit) -> list[dict[str, Any]]:
        """I dict dei soli comandi mappati (esclusi commenti e comandi che il modello non conosce)."""
        return [f for f in self.reset_fields(unit) if self.reset_map.is_command(f)]

    def unmapped_commands(self, unit: ZoneUnit) -> int:
        """Quanti record dello script non sono ne' comandi mappati ne' commenti."""
        return sum(1 for f in self.reset_fields(unit) if not self.reset_map.is_command(f) and not self.reset_map.is_comment(f))

    # ------------------------------------------------------------------ uso dei vnum

    def find_usage(self, kind: EntityKind, vnum: int, *, include_exit_keys: bool = True) -> list[ResetUsage]:
        """Reset (di ogni zona) che referenziano `vnum` come `kind`; per gli oggetti anche le chiavi delle uscite."""
        fields: dict[Any, list[str]] = {}
        for command_type, name in rules.USAGE_FIELDS[kind]:
            fields.setdefault(command_type, []).append(name)
        usage: list[ResetUsage] = []
        for unit in self.store.zones:
            for index, f in enumerate(self.commands(unit)):
                out = self.reset_map.out(unit.zone_id, index, f)
                if out.command_type in fields and any(getattr(out, n) == vnum for n in fields[out.command_type]):
                    usage.append(
                        ResetUsage(
                            zone_id=unit.zone_id,
                            zone_name=self.zone_name(unit),
                            reset_command_id=index,
                            order_index=index,
                            command_type=out.command_type,
                        )
                    )
        if kind == "object" and include_exit_keys:
            exits_name, key_field = self.spec.model.room.exits, self.spec.model.exit.key_field
            for unit in self.store.zones:
                for room in unit.items["room"]:
                    for x in room.fields.get(exits_name, []):
                        if key_field and x.get(key_field) == vnum and vnum > 0:
                            direction = int(self.exit_map.bindings["direction"].read(x))
                            usage.append(
                                ResetUsage(
                                    zone_id=unit.zone_id,
                                    zone_name=self.zone_name(unit),
                                    source="exit_key",
                                    exit_id=self.vnum(room) * self.rules.exit_id_stride + direction,
                                    room_id=self.vnum(room),
                                    room_vnum=self.vnum(room),
                                )  # fmt: skip
                            )
        return usage

    def zone_name(self, unit: ZoneUnit) -> str:
        """Nome leggibile della zona."""
        return str(self.zone_map.bindings["name"].read(unit.header.fields))

    def ensure_unused(self, kind: EntityKind, vnum: int, code: str, *, include_exit_keys: bool = True) -> None:
        """409 `code` se `vnum` e' referenziato (reset e, per gli oggetti, chiavi di uscite)."""
        rules.raise_if_used(self.find_usage(kind, vnum, include_exit_keys=include_exit_keys), code)

    # ------------------------------------------------------------------ riferimenti dal validatore

    def reset_lookup(self) -> "MappingResetLookup":
        """`rules.ResetLookup` sui file."""
        return MappingResetLookup(self)

    def drafts_of(self, commands: Any) -> list[ResetCommandDraft]:
        """Comandi in ingresso come bozze (nomi Python)."""
        return [ResetCommandDraft.model_validate(c.model_dump(by_alias=False)) for c in commands]

    def files_of(self, *records: Record) -> list[FileEntry]:
        """I file che contengono i record."""
        return [self.store.file_of(r) for r in records]


class MappingResetLookup:
    """`rules.ResetLookup` sui file di dati."""

    def __init__(self, support: MappingSupport) -> None:
        """Usa l'archivio (gia' sincronizzato) per le verifiche di esistenza."""
        self.support = support

    async def existing_vnums(self, kind: EntityKind, vnums: set[int]) -> set[int]:
        """Quali tra `vnums` esistono come stanza/mob/oggetto in qualsiasi zona."""
        return {v for v in vnums if self.support.store.find(kind, v) is not None}

    async def exit_has_door(self, room_vnum: int, direction: int) -> bool | None:
        """`None` se la stanza non ha l'uscita, altrimenti se e' una porta."""
        found = self.support.store.find("room", room_vnum)
        if found is None:
            return None
        s = self.support
        for x in found[1].fields.get(s.spec.model.room.exits, []):
            if int(s.exit_map.bindings["direction"].read(x)) == Direction(direction).value:
                from pachimudeditor.common.enums import DoorFlag

                return s.exit_map.bindings["door_flag"].read(x) != DoorFlag.NONE
        return None


__all__ = ["MappingResetLookup", "MappingSupport", "tag_grammar"]
