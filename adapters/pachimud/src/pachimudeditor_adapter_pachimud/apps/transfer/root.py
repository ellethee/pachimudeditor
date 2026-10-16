"""Trasferimento zone: esportazione e importazione nel formato YAML del game server. Prefisso `/api/transfer`."""

import re
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import Depends, File, Query, Response, UploadFile
from pachifast.i18n import api_error
from pachifast.router_factory import get_router

from pachimudeditor_adapter_pachimud.transfer.files import ZONE_FILES
from pachimudeditor_adapter_pachimud.apps.transfer.archive import stage_uploads
from pachimudeditor.common.adapters.models import ImportPreview, ZoneBundle
from pachimudeditor.sdk import AdapterDep, require_capability

router = get_router(deps=[Depends(require_capability("supports_transfer"))])


@router.get("/zones/{zone_id}/export", response_model=None, skip_envelope=True)
async def export_zone(zone_id: int, adapter: AdapterDep) -> Response:
    """Zip `<cartella>/{zone,rooms,mobs,objects,resets}.yaml` nel formato dell'importer del gioco."""
    bundle = await adapter.export_zone_bundle(zone_id)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ZONE_FILES:
            archive.writestr(f"{bundle.folder}/{name}", bundle.files[name])
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{bundle.folder}-{bundle.zone_vnum}.zip")
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/zones/{zone_id}/export/bundle", response_model=ZoneBundle)
async def export_zone_bundle(zone_id: int, adapter: AdapterDep) -> ZoneBundle:
    """Gli stessi cinque file come JSON (`files`: nome -> testo YAML), per anteprima o integrazioni."""
    return await adapter.export_zone_bundle(zone_id)


@router.post("/zones/import", response_model=ImportPreview)
async def import_zone(
    adapter: AdapterDep,
    files: Annotated[list[UploadFile], File(description="Uno zip della zona e/o i file zone/rooms/mobs/objects/resets .yaml")],
    dry_run: Annotated[bool, Query(alias="dryRun")] = True,
    confirm: Annotated[bool, Query()] = False,
) -> ImportPreview:
    """Importa una zona dai file caricati.

    Con `dryRun=true` (default) restituisce solo il riepilogo di creazioni/aggiornamenti per vnum e non
    scrive nulla. L'import vero richiede `dryRun=false` **e** `confirm=true` (altrimenti 422
    `transfer.confirm_required`) ed e' bloccato (409 `transfer.vnum_conflict`) se un vnum del file
    appartiene a un'altra zona. Stessa semantica dell'importer: upsert per vnum, mai cancellazioni.
    """
    if not dry_run and not confirm:
        raise api_error(422, "transfer.confirm_required", loc=("query", "confirm"))
    with tempfile.TemporaryDirectory(prefix="pachimud-import-") as tmp:
        zone_dir = await stage_uploads(files, Path(tmp))
        return await adapter.import_zone_dir(zone_dir, dry_run=dry_run, confirm=confirm)
