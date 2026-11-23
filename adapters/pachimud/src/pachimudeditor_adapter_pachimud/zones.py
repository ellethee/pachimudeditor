"""Zone (cartelle con `zone.yaml`) e script di reset (`resets*.yaml`) (mixin di `PachimudAdapter`).

Una zona nuova e' una cartella `<definitions>/zones/<Cartella>/` con il solo `zone.yaml` (la cartella e' `extra.folder`,
altrimenti ricavata dal nome). Lo script di reset si legge da tutti i `resets*.yaml` della zona e si scrive sempre in
`resets.yaml` (gli altri file di reset della zona vengono svuotati: i commenti dei reset non si conservano).
"""

import re
from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from pachimudeditor.common.adapters.models import (
    EntityKind,
    NextZoneVnum,
    ResetCommandDraft,
    ResetCommandIn,
    ResetCommandOut,
    ResetDraftScriptIn,
    ResetScriptIn,
    ResetValidation,
    ZoneCloneIn,
    ZoneIn,
    ZoneOut,
    ZonePageParams,
    ZonePatch,
    ZoneSummary,
)
from pachimudeditor.common.enums import ZoneResetMode
from pachimudeditor.sdk import conflict, rules
from pachimudeditor_adapter_pachimud import mapping, resets
from pachimudeditor_adapter_pachimud.base import PachimudResetLookup, PachimudSupport, make_page, paginate_list
from pachimudeditor_adapter_pachimud.loaders import LoaderZone
from pachimudeditor_adapter_pachimud.store import YamlFile, ZoneEntry, plain

ZONE_EXTRA = frozenset({"zoneId", "description", "folder", "climate", "prototypesOnly", "extendsZone"})


def slug(name: str) -> str:
    """`Foresta Nera` -> `ForestaNera` (nome di cartella)."""
    return re.sub(r"[^A-Za-z0-9]+", "", name.title())[:40]


