"""`PachimudAdapter`: il mondo pachimud, con i contenuti su file YAML e giocatori/account nel database di gioco.

Implementa `WorldAdapter` componendo i mixin per area (`zones`, `rooms`, `prototypes`, `meta`). NON importa il gioco.

- **Contenuti** (zone, stanze, uscite, mob, oggetti, reset, classi, razze): file YAML sotto `definitions_path`
  (`zones/<Zona>/{zone,rooms*,mobs*,objects*,resets*}.yaml`, `classes/`, `races/`), letti e scritti da `store.py`. `id == vnum`
  (la zona: `vnum` di `zone.yaml`). Il gioco non ricarica a caldo: le modifiche hanno effetto al suo riavvio.
- **Giocatori e account**: tabelle `account` e `player_character` del database indicato da `database_url` (riflesse,
  `schema.py`), riga per riga come le scrive il game server.

Capability: panoramica mondo, giocatori (se il DB c'e'), trasferimento di zone, razze/classi, script di reset ed extra
description. Niente istanze su disco: nel gioco vivono solo in memoria (si leggono dal canale live, `instances.list`).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pachifast.i18n import api_error
from starlette.concurrency import run_in_threadpool

from pachimudeditor.common.adapters.models import (
    ExitIn,
    ExitOut,
    ExtraDescriptionIn,
    ExtraDescriptionOut,
    ImportPreview,
    MobIn,
    MobOut,
    ObjectIn,
    ObjectOut,
    ResetCommandIn,
    ResetCommandOut,
    RoomDetail,
    RoomIn,
    ZoneBundle,
    ZoneIn,
    ZoneOut,
)
from pachimudeditor.common.enums import ZoneCommandType
from pachimudeditor.sdk import AdapterCapabilities, AdapterInfo, ResourceInfo, WorldAdapter, describe_resource, finish_resource
from pachimudeditor_adapter_pachimud import integrity
from pachimudeditor_adapter_pachimud.fields import EXTRA, FLAG_LISTS, READ_ONLY, UNSUPPORTED
from pachimudeditor_adapter_pachimud.live import LiveMixin
from pachimudeditor_adapter_pachimud.meta import MetaMixin
from pachimudeditor_adapter_pachimud.prototypes import PrototypesMixin
from pachimudeditor_adapter_pachimud.rooms import RoomsMixin
from pachimudeditor_adapter_pachimud.schema import SchemaIssue, SchemaReport, SchemaUnavailable
from pachimudeditor_adapter_pachimud.transfer import service as transfer
from pachimudeditor_adapter_pachimud.zones import ZonesMixin

log = logging.getLogger(__name__)


@dataclass
class WorldReport:
    """Stato del mondo per `worlds check`: contenuti YAML (conteggi, problemi dei file) e schema del DB dei giocatori."""

    zones: int
    rooms: int
    mobs: int
    objects: int
    db: SchemaReport | None = None
    problems: list[SchemaIssue] = field(default_factory=list)
    """Problemi dei file YAML (YAML rotto, voci non valide, vnum duplicate)."""

    @property
    def warnings(self) -> list[SchemaIssue]:
        """Problemi dei file e avvisi dello schema del DB (le semplici informazioni sono escluse)."""
        return [*self.problems, *(self.db.warnings if self.db is not None else [])]

    def summary(self) -> str:
        """Una riga per `worlds check`: `45 stanze, 28 mob, 32 oggetti; giocatori: schema ok, revisione X; 1 problema nei file`."""
        db = f"giocatori: {self.db.summary()}" if self.db is not None else "giocatori: DB non disponibile"
        problems = f"; {len(self.problems)} problemi nei file" if self.problems else ""
        return f"{self.rooms} stanze, {self.mobs} mob, {self.objects} oggetti; {db}{problems}"


class PachimudAdapter(ZonesMixin, RoomsMixin, PrototypesMixin, MetaMixin, LiveMixin, WorldAdapter):
    """Adapter del gioco pachimud (vedi docstring del modulo)."""

    min_object_rent = -1

    # ------------------------------------------------------------------ stato e capability

    def unavailable_reason(self) -> str | None:
        """Perche' il mondo non e' utilizzabile ora (cartella `zones` assente), o `None` se lo e'."""
        if not self.params.definitions_path.is_dir():
            return f"cartella delle definizioni non trovata: {self.params.definitions_path}"
        return None

    def players_schema(self, *, refresh: bool = False) -> SchemaReport | None:
        """Il rapporto di compatibilita' del DB dei giocatori, o `None` se non e' configurato/utilizzabile."""
        if self.connection is None:
            return None
        try:
            return self.connection.schema(refresh=refresh).report
        except SchemaUnavailable as exc:
            return exc.report

    def schema_report(self, *, refresh: bool = False) -> WorldReport | None:
        """Stato del mondo (contenuti YAML e DB dei giocatori) o `None` se le definizioni non esistono."""
        if self.unavailable_reason() is not None:
            return None
        store = self.sync()
        problems = [SchemaIssue("error" if i.severity == "error" else "warning", i.code, i.text()) for i in store.issues]
        if self.params.ignored_extra_paths:  # il gioco li applica, l'editor no: senza l'avviso mancherebbero contenuti senza spiegazione
            problems.append(
                SchemaIssue(
                    "warning",
                    "extra_definition_paths_ignored",
                    f"il gioco usa {len(self.params.ignored_extra_paths)} cartelle in extra_definition_paths che l'editor non legge: "
                    "i loro contenuti non compaiono (indicare le cartelle del gioco in params.definitions_path non le unisce)",
                )
            )
        return WorldReport(
            zones=len(store.zones),
            rooms=len(store.vnums("room")),
            mobs=len(store.vnums("mob")),
            objects=len(store.vnums("object")),
            db=self.players_schema(refresh=refresh),
            problems=problems,
        )

    def log_schema_report(self) -> None:
        """Scrive nel log lo stato del mondo (avvisi inclusi): da chiamare all'avvio dell'app."""
        name = f"mondo {self.config.id!r} ({self.params.definitions_path})"
        report = self.schema_report(refresh=True)
        if report is None:
            log.warning("%s non utilizzabile: %s", name, self.unavailable_reason())
            return
        log.info("%s: %s", name, report.summary())
        for issue in report.warnings:
            log.warning("%s: [%s] %s", name, issue.code, issue.message)

    def capabilities(self) -> AdapterCapabilities:
        """Le capability consentite dalla configurazione e dal DB dei giocatori; `read_only` e' da configurazione."""
        report = self.players_schema()
        return AdapterCapabilities(
            read_only=self.config.read_only,
            supports_world_overview=True,
            supports_players=report is not None and report.usable and not {"account", "player_character"} & set(report.missing_tables),
            supports_transfer=True,
            supports_content_races=True,
            supports_boards=report is not None and report.usable,
            supports_reset_scripts=True,
            supports_extra_descriptions=True,
            supports_live=self.live_settings is not None,
        )

    def describe(self) -> AdapterInfo:
        """Descrittori dei campi ricavati dagli schemi Pydantic dei DTO, con le chiavi di `extra` di pachimud."""

        def finish(info: ResourceInfo) -> ResourceInfo:
            """Completa la risorsa con le chiavi di `extra` e i campi derivati."""
            enums = {name: key for (res, name), key in FLAG_LISTS.items() if res == info.type}
            return finish_resource(
                info,
                EXTRA.get(info.type, []),
                enums=enums,
                unsupported=UNSUPPORTED.get(info.type, frozenset()),
                read_only=READ_ONLY.get(info.type, frozenset()),
            )

        resources = [
            describe_resource("zone", ZoneOut, ZoneIn),
            describe_resource("room", RoomDetail, RoomIn, skip=frozenset({"extra", "exits", "extra_descriptions"})),
            describe_resource("exit", ExitOut, ExitIn, read_only=frozenset({"id", "room_id"})),
            describe_resource("extra_description", ExtraDescriptionOut, ExtraDescriptionIn),
            describe_resource("mob", MobOut, MobIn),
            describe_resource("object", ObjectOut, ObjectIn),
            describe_resource("reset_command", ResetCommandOut, ResetCommandIn, skip=frozenset({"extra", "if_value", "comment"})),
        ]
        return AdapterInfo(
            id=self.config.id,
            kind=self.config.kind,
            name=self.config.name or "Pachimud",
            capabilities=self.capabilities(),
            resources=[finish(r) for r in resources],
        )

    def unsupported_reset_types(self) -> frozenset[int]:
        """`R` (rimescola le uscite) non esiste nel gioco: la conversione lo scarta riportando la perdita."""
        return frozenset({int(ZoneCommandType.RANDOMIZE_EXITS)})

    # ------------------------------------------------------------------ integrita'

    def integrity(self) -> list[integrity.Warn]:
        """I problemi di qualita' dei dati del mondo (vedi `integrity.py`)."""
        return integrity.collect(self.sync())

    # ------------------------------------------------------------------ trasferimento YAML

    async def export_zone_bundle(self, zone_id: int) -> ZoneBundle:
        """I file YAML della zona come testo, esattamente come sono su disco."""
        zone = self.sync().zone(zone_id)
        if zone is None:
            raise api_error(404, "transfer.zone_not_found", id=zone_id)
        return transfer.bundle(self.store, zone)

    async def import_zone_dir(self, directory: Path, *, dry_run: bool, confirm: bool) -> ImportPreview:
        """Anteprima e, con `dry_run=False` e `confirm=True`, import (upsert per vnum, mai cancellazioni).

        409 `transfer.vnum_conflict` se un vnum del file appartiene a un'altra zona.
        """
        if not dry_run and not confirm:
            raise api_error(422, "transfer.confirm_required", loc=("query", "confirm"))
        if not dry_run:
            self.ensure_writable()
        parsed = await run_in_threadpool(transfer.parse_zone_dir, directory)  # YAML+pydantic sincroni: fuori dal loop
        race_ids, class_ids = self.content_ids()
        if dry_run:
            return transfer.preview(self.sync(), parsed, race_ids, class_ids)
        async with self.writing():
            preview = transfer.preview(self.store, parsed, race_ids, class_ids)
            if preview.conflicts:
                raise api_error(
                    409,
                    "transfer.vnum_conflict",
                    count=len(preview.conflicts),
                    vnums=", ".join(f"{c.kind} {c.vnum} (zona {c.zone_vnum})" for c in preview.conflicts[:10]),
                )
            transfer.apply(self.store, parsed)
            preview.applied = True
            return preview
