"""Servizio dell'API di conversione: risolve i mondi per id, esegue il motore, traduce il rapporto."""

from pachifast.i18n import translate

from pachimudeditor.apps.convert.schemas import ConvertRequest, PairInfo, PairsResponse, WorldRef
from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.convert.converter import get_converter
from pachimudeditor.common.adapters.convert.engine import convert, ensure_distinct
from pachimudeditor.common.adapters.convert.journal import journal_dir
from pachimudeditor.common.adapters.convert.models import ConvertReport
from pachimudeditor.common.adapters.registry import get_registry


def _adapters(source_id: str, target_id: str) -> tuple[WorldAdapter, WorldAdapter]:
    """Gli adapter dei due mondi per id (404 `world.not_found`), senza passare da `X-World`."""
    registry = get_registry()
    return registry.get(source_id), registry.get(target_id)


def translate_report(report: ConvertReport) -> ConvertReport:
    """Riempie `message` di perdite ed errori nella lingua della richiesta."""
    for item in report.losses:
        item.message = translate(f"convert.loss.{item.code}", {**item.params, "field": item.field})
    for err in [*report.errors, *report.rollback_errors]:
        err.message = translate(err.code, err.params)
    return report


async def run_conversion(body: ConvertRequest, *, force_dry_run: bool) -> ConvertReport:
    """Esegue (o anteprima, con `force_dry_run`) la conversione descritta dal corpo della richiesta."""
    source, target = _adapters(body.source_world, body.target_world)
    report = await convert(
        source,
        target,
        body,
        dry_run=True if force_dry_run else body.dry_run,
        confirm=body.confirm,
        journal_dir=journal_dir(),
    )
    return translate_report(report)


def list_pairs() -> PairsResponse:
    """Mondi e coppie ordinate con convertitore e ammissibilita'."""
    registry = get_registry()
    infos = {wid: registry.get(wid).describe() for wid in registry.world_ids}
    worlds = [WorldRef(id=i.id, kind=i.kind, name=i.name, read_only=i.capabilities.read_only) for i in infos.values()]
    pairs: list[PairInfo] = []
    for sid, s in infos.items():
        for tid, t in infos.items():
            reason = None
            if sid == tid:
                reason = "same_world"
            else:
                try:  # come /run: prima "stessi dati" (anche sotto due id), poi la sola lettura
                    ensure_distinct(registry.get(sid), registry.get(tid))
                except Exception:  # noqa: BLE001
                    reason = "same_world"
                if reason is None and t.capabilities.read_only:
                    reason = "target_read_only"
            pairs.append(
                PairInfo(
                    source=sid,
                    target=tid,
                    source_kind=s.kind,
                    target_kind=t.kind,
                    converter="generic" if get_converter(s.kind, t.kind).generic else "specific",
                    allowed=reason is None,
                    reason=reason,
                )  # fmt: skip
            )
    return PairsResponse(worlds=worlds, pairs=pairs, journal_enabled=journal_dir() is not None)