def _zone_id_slug(name: str) -> str:
    """`Foresta Nera` -> `foresta_nera` (`zone_id` di `zone.yaml`)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "zona"


class ZonesMixin(PachimudSupport):
    """Operazioni su zone e script di reset."""

    # ------------------------------------------------------------------ utilita'

    def _check_zone_extra(self, extra: dict[str, Any], *, current: ZoneEntry | None) -> None:
        """422 `pachimud.extra_unknown` / `pachimud.extra_readonly` per chiavi non ammesse in `extra` di una zona."""
        for key, value in extra.items():
            if key not in ZONE_EXTRA:
                raise api_error(422, "pachimud.extra_unknown", key=key)
            if key == "folder" and current is not None and value != current.dir.name:
                raise api_error(422, "pachimud.extra_readonly", key=key)

    def _check_new_zone(self, vnum: int, bottom: int, top: int, *, skip: ZoneEntry | None = None) -> None:
        """409 `zones.vnum_taken` / `zones.range_overlap` per una zona con questo vnum e range."""
        others = [z for z in self.store.zones if z is not skip]
        if vnum in {z.vnum for z in others}:
            raise conflict("zones.vnum_taken", vnum=vnum)
        if (bottom, top) != (0, 0):
            clash = rules.range_clash(((z.model.name, z.vnum, z.model.bottom_vnum, z.model.top_vnum) for z in others), bottom, top)
            if clash is not None:
                raise conflict("zones.range_overlap", zone=clash[0], zone_vnum=clash[1])

    def _new_folder(self, requested: Any, name: str, vnum: int) -> str:
        """Nome della nuova cartella: `extra.folder` (validato, 409 se esiste) oppure uno derivato da `name`, mai esistente."""
        if requested:
            self.store.safe_folder(str(requested))
            if (self.store.root / str(requested)).exists():
                raise conflict("pachimud.folder_exists", name=str(requested))
            return str(requested)
        return self.store.free_folder(slug(name) or f"Zona{vnum}")

    def _create_zone_file(self, values: dict[str, Any], extra: dict[str, Any]) -> ZoneEntry:
        """Scrive cartella e `zone.yaml` di una nuova zona e restituisce la zona caricata."""
        folder = self._new_folder(extra.get("folder"), values["name"], values["vnum"])
        document = mapping.new_map(
            {
                "zone_id": extra.get("zoneId") or _zone_id_slug(values["name"]),
                "vnum": values["vnum"],
                "name": values["name"],
                "builder": values.get("builder", ""),
                **({"description": extra["description"]} if extra.get("description") else {}),
                **({"climate": extra["climate"]} if extra.get("climate") not in (None, "temperate") else {}),
                **({"prototypes_only": True} if extra.get("prototypesOnly") else {}),
                **({"extends_zone": extra["extendsZone"]} if extra.get("extendsZone") else {}),
                "bottom_vnum": values["bottom_vnum"],
                "top_vnum": values["top_vnum"],
                "max_level": values["max_level"],
                "lifespan_minutes": values["lifespan_minutes"],
                "reset_mode": ZoneResetMode(values["reset_mode"]).name,
                "enabled": values["enabled"],
            }
        )
        LoaderZone.model_validate(plain(document))
        path = self.store.safe_folder(folder) / "zone.yaml"
        file = YamlFile(path=path, kind="zone", doc=document, explicit_start=True)
        self.store.save(file)
        zone = self.sync().zone(values["vnum"])
        assert zone is not None
        return zone

    # ------------------------------------------------------------------ zone

    async def list_zones(self, params: ZonePageParams) -> PaginatedResponse[ZoneOut]:
        """Zone paginate (ordine di default per vnum), cercabili per nome/builder/vnum."""
        self.sync()
        zones = [mapping.zone_out(z) for z in self.store.zones]
        items, total = paginate_list(
            zones, params, lambda z: (z.name, z.builder, z.vnum), lambda z, f: getattr(z, f), ZonePageParams.order_fields or []
        )
        return make_page(ZoneOut, items, total, params)

    async def get_zone(self, zone_id: int) -> ZoneOut:
        """Una zona (404 `zones.not_found`)."""
        return mapping.zone_out(self.zone_or_404(zone_id))

    async def create_zone(self, data: ZoneIn) -> ZoneOut:
        """Crea la cartella della zona con il suo `zone.yaml` (il vnum deve essere libero)."""
        self.ensure_writable()
        values = data.model_dump(by_alias=False, exclude={"extra"})
        values.pop("min_level")  # il gioco non ha il livello minimo di zona: neutro, ignorato
        self._check_zone_extra(data.extra, current=None)
        async with self.writing():
            self._check_new_zone(data.vnum, 0, 0)
            return mapping.zone_out(self._create_zone_file(values, data.extra))

    async def update_zone(self, zone_id: int, data: ZonePatch) -> ZoneOut:
        """Aggiornamento parziale; i range finali (vnum e livelli) devono restare coerenti anche se il patch
        ne cambia solo un estremo (422 `zones.invalid_vnum_range` / `zones.invalid_level_range`); `vnum` libero."""
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        extra = data.extra or {}
        low = changes.pop(
            "min_level", 1
        )  # come in dikumod: il patch di un campo che il gioco non ha e' ignorato, ma il range resta coerente
        async with self.writing():
            zone = self.zone_or_404(zone_id)
            self._check_zone_extra(extra, current=zone)
            m = zone.model
            if "vnum" in changes and changes["vnum"] != zone.vnum and self.store.zone(changes["vnum"]) is not None:
                raise conflict("zones.vnum_taken", vnum=changes["vnum"])
            final = {n: changes.get(n, getattr(m, n)) for n in ("bottom_vnum", "top_vnum", "max_level")}
            rules.check_zone_ranges(final["bottom_vnum"], final["top_vnum"], low, final["max_level"])
            mapping.zone_apply(zone.file.doc, changes)
            for key in ("zoneId", "description", "climate"):
                if key in extra:
                    mapping.put(
                        zone.file.doc,
                        "zone_id" if key == "zoneId" else key,
                        extra[key],
                        default="temperate" if key == "climate" else "",
                        required=key == "zoneId",
                    )
            if "prototypesOnly" in extra:
                mapping.put(zone.file.doc, "prototypes_only", bool(extra["prototypesOnly"]), default=False)
            if "extendsZone" in extra:
                mapping.put(zone.file.doc, "extends_zone", extra["extendsZone"] or None)
            zone.revalidate()
            self.store.save(zone.file)
            return mapping.zone_out(self.zone_or_404(zone.vnum))

    async def delete_zone(self, zone_id: int) -> None:
        """Elimina la zona con i suoi file; 409 `zones.not_empty` finche' contiene ancora stanze, mob o oggetti.

        Si tolgono `zone.yaml` e i file `rooms*/mobs*/objects*/resets*.yaml` (vuoti, tranne i reset: appartengono alla zona);
        la cartella sparisce solo se resta vuota."""
        self.ensure_writable()
        async with self.writing():
            zone = self.zone_or_404(zone_id)
            summary = self._summary(zone)
            if summary.room_count or summary.mob_count or summary.object_count:
                raise conflict("zones.not_empty", rooms=summary.room_count, mobs=summary.mob_count, objects=summary.object_count)
            for file in [*zone.files, zone.file]:
                file.path.unlink(missing_ok=True)
            try:
                zone.dir.rmdir()
            except OSError:
                pass  # restano altri file (es. note): la cartella non e' piu' una zona ma non si tocca
            self.store.invalidate()

    @staticmethod
    def _summary(zone: ZoneEntry) -> ZoneSummary:
        """Conteggi del contenuto di una zona."""
        return ZoneSummary(room_count=len(zone.items["room"]), mob_count=len(zone.items["mob"]), object_count=len(zone.items["object"]))

    async def zone_summary(self, zone_id: int) -> ZoneSummary:
        """Conteggi di stanze, mob e oggetti."""
        return self._summary(self.zone_or_404(zone_id))

    async def next_zone_vnum(self, span: int) -> NextZoneVnum:
        """Un vnum di zona libero e un range `span` ampio che non tocca nessun'altra zona."""
        self.sync()
        vnum, bottom, top = rules.suggest_zone_range(((z.vnum, z.model.bottom_vnum, z.model.top_vnum) for z in self.store.zones), span)
        return NextZoneVnum(vnum=vnum, bottom_vnum=bottom, top_vnum=top)

    async def next_content_vnum(self, zone_id: int, kind: EntityKind) -> int:
        """Un vnum libero per una nuova stanza/mob/oggetto: uno oltre il piu' alto della zona (o il vnum minimo
        della zona se vuota), saltando i vnum gia' occupati altrove."""
        zone = self.zone_or_404(zone_id)
        highest = max((i.vnum for i in zone.items[kind]), default=None)
        candidate = highest + 1 if highest is not None else zone.model.bottom_vnum
        return rules.first_free_vnum(candidate, {v for v in self.store.vnums(kind) if v >= candidate})

    async def clone_zone(self, zone_id: int, data: ZoneCloneIn) -> ZoneOut:
        """Duplica una zona (non il contenuto); opzionalmente copia lo script di reset (i vnum restano quelli
        originali). Range della copia da `bottomVnum`/`topVnum` (409 `zones.range_overlap`) oppure 0-0."""
        self.ensure_writable()
        async with self.writing():
            source = self.zone_or_404(zone_id)
            bottom, top = data.bottom_vnum or 0, data.top_vnum or 0
            self._check_new_zone(data.vnum, bottom, top)
            m = source.model
            values = {
                "vnum": data.vnum, "name": data.name, "builder": m.builder, "bottom_vnum": bottom, "top_vnum": top,
                "max_level": m.max_level, "lifespan_minutes": m.lifespan_minutes,
                "reset_mode": ZoneResetMode[m.reset_mode], "enabled": m.enabled,
            }  # fmt: skip
            clone = self._create_zone_file(values, {"description": m.description, "climate": m.climate})
            if data.copy_reset_commands:
                commands = resets.to_out(clone.vnum, resets.flatten(source))
                resets.write(self.store, clone, [_as_in(c) for c in commands])
            return mapping.zone_out(self.zone_or_404(clone.vnum))

    # ------------------------------------------------------------------ reset

    async def list_reset_commands(self, zone_id: int) -> list[ResetCommandOut]:
        """Lo script di reset della zona (`id` = `orderIndex` = posizione)."""
        zone = self.zone_or_404(zone_id)
        return resets.to_out(zone.vnum, resets.flatten(zone))

    async def replace_reset_commands(self, zone_id: int, data: ResetScriptIn) -> list[ResetCommandOut]:
        """Sostituisce l'intero script; vnum inesistenti = 422 `zones.reset_unknown_*`. Il comando `R` non esiste nel
        gioco e `ifFlag`/`ifValue`/commento/`extra` non sono rappresentabili (422)."""
        self.ensure_writable()
        for index, c in enumerate(data.commands):
            if c.extra or c.comment is not None or c.if_value is not None or c.command_type in rules.EXTENDED_TYPES:
                raise api_error(422, "world.extra_unsupported", loc=("body", "commands", index))
        async with self.writing():
            zone = self.zone_or_404(zone_id)
            drafts = [ResetCommandDraft.model_validate(c.model_dump(by_alias=False)) for c in data.commands]
            rules.raise_script_errors(await rules.validate_script(PachimudResetLookup(self.store), drafts))
            new = [(c.command_type, c.arg1, c.arg2, c.arg3, c.arg4, c.arg_str) for c in data.commands]
            resets.build(data.commands)  # 422 se lo script non e' esprimibile prima di toccare i file
            if _normalized(new) != _normalized(resets.flatten(zone)):
                resets.write(self.store, zone, data.commands)
            return resets.to_out(zone_id, resets.flatten(self.zone_or_404(zone_id)))

    async def validate_reset_commands(self, zone_id: int, data: ResetDraftScriptIn) -> ResetValidation:
        """Controlla uno script senza salvarlo (errori e avvertimenti per passo)."""
        self.zone_or_404(zone_id)
        issues = rules.to_issues(await rules.validate_script(PachimudResetLookup(self.store), data.commands))
        return ResetValidation(ok=not any(i.severity == "error" for i in issues), issues=issues)


def _normalized(commands: list[Any]) -> list[tuple[Any, ...]]:
    """Comandi come tuple confrontabili (gli argomenti opzionali assenti valgono come nel file: massimo 1, limite 1)."""
    out = []
    for t, a1, a2, a3, a4, s in commands:
        if t.name in ("LOAD_OBJECT", "LOAD_MOB"):
            a2, a4 = 1 if a2 is None else a2, 1 if a4 is None else a4
        out.append((t, a1, a2, a3, a4, (s or "").upper() if t.name == "SET_DOOR_STATE" else s))
    return out


def _as_in(command: ResetCommandOut) -> Any:
    """Un `ResetCommandOut` come `ResetCommandIn` (per ricostruire lo script di una zona clonata)."""
    return ResetCommandIn(
        command_type=command.command_type,
        arg1=command.arg1,
        arg2=command.arg2,
        arg3=command.arg3,
        arg4=command.arg4,
        arg_str=command.arg_str,
    )
