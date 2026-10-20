"""`PachimudAdapter`: il mondo pachimud (database SQLAlchemy letto "al volo" + YAML di definizioni).

Implementa `WorldAdapter` componendo i mixin per area (`zones`, `rooms`, `prototypes`, `meta`). NON importa il gioco:
apre il database indicato dai parametri del mondo (`database_url`, `definitions_path`, `config_path`: vedi
`adapters.pachimud.params`), ne rifletta le tabelle (`adapters.pachimud.schema`) e gestisce da se' engine e sessioni
(`adapters.pachimud.connection`). `id` = chiave primaria della riga. Capability: tutte quelle che lo schema reale e la
configurazione permettono (panoramica mondo, istanze, giocatori, trasferimento YAML, razze/classi).
"""

import logging
import tempfile
from pathlib import Path
from pachifast.i18n import api_error
from starlette.concurrency import run_in_threadpool

from pachimudeditor_adapter_pachimud.meta import MetaMixin
from pachimudeditor_adapter_pachimud.prototypes import PrototypesMixin
from pachimudeditor_adapter_pachimud.rooms import RoomsMixin
from pachimudeditor_adapter_pachimud.schema import SchemaReport, SchemaUnavailable, models_of
from pachimudeditor_adapter_pachimud.transfer.files import snapshot_zone, zone_slug
from pachimudeditor_adapter_pachimud.transfer.importer import import_zone_directory, parse_zone_dir
from pachimudeditor_adapter_pachimud.transfer.preview import build_preview
from pachimudeditor_adapter_pachimud.zones import ZonesMixin
from pachimudeditor.sdk import AdapterCapabilities, AdapterInfo, ResourceInfo, WorldAdapter
from pachimudeditor.sdk import describe_resource
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
from pachimudeditor.sdk import WorldConfig

log = logging.getLogger(__name__)


class PachimudAdapter(ZonesMixin, RoomsMixin, PrototypesMixin, MetaMixin, WorldAdapter):
    """Adapter del database di pachimud (vedi docstring del modulo)."""

    def __init__(self, config: WorldConfig) -> None:
        """Risolve i parametri del mondo (`PachimudConfigError` se mancano o non sono validi)."""
        super().__init__(config)

    # ------------------------------------------------------------------ schema e capability

    def schema_report(self, *, refresh: bool = False) -> SchemaReport | None:
        """Il rapporto di compatibilita' con il gioco (revisione alembic, colonne assenti, ...) o `None` se il DB non e'
        utilizzabile (`unavailable_reason()` ne dice il motivo)."""
        try:
            return self.connection.schema(refresh=refresh).report
        except SchemaUnavailable as exc:
            return exc.report

    def unavailable_reason(self) -> str | None:
        """Perche' il database non e' utilizzabile ora, o `None` se lo e'."""
        try:
            self.connection.schema()
        except SchemaUnavailable as exc:
            return str(exc)
        return None

    def log_schema_report(self) -> None:
        """Scrive nel log lo stato dello schema (avvisi inclusi): da chiamare all'avvio dell'app."""
        report = self.schema_report(refresh=True)
        name = f"mondo {self.config.id!r} ({self.params.redacted_url()})"
        if report is None:
            log.warning("%s non utilizzabile: %s", name, self.unavailable_reason())
            return
        log.info("%s: %s", name, report.summary())
        for issue in report.warnings:
            log.warning("%s: schema [%s] %s", name, issue.code, issue.message)

    def capabilities(self) -> AdapterCapabilities:
        """Le capability consentite dallo schema reale e dalla configurazione; `read_only` e' da configurazione.

        Con il DB non utilizzabile restano solo `read_only` e le funzioni che non lo richiedono.
        """
        try:
            models = self.connection.schema().models
        except SchemaUnavailable:
            return AdapterCapabilities(read_only=self.config.read_only, supports_reset_scripts=False, supports_extra_descriptions=False)
        return AdapterCapabilities(
            read_only=self.config.read_only,
            supports_world_overview=True,
            supports_instances=models.has("mob_instance") and models.has("object_instance") and models.has("player_character"),
            supports_players=models.has("account") and models.has("player_character") and models.has("object_instance"),
            supports_transfer=True,
            supports_content_races=self.params.definitions_path is not None,
            supports_reset_scripts=True,
            supports_extra_descriptions=models.has("room_extra_description"),
        )

    def describe(self) -> AdapterInfo:
        """Descrittori dei campi ricavati dagli schemi Pydantic dei DTO; i campi senza colonna nel DB sono `unsupported`."""
        try:
            models = self.connection.schema().models
        except SchemaUnavailable:
            models = None

        def resource(info: ResourceInfo) -> ResourceInfo:
            """Marca i campi non supportati dallo schema reale."""
            if models is None:
                return info
            unsupported = models.unsupported_fields(info.type)
            if not unsupported:
                return info
            fields = [f.model_copy(update={"unsupported": True, "read_only": True}) if f.name in unsupported else f for f in info.fields]
            return info.model_copy(update={"fields": fields})

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
            resources=[resource(r) for r in resources],
        )

    # ------------------------------------------------------------------ trasferimento YAML

    async def export_zone_bundle(self, zone_id: int) -> ZoneBundle:
        """I cinque file YAML di una zona (formato dell'importer del gioco), con eventuali warning di validita'."""
        async with self.session() as session:
            zone = await session.get(models_of(session).Zone, zone_id)
            if zone is None:
                raise api_error(404, "transfer.zone_not_found", id=zone_id)
            snapshot = await snapshot_zone(session, zone)
            texts = snapshot.texts()
            vnum, name, folder = zone.vnum, zone.name, zone_slug(zone)
        warnings: list[str] = []
        with tempfile.TemporaryDirectory(prefix="pachimud-export-") as tmp:
            for file_name, text in texts.items():
                (Path(tmp) / file_name).write_text(text, encoding="utf-8")
            try:
                parse_zone_dir(Path(tmp))
            except Exception as error:  # dati incoerenti nel DB: si esporta comunque, segnalando
                detail = error.detail[0].get("msg", "") if hasattr(error, "detail") and error.detail else str(error)
                warnings.append(str(detail))
        return ZoneBundle(zone_vnum=vnum, zone_name=name, folder=folder, files=texts, warnings=warnings)

    async def import_zone_dir(self, directory: Path, *, dry_run: bool, confirm: bool) -> ImportPreview:
        """Anteprima e, con `dry_run=False` e `confirm=True`, import (upsert per vnum, mai cancellazioni).

        409 `transfer.vnum_conflict` se un vnum del file appartiene a un'altra zona.
        """
        if not dry_run and not confirm:
            raise api_error(422, "transfer.confirm_required", loc=("query", "confirm"))
        if not dry_run:
            self.ensure_writable()
        parsed = await run_in_threadpool(parse_zone_dir, directory)  # YAML+pydantic sincroni: fuori dal loop
        race_ids, class_ids = self.content_ids()
        async with self.session() as session:
            preview = await build_preview(session, parsed, race_ids, class_ids)
            if dry_run:
                return preview
            if preview.conflicts:
                raise api_error(
                    409,
                    "transfer.vnum_conflict",
                    count=len(preview.conflicts),
                    vnums=", ".join(f"{c.kind} {c.vnum} (zona {c.zone_vnum})" for c in preview.conflicts[:10]),
                )
            try:
                await import_zone_directory(session, directory, race_ids=race_ids, class_ids=class_ids, parsed=parsed)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            preview.applied = True
            return preview
