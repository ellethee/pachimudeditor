"""Zone (file `.are`) e script di reset (mixin di `BasedMudAdapter`)."""

import copy
import re
from typing import Any

from pachimudeditor_adapter_basedmud.rom_lib import Area, AreaHeader, Reset
from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from pachimudeditor.common.enums import ZoneResetMode

from pachimudeditor_adapter_basedmud import mapping
from pachimudeditor_adapter_basedmud.base import (
    BasedMudResetLookup,
    BasedMudSupport,
    make_page,
    paginate_list,
    real_resets,
)
from pachimudeditor_adapter_basedmud.store import AreaEntry
from pachimudeditor.sdk import rules
from pachimudeditor.common.adapters.models import (
    EntityKind,
    NextZoneVnum,
    ResetCommandDraft,
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
from pachimudeditor.sdk import conflict


def _slug(name: str) -> str:
    """Nome di file di base da un nome di zona (`Foresta Nera` -> `forestanera`)."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())[:20] or "area"


class ZonesMixin(BasedMudSupport):
    """Operazioni su zone e script di reset."""

    # ------------------------------------------------------------------ utilita'

    def _zone_out(self, entry: AreaEntry) -> ZoneOut:
        """DTO neutro di una zona. `enabled` = il file e' in `area.lst`; il resto di `#AREADATA` e' in `extra`."""
        header = entry.header
        low, high, _ = mapping.parse_credits(header.credits)
        return ZoneOut(
            id=entry.zone_id,
            vnum=entry.zone_id,
            name=header.name,
            builder=mapping.header_builder(header),
            bottom_vnum=header.min_vnum,
            top_vnum=header.max_vnum,
            min_level=low,
            max_level=max(low, high),
            lifespan_minutes=mapping.LIFESPAN_MINUTES,
            reset_mode=ZoneResetMode.EMPTY,
            enabled=entry.listed,
            extra={
                "file": entry.name,
                "style": header.style,
                "credits": header.credits,
                "security": header.security,
                "vnumRaw": header.vnum_raw,
            },
        )

    def _zone_extra_handlers(self, entry_name: str | None, header: AreaHeader) -> dict[str, Any]:
        """Handler delle chiavi di `extra` di una zona (`file`/`style`/`vnumRaw` sono di sola lettura)."""

        def readonly(key: str, current: Any) -> Any:
            """Accetta solo il valore corrente (riscrivere l'`extra` letto e' un no-op)."""

            def check(value: Any) -> None:
                """422 se il valore e' diverso."""
                if value != current:
                    raise api_error(422, "basedmud.extra_readonly", key=key)

            return check

        def credits(value: Any) -> None:
            """Testo dei credits (`{ min max } Autore  Titolo`)."""
            header.credits = str(value)

        def security(value: Any) -> None:
            """Livello di sicurezza OLC."""
            if not isinstance(value, int):
                raise api_error(422, "basedmud.extra_invalid", key="security")
            header.security = value

        return {
            "file": readonly("file", entry_name) if entry_name else (lambda v: None),
            "style": readonly("style", header.style) if entry_name else (lambda v: None),
            "vnumRaw": readonly("vnumRaw", header.vnum_raw) if entry_name else (lambda v: None),
            "credits": credits,
            "security": security,
        }

    def _check_new_zone(self, vnum: int, bottom: int, top: int, *, skip: AreaEntry | None = None) -> None:
        """409 `zones.vnum_taken` / `zones.range_overlap` per una zona con questo vnum e range."""
        ranged = (bottom, top) != (0, 0)
        others = [z for z in self.store.zones if z is not skip]
        if ranged:
            clash = rules.range_clash(((z.header.name, z.zone_id, z.header.min_vnum, z.header.max_vnum) for z in others), bottom, top)
            if clash is not None:
                raise conflict("zones.range_overlap", zone=clash[0], zone_vnum=clash[1])
        if (bottom if ranged else vnum) in {z.zone_id for z in others}:
            raise conflict("zones.vnum_taken", vnum=bottom if ranged else vnum)

    def _new_file_name(self, requested: Any, name: str) -> str:
        """Nome del nuovo file: `extra.file` (validato, 409 se esiste) oppure uno derivato da `name`, mai esistente."""
        if requested:
            self.store.safe_path(str(requested))
            if (self.store.area_dir / str(requested)).exists():
                raise conflict("basedmud.file_exists", name=str(requested))
            return str(requested)
        base, n = _slug(name), 1
        while (self.store.area_dir / f"{base}{'' if n == 1 else n}.are").exists():
            n += 1
        return f"{base}{'' if n == 1 else n}.are"

    # ------------------------------------------------------------------ zone

    async def list_zones(self, params: ZonePageParams) -> PaginatedResponse[ZoneOut]:
        """Zone paginate (ordine di default per vnum), cercabili per nome/builder/vnum."""
        self.sync()
        zones = sorted((self._zone_out(e) for e in self.store.zones), key=lambda z: z.id)
        items, total = paginate_list(
            zones, params, lambda z: (z.name, z.builder, z.vnum), lambda z, f: getattr(z, f), ZonePageParams.order_fields or []
        )
        return make_page(ZoneOut, items, total, params)

    async def get_zone(self, zone_id: int) -> ZoneOut:
        """Una zona (404 `zones.not_found`)."""
        return self._zone_out(self.zone_or_404(zone_id))

    async def create_zone(self, data: ZoneIn) -> ZoneOut:
        """Crea un nuovo file `.are` (e lo elenca in `area.lst` se `enabled`).

        `id`/`vnum` della zona sono il suo `bottomVnum` (il `vnum` della richiesta conta solo se non c'e' un range);
        `extra` ammette `file` (nome del file), `credits` e `security`.
        """
        self.ensure_writable()
        async with self.writing():
            self.sync()
            self._check_new_zone(data.vnum, data.bottom_vnum, data.top_vnum)
            name = self._new_file_name(data.extra.get("file"), data.name)
            credits = f"{{ {data.min_level} {data.max_level} }} {data.builder or 'Unknown'}  {data.name}"
            header = AreaHeader(
                style="AREADATA", name=data.name, builders=data.builder, credits=credits,
                min_vnum=data.bottom_vnum, max_vnum=data.top_vnum, security=9,
            )  # fmt: skip
            mapping.apply_extra(data.extra, self._zone_extra_handlers(None, header))
            area = Area()
            area.header = header
            return self._zone_out(self.store.add_file(name, area, listed=data.enabled))

    async def update_zone(self, zone_id: int, data: ZonePatch) -> ZoneOut:
        """Aggiornamento parziale dell'intestazione.

        `vnum` non e' modificabile da solo (coincide con `bottomVnum`); `lifespanMinutes`/`resetMode` non esistono in
        ROM (valori costanti, il patch viene ignorato); `enabled` aggiunge/toglie il file da `area.lst`.
        """
        self.ensure_writable()
        changes = data.model_dump(by_alias=False, exclude_unset=True, exclude={"extra"})
        async with self.writing():
            entry = self.zone_or_404(zone_id)
            old = entry.header
            new = copy.copy(old)
            low, high, author = mapping.parse_credits(old.credits)
            bottom, top = changes.get("bottom_vnum", old.min_vnum), changes.get("top_vnum", old.max_vnum)
            low, high = changes.get("min_level", low), changes.get("max_level", high)
            rules.check_zone_ranges(bottom, top, low, high)
            if "vnum" in changes and changes["vnum"] not in (entry.zone_id, bottom):
                raise api_error(422, "basedmud.zone_vnum_is_range", vnum=changes["vnum"])
            if (bottom, top) != (old.min_vnum, old.max_vnum):
                self._check_new_zone(entry.zone_id, bottom, top, skip=entry)
                new.min_vnum, new.max_vnum, new.vnum_raw = bottom, top, None
            if "name" in changes:
                new.name = changes["name"]
            mapping.apply_extra(data.extra or {}, self._zone_extra_handlers(entry.name, new))
            if "builder" in changes and changes["builder"] != mapping.header_builder(new):
                if new.style == "AREADATA":
                    new.builders = changes["builder"]
                else:
                    new.credits = mapping.build_credits(new.credits, *mapping.parse_credits(new.credits)[:2], changes["builder"])
            if ("min_level" in changes or "max_level" in changes) and (low, high) != mapping.parse_credits(new.credits)[:2]:
                new.credits = mapping.build_credits(new.credits, low, high)
            name = entry.name
            if repr(new) != repr(old):
                entry.area.header = new
                self.store.save(entry)
            if "enabled" in changes and changes["enabled"] != entry.listed:
                self.store.set_listed(name, changes["enabled"])
            self.store.refresh()
            return self._zone_out(self.store.entries[name])

    async def delete_zone(self, zone_id: int) -> None:
        """Elimina il file `.are` (e la riga in `area.lst`); 409 `zones.not_empty` se ha ancora stanze, mob o oggetti."""
        self.ensure_writable()
        async with self.writing():
            entry = self.zone_or_404(zone_id)
            summary = self._summary(entry)
            if summary.room_count or summary.mob_count or summary.object_count:
                raise conflict("zones.not_empty", rooms=summary.room_count, mobs=summary.mob_count, objects=summary.object_count)
            self.store.set_listed(entry.name, False)
            entry.path.unlink(missing_ok=True)
            self.store.refresh()

    @staticmethod
    def _summary(entry: AreaEntry) -> ZoneSummary:
        """Conteggi del contenuto di una zona."""
        return ZoneSummary(room_count=len(entry.items("room")), mob_count=len(entry.items("mob")), object_count=len(entry.items("object")))

    async def zone_summary(self, zone_id: int) -> ZoneSummary:
        """Conteggi di stanze, mob e oggetti."""
        return self._summary(self.zone_or_404(zone_id))

    async def next_zone_vnum(self, span: int) -> NextZoneVnum:
        """Un vnum di zona libero (= vnum minimo) e un range `span` ampio, multiplo di 100, che non tocca altre zone."""
        self.sync()
        tops = [z.header.max_vnum for z in self.store.zones if (z.header.min_vnum, z.header.max_vnum) != (0, 0)]
        bottom = max(100, -(-(max(tops, default=0) + 1) // 100) * 100)
        return NextZoneVnum(vnum=bottom, bottom_vnum=bottom, top_vnum=bottom + span)

    async def next_content_vnum(self, zone_id: int, kind: EntityKind) -> int:
        """Un vnum libero: uno oltre il piu' alto della zona (o il vnum minimo se vuota), saltando i vnum occupati."""
        entry = self.zone_or_404(zone_id)
        highest = max((i.vnum for i in entry.items(kind)), default=None)
        candidate = highest + 1 if highest is not None else entry.header.min_vnum
        taken = {v for v in self.store._index[kind] if v >= candidate}  # noqa: SLF001
        return rules.first_free_vnum(candidate, taken)

    async def clone_zone(self, zone_id: int, data: ZoneCloneIn) -> ZoneOut:
        """Duplica l'intestazione in un nuovo file (non il contenuto); opzionalmente copia lo script di reset.
        Range della copia da `bottomVnum`/`topVnum` (409 `zones.range_overlap`) oppure 0-0."""
        self.ensure_writable()
        async with self.writing():
            source = self.zone_or_404(zone_id)
            bottom, top = data.bottom_vnum or 0, data.top_vnum or 0
            self._check_new_zone(data.vnum, bottom, top)
            header = AreaHeader(
                style="AREADATA", name=data.name, builders=source.header.builders, credits=source.header.credits,
                min_vnum=bottom, max_vnum=top, security=source.header.security,
            )  # fmt: skip
            area = Area()
            area.header = header
            if data.copy_reset_commands:
                area.resets.extend(mapping.copy_reset(r) for r in real_resets(source))
            return self._zone_out(self.store.add_file(self._new_file_name(None, data.name), area, listed=True))

    # ------------------------------------------------------------------ reset

    async def list_reset_commands(self, zone_id: int) -> list[ResetCommandOut]:
        """Lo script di reset della zona (`id` = `orderIndex` = posizione, righe di commento escluse)."""
        entry = self.zone_or_404(zone_id)
        return [mapping.reset_out(entry.zone_id, i, r) for i, r in enumerate(real_resets(entry))]

    async def replace_reset_commands(self, zone_id: int, data: ResetScriptIn) -> list[ResetCommandOut]:
        """Sostituisce lo script. I comandi invariati riusano il reset originale (stessi byte e commento); le righe
        di commento `*` vanno perse solo se lo script cambia davvero."""
        self.ensure_writable()
        async with self.writing():
            entry = self.zone_or_404(zone_id)
            drafts = [ResetCommandDraft.model_validate(c.model_dump(by_alias=False)) for c in data.commands]
            rules.raise_script_errors(await rules.validate_script(BasedMudResetLookup(self.store), drafts))
            old = real_resets(entry)
            pool: dict[Any, list[Reset]] = {}
            for reset in old:
                pool.setdefault(mapping.reset_key(reset), []).append(reset)
            new: list[Reset] = []
            for index, command in enumerate(drafts):
                built = mapping.reset_from(command, index)
                same = pool.get(mapping.reset_key(built))
                new.append(same.pop(0) if same else built)
            if len(new) != len(old) or any(a is not b for a, b in zip(new, old)):
                entry.area.resets[:] = new
                self.store.save(entry)
            return await self.list_reset_commands(zone_id)

    async def validate_reset_commands(self, zone_id: int, data: ResetDraftScriptIn) -> ResetValidation:
        """Controlla uno script senza salvarlo (errori e avvertimenti per passo)."""
        self.zone_or_404(zone_id)
        issues = rules.to_issues(await rules.validate_script(BasedMudResetLookup(self.store), data.commands))
        return ResetValidation(ok=not any(i.severity == "error" for i in issues), issues=issues)
