"""Motore di conversione tra mondi: `convert(source, target, plan)`.

Legge dalla sorgente e scrive sull'arrivo **solo** attraverso `WorldAdapter`; la traduzione dei dati e' del
`PairConverter` della coppia (`common.adapters.convert.converter`). Flusso: controlli di sicurezza -> lettura delle
zone sorgente e dell'indice dell'arrivo -> pianificazione (`planner`) -> costruzione del contenuto (`build`) ->
rapporto; solo se non e' un dry-run -> scrittura (`writer`) con rollback best-effort in caso di errore -> giornale.
"""

from pathlib import Path

from pachifast.i18n import api_error

from pachimudeditor.common.adapters.base import WorldAdapter
from pachimudeditor.common.adapters.convert import build as builder
from pachimudeditor.common.adapters.convert import planner, writer
from pachimudeditor.common.adapters.convert.converter import ConvertContext, get_converter
from pachimudeditor.common.adapters.convert.journal import write_journal
from pachimudeditor.common.adapters.convert.models import (
    ConvertPlan,
    ConvertReport,
    EntityCounts,
    ZoneAction,
)
from pachimudeditor.common.adapters.convert.reader import SourceZone, read_target_index, read_zone


def ensure_distinct(source: WorldAdapter, target: WorldAdapter) -> None:
    """422 `convert.same_world` se sorgente e arrivo sono lo stesso mondo (stesso id, oggetto o stessi dati)."""
    if source is target or source.describe().id == target.describe().id:
        raise api_error(422, "convert.same_world")
    cs, ct = getattr(source, "config", None), getattr(target, "config", None)
    if cs is not None and ct is not None and cs.kind == ct.kind and cs.path == ct.path and cs.mapping == ct.mapping:
        raise api_error(422, "convert.same_world")


async def _context(target: WorldAdapter) -> ConvertContext:
    """Razze e classi del mondo di arrivo (per i riferimenti dei mob)."""
    races = {r.id for r in await target.races()}
    classes = {c.id for c in await target.classes()}
    return ConvertContext(target_races=races or None, target_classes=classes or None)


def _totals(zones: list[ZoneAction], built: builder.BuildResult, sources: list[SourceZone]) -> dict[str, EntityCounts]:
    """Conteggi per tipo: creazioni, sostituzioni, saltati, scartati."""
    totals = {name: EntityCounts() for name in builder.ENTITIES}
    for z in zones:
        totals["zones"].create += z.action == "create"
        totals["zones"].replace += z.action == "replace"
        totals["zones"].skip += z.action in ("skip", "blocked")
    for zw in built.writes:
        replace = zw.plan.action == "replace"
        for name in builder.ENTITIES[1:]:
            if replace:
                totals[name].replace += zw.counts.get(name, 0)
            else:
                totals[name].create += zw.counts.get(name, 0)
    written = {zw.plan.src.zone.id for zw in built.writes}
    for src in sources:
        if src.zone.id not in written:
            totals["rooms"].skip += len(src.rooms)
            totals["mobs"].skip += len(src.mobs)
            totals["objects"].skip += len(src.objects)
    for name, count in built.dropped.items():
        totals[name].dropped = count
    return totals


async def convert(
    source: WorldAdapter,
    target: WorldAdapter,
    plan: ConvertPlan,
    *,
    dry_run: bool = True,
    confirm: bool = False,
    journal_dir: Path | None = None,
) -> ConvertReport:
    """Converte le zone del piano da `source` a `target`.

    Con `dry_run` (default) non scrive nulla e restituisce il rapporto completo. La scrittura vera richiede
    `dry_run=False` **e** `confirm=True` (422 `convert.confirm_required`); il mondo di arrivo non puo' essere in
    sola lettura (409 `world.read_only`, anche in anteprima) ne' coincidere con la sorgente (422 `convert.same_world`).
    """
    ensure_distinct(source, target)
    if target.capabilities().read_only:
        raise api_error(409, "world.read_only")
    if not dry_run and not confirm:
        raise api_error(422, "convert.confirm_required")
    if len(set(plan.zone_ids)) != len(plan.zone_ids):
        raise api_error(422, "convert.duplicate_zone")
    s_info, t_info = source.describe(), target.describe()
    converter = get_converter(s_info.kind, t_info.kind)

    sources = [await read_zone(source, zid, with_resets=plan.convert_resets) for zid in plan.zone_ids]
    index = await read_target_index(target)
    plans = await planner.allocate(target, sources, plan)
    planner.detect_conflicts(plans, index, plan)
    ctx = await _context(target)
    built = builder.build(plans, converter, ctx, index, plan)

    by_vnum = {zw.plan.src.zone.vnum: zw for zw in built.writes}
    zones = [
        ZoneAction(
            source_zone_id=p.src.zone.id,
            source_vnum=p.src.zone.vnum,
            name=p.src.zone.name,
            action=p.action,  # type: ignore[arg-type]
            target_vnum=p.target_vnum,
            target_zone_id=p.existing.id if p.existing is not None and p.written else None,
            source_bottom_vnum=p.src.zone.bottom_vnum,
            source_top_vnum=p.src.zone.top_vnum,
            bottom_vnum=p.bottom,
            top_vnum=p.top,
            offset=p.offset,
            counts=by_vnum[p.src.zone.vnum].counts if p.src.zone.vnum in by_vnum else {},
        )
        for p in plans
    ]
    report = ConvertReport(
        dry_run=dry_run,
        source_world=s_info.id,
        target_world=t_info.id,
        source_kind=s_info.kind,
        target_kind=t_info.kind,
        converter="generic" if converter.generic else "specific",
        zones=zones,
        totals=_totals(zones, built, sources),
        remap=built.remap,
        losses=built.losses,
        conflicts=[c for p in plans for c in p.conflicts],
    )
    summary: dict[str, int] = {}
    for item in report.losses:
        summary[item.severity] = summary.get(item.severity, 0) + 1
    report.loss_summary = summary
    if dry_run:
        return report

    created = writer.Created()
    try:
        await writer.write_all(target, built.writes, created, index)
    except Exception as error:  # noqa: BLE001  (qualunque errore: rollback e rapporto)
        report.errors.append(writer.error_of(error, "write"))
        report.rollback_errors = await writer.rollback(target, created, index)
        report.rolled_back = True
        for z in report.zones:
            z.target_zone_id = None
    else:
        report.applied = True
        for z in report.zones:
            z.target_zone_id = created.zone_ids.get(z.source_vnum, z.target_zone_id)
    report.journal = write_journal(journal_dir, plan, report)
    return report


__all__ = ["convert", "ensure_distinct"]
