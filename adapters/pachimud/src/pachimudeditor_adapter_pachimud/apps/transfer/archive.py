"""Preparazione di un upload (zip e/o yaml) in una cartella temporanea di zona, senza fidarsi dei nomi.

Dai nomi dei file caricati si usa solo il *nome base*, e solo se e' uno dei cinque file di zona:
i path interni a uno zip non vengono mai usati per scrivere su disco (niente path traversal / zip slip).
"""

import zipfile
from pathlib import Path, PurePosixPath

from fastapi import UploadFile
from pachifast.i18n import api_error

from pachimudeditor_adapter_pachimud.transfer.files import ZONE_FILES

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
"""Limite per il totale decompresso (e per ogni singolo file caricato)."""
MAX_MEMBERS = 200
"""Numero massimo di voci in uno zip."""


def canonical_name(name: str) -> str | None:
    """Il nome canonico (`zone.yaml`, ...) del file `name` (solo base name, case-insensitive; `.yml` accettato)."""
    base = PurePosixPath(name.replace("\\", "/")).name.lower()
    if base.endswith(".yml"):
        base = base[:-4] + ".yaml"
    return base if base in ZONE_FILES else None


async def _read_limited(upload: UploadFile) -> bytes:
    """Legge un upload fino a `MAX_UPLOAD_BYTES`; oltre -> 413."""
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise api_error(413, "transfer.file_too_large", file=upload.filename or "", max_mb=MAX_UPLOAD_BYTES // (1024 * 1024))
    return data


def _extract_zip(data: bytes, filename: str, target: Path) -> None:
    """Estrae in `target/<n>/<nomecanonico>` i file di zona di uno zip, raggruppati per cartella di origine."""
    import io

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise api_error(422, "transfer.invalid_archive", file=filename) from error
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise api_error(422, "transfer.invalid_archive", file=filename)
        total = 0
        groups: dict[str, Path] = {}
        for info in infos:
            if info.is_dir():
                continue
            name = canonical_name(info.filename)
            if name is None:
                continue
            if info.file_size > MAX_UPLOAD_BYTES:  # il dichiarato e' solo un rifiuto rapido: il limite vero e' sui byte letti
                raise api_error(413, "transfer.file_too_large", file=filename, max_mb=MAX_UPLOAD_BYTES // (1024 * 1024))
            parent = str(PurePosixPath(info.filename.replace("\\", "/")).parent)
            if parent not in groups:
                group = target / f"g{len(groups)}"
                group.mkdir(parents=True)
                groups[parent] = group
            with archive.open(info) as source:
                content = source.read(min(MAX_UPLOAD_BYTES, MAX_UPLOAD_BYTES - total) + 1)
            total += len(content)
            if total > MAX_UPLOAD_BYTES:
                raise api_error(413, "transfer.file_too_large", file=filename, max_mb=MAX_UPLOAD_BYTES // (1024 * 1024))
            (groups[parent] / name).write_bytes(content)


async def stage_uploads(uploads: list[UploadFile], target: Path) -> Path:
    """Scrive gli upload in `target` e restituisce la cartella della (unica) zona trovata.

    Errori 422: nessun file (`transfer.no_files`), file non riconosciuto (`transfer.unsupported_file`),
    zip non valido (`transfer.invalid_archive`), nessun `zone.yaml` (`transfer.zone_missing`),
    piu' zone (`transfer.multiple_zones`).
    """
    if not uploads:
        raise api_error(422, "transfer.no_files")
    loose = target / "loose"
    loose.mkdir(parents=True)
    for upload in uploads:
        filename = upload.filename or ""
        data = await _read_limited(upload)
        if filename.lower().endswith(".zip") or data[:2] == b"PK":
            _extract_zip(data, filename, target)
            continue
        name = canonical_name(filename)
        if name is None:
            raise api_error(422, "transfer.unsupported_file", file=filename)
        (loose / name).write_bytes(data)
    candidates = sorted(p for p in target.rglob("zone.yaml"))
    if not candidates:
        raise api_error(422, "transfer.zone_missing")
    if len(candidates) > 1:
        raise api_error(422, "transfer.multiple_zones", count=len(candidates))
    return candidates[0].parent
